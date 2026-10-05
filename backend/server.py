from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
import io
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta, date

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ----------------------------- Auth helpers -----------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only the treasurer (admin) can manage users")
    return user


# ----------------------------- Models -----------------------------
class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "user"


class AccountInput(BaseModel):
    name: str
    mask: str = ""
    opening_balance: float = 0.0
    opening_date: str = ""
    active: bool = True


class FundInput(BaseModel):
    name: str
    description: str = ""
    active: bool = True


class CategoryInput(BaseModel):
    name: str
    type: str = "expense"  # income | expense
    active: bool = True


class PayeeInput(BaseModel):
    name: str
    active: bool = True


class CoaInput(BaseModel):
    code: str = ""
    name: str
    group: str  # Asset | Liability | Equity | Income | Expense
    active: bool = True


class TransactionInput(BaseModel):
    type: str  # income | expense | transfer
    date: str  # YYYY-MM-DD
    account_id: str
    to_account_id: Optional[str] = None
    amount: float
    payee_id: Optional[str] = None
    check_number: Optional[str] = ""
    category_id: Optional[str] = None
    fund_id: Optional[str] = None
    memo: Optional[str] = ""


class ChurchSettings(BaseModel):
    church_name: str
    treasurer_name: str = ""
    meeting_day: str = ""


# ----------------------------- Utils -----------------------------
def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


async def signed_amount_for_account(txn: dict, account_id: str) -> float:
    """Return the net effect of a transaction on a given account."""
    amt = float(txn["amount"])
    if txn["type"] == "income" and txn["account_id"] == account_id:
        return amt
    if txn["type"] == "expense" and txn["account_id"] == account_id:
        return -amt
    if txn["type"] == "transfer":
        if txn["account_id"] == account_id:
            return -amt
        if txn.get("to_account_id") == account_id:
            return amt
    return 0.0


async def account_balance(account: dict, up_to: Optional[str] = None) -> float:
    """Balance of an account. up_to is inclusive end date (YYYY-MM-DD) or None for all."""
    query = {"$or": [{"account_id": account["id"]}, {"to_account_id": account["id"]}]}
    if up_to is not None:
        query["date"] = {"$lte": up_to}
    bal = float(account.get("opening_balance", 0.0) or 0.0)
    async for txn in db.transactions.find(query, {"_id": 0}):
        bal += await signed_amount_for_account(txn, account["id"])
    return round(bal, 2)


async def balance_before(account: dict, start: str) -> float:
    """Balance as of the day before `start` (exclusive)."""
    query = {
        "$or": [{"account_id": account["id"]}, {"to_account_id": account["id"]}],
        "date": {"$lt": start},
    }
    bal = float(account.get("opening_balance", 0.0) or 0.0)
    async for txn in db.transactions.find(query, {"_id": 0}):
        bal += await signed_amount_for_account(txn, account["id"])
    return round(bal, 2)


# ----------------------------- Auth routes -----------------------------
@api_router.post("/auth/login")
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]},
    }


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api_router.get("/auth/users")
async def list_users(user: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return users


@api_router.post("/auth/users")
async def create_user(data: UserCreate, user: dict = Depends(require_admin)):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    doc = {
        "id": new_id(),
        "email": data.email.lower(),
        "name": data.name,
        "role": data.role if data.role in ("admin", "user") else "user",
        "password_hash": hash_password(data.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return {"id": doc["id"], "email": doc["email"], "name": doc["name"], "role": doc["role"]}


@api_router.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.delete_one({"id": user_id})
    return {"ok": True}


# ----------------------------- Generic CRUD factory -----------------------------
def register_crud(path: str, collection: str, model):
    @api_router.get(f"/{path}")
    async def list_items(user: dict = Depends(get_current_user), _coll=collection):
        items = await db[_coll].find({}, {"_id": 0}).sort("name", 1).to_list(1000)
        return items

    @api_router.post(f"/{path}")
    async def create_item(data: model, user: dict = Depends(get_current_user), _coll=collection):
        doc = data.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await db[_coll].insert_one(doc)
        return clean(doc)

    @api_router.put(f"/{path}/{{item_id}}")
    async def update_item(item_id: str, data: model, user: dict = Depends(get_current_user), _coll=collection):
        existing = await db[_coll].find_one({"id": item_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        await db[_coll].update_one({"id": item_id}, {"$set": data.model_dump()})
        updated = await db[_coll].find_one({"id": item_id}, {"_id": 0})
        return updated

    @api_router.delete(f"/{path}/{{item_id}}")
    async def delete_item(item_id: str, user: dict = Depends(get_current_user), _coll=collection):
        await db[_coll].delete_one({"id": item_id})
        return {"ok": True}


register_crud("accounts", "accounts", AccountInput)
register_crud("funds", "funds", FundInput)
register_crud("categories", "categories", CategoryInput)
register_crud("payees", "payees", PayeeInput)
register_crud("coa", "coa", CoaInput)


# ----------------------------- Transactions -----------------------------
@api_router.get("/transactions")
async def list_transactions(
    user: dict = Depends(get_current_user),
    account_id: Optional[str] = None,
    fund_id: Optional[str] = None,
    category_id: Optional[str] = None,
    payee_id: Optional[str] = None,
    type: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    search: Optional[str] = None,
):
    query: dict = {}
    if account_id:
        query["$or"] = [{"account_id": account_id}, {"to_account_id": account_id}]
    if fund_id:
        query["fund_id"] = fund_id
    if category_id:
        query["category_id"] = category_id
    if payee_id:
        query["payee_id"] = payee_id
    if type:
        query["type"] = type
    if start or end:
        drange = {}
        if start:
            drange["$gte"] = start
        if end:
            drange["$lte"] = end
        query["date"] = drange
    if search:
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"memo": {"$regex": search, "$options": "i"}},
                {"check_number": {"$regex": search, "$options": "i"}},
            ]
        }]
    items = await db.transactions.find(query, {"_id": 0}).sort("date", -1).to_list(5000)
    return items


@api_router.post("/transactions")
async def create_transaction(data: TransactionInput, user: dict = Depends(get_current_user)):
    if data.type == "transfer" and not data.to_account_id:
        raise HTTPException(status_code=400, detail="Transfer requires a destination account")
    doc = data.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.transactions.insert_one(doc)
    return clean(doc)


@api_router.put("/transactions/{txn_id}")
async def update_transaction(txn_id: str, data: TransactionInput, user: dict = Depends(get_current_user)):
    existing = await db.transactions.find_one({"id": txn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.transactions.update_one({"id": txn_id}, {"$set": data.model_dump()})
    updated = await db.transactions.find_one({"id": txn_id}, {"_id": 0})
    return updated


@api_router.delete("/transactions/{txn_id}")
async def delete_transaction(txn_id: str, user: dict = Depends(get_current_user)):
    await db.transactions.delete_one({"id": txn_id})
    return {"ok": True}


# ----------------------------- Dashboard -----------------------------
@api_router.get("/dashboard")
async def dashboard(user: dict = Depends(get_current_user)):
    accounts = await db.accounts.find({}, {"_id": 0}).to_list(1000)
    account_balances = []
    total = 0.0
    for acc in accounts:
        bal = await account_balance(acc)
        total += bal
        account_balances.append({**acc, "balance": bal})

    # fund balances
    funds = await db.funds.find({}, {"_id": 0}).to_list(1000)
    fund_map = {f["id"]: {**f, "balance": 0.0} for f in funds}
    async for txn in db.transactions.find({"fund_id": {"$ne": None}}, {"_id": 0}):
        fid = txn.get("fund_id")
        if fid in fund_map:
            if txn["type"] == "income":
                fund_map[fid]["balance"] += float(txn["amount"])
            elif txn["type"] == "expense":
                fund_map[fid]["balance"] -= float(txn["amount"])
    fund_balances = [ {**v, "balance": round(v["balance"], 2)} for v in fund_map.values() ]

    # recent transactions (enriched)
    recent = await db.transactions.find({}, {"_id": 0}).sort("date", -1).limit(8).to_list(8)
    acc_names = {a["id"]: a for a in accounts}
    payees = {p["id"]: p["name"] for p in await db.payees.find({}, {"_id": 0}).to_list(1000)}
    for t in recent:
        t["account_name"] = acc_names.get(t["account_id"], {}).get("name", "")
        t["account_mask"] = acc_names.get(t["account_id"], {}).get("mask", "")
        t["payee_name"] = payees.get(t.get("payee_id"), "")

    return {
        "total_balance": round(total, 2),
        "accounts": account_balances,
        "funds": fund_balances,
        "recent": recent,
    }


# ----------------------------- Report data builder -----------------------------
async def build_report(start: str, end: str, account_ids: List[str]):
    accounts = await db.accounts.find({"id": {"$in": account_ids}}, {"_id": 0}).to_list(1000)
    accounts.sort(key=lambda a: a.get("mask", ""))
    payees = {p["id"]: p["name"] for p in await db.payees.find({}, {"_id": 0}).to_list(1000)}
    categories = {c["id"]: c["name"] for c in await db.categories.find({}, {"_id": 0}).to_list(1000)}
    account_names = {a["id"]: a for a in await db.accounts.find({}, {"_id": 0}).to_list(1000)}

    report_accounts = []
    for acc in accounts:
        bf = await balance_before(acc, start)
        query = {
            "$or": [{"account_id": acc["id"]}, {"to_account_id": acc["id"]}],
            "date": {"$gte": start, "$lte": end},
        }
        txns = await db.transactions.find(query, {"_id": 0}).sort("date", 1).to_list(5000)
        expenses = []
        incomes = []
        total_exp = 0.0
        total_inc = 0.0
        for t in txns:
            eff = await signed_amount_for_account(t, acc["id"])
            if eff < 0:
                label_payee = payees.get(t.get("payee_id"), "")
                if t["type"] == "transfer":
                    dest = account_names.get(t.get("to_account_id"), {})
                    label_payee = f"Transfer to {dest.get('mask') or dest.get('name', 'account')}"
                expenses.append({
                    "date": t["date"],
                    "check_number": t.get("check_number", ""),
                    "payee": label_payee,
                    "amount": round(-eff, 2),
                    "memo": t.get("memo", ""),
                    "category": categories.get(t.get("category_id"), ""),
                })
                total_exp += -eff
            elif eff > 0:
                if t["type"] == "transfer":
                    src = account_names.get(t.get("account_id"), {})
                    label = f"Transfer from {src.get('mask') or src.get('name', 'account')}"
                else:
                    label = categories.get(t.get("category_id")) or "Deposit"
                incomes.append({
                    "date": t["date"],
                    "label": label,
                    "amount": round(eff, 2),
                    "memo": t.get("memo", ""),
                    "category": categories.get(t.get("category_id"), ""),
                })
                total_inc += eff
        report_accounts.append({
            "id": acc["id"],
            "name": acc["name"],
            "mask": acc.get("mask", ""),
            "balance_forward": round(bf, 2),
            "expenses": expenses,
            "incomes": incomes,
            "total_expenses": round(total_exp, 2),
            "total_income": round(total_inc, 2),
            "new_balance": round(bf + total_inc - total_exp, 2),
        })

    # category summary across selected accounts
    cat_query = {
        "account_id": {"$in": account_ids},
        "date": {"$gte": start, "$lte": end},
        "type": {"$in": ["income", "expense"]},
    }
    cat_summary = {}
    async for t in db.transactions.find(cat_query, {"_id": 0}):
        name = categories.get(t.get("category_id"), "Uncategorized")
        key = (name, t["type"])
        cat_summary[key] = cat_summary.get(key, 0.0) + float(t["amount"])
    category_summary = [
        {"category": k[0], "type": k[1], "amount": round(v, 2)}
        for k, v in sorted(cat_summary.items(), key=lambda x: (x[0][1], x[0][0]))
    ]

    # fund balances as of end
    funds = await db.funds.find({}, {"_id": 0}).to_list(1000)
    fund_map = {f["id"]: {"name": f["name"], "balance": 0.0} for f in funds}
    async for t in db.transactions.find({"fund_id": {"$ne": None}, "date": {"$lte": end}}, {"_id": 0}):
        fid = t.get("fund_id")
        if fid in fund_map:
            if t["type"] == "income":
                fund_map[fid]["balance"] += float(t["amount"])
            elif t["type"] == "expense":
                fund_map[fid]["balance"] -= float(t["amount"])
    fund_balances = [{"name": v["name"], "balance": round(v["balance"], 2)} for v in fund_map.values()]

    church = await db.settings.find_one({"id": "church"}, {"_id": 0}) or {"church_name": os.environ.get("CHURCH_NAME", "Church"), "treasurer_name": ""}

    return {
        "church": church,
        "start": start,
        "end": end,
        "accounts": report_accounts,
        "category_summary": category_summary,
        "fund_balances": fund_balances,
    }


@api_router.get("/reports/treasurer")
async def treasurer_report(
    start: str = Query(...),
    end: str = Query(...),
    account_ids: str = Query(...),
    user: dict = Depends(get_current_user),
):
    ids = [i for i in account_ids.split(",") if i]
    return await build_report(start, end, ids)


# ----------------------------- PDF -----------------------------
def money(v: float) -> str:
    return f"${v:,.2f}"


def fmt_date(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%m/%d/%Y")
    except Exception:
        return s


@api_router.get("/reports/treasurer/pdf")
async def treasurer_report_pdf(
    start: str = Query(...),
    end: str = Query(...),
    account_ids: str = Query(...),
    include_category: bool = Query(False),
    include_funds: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    ids = [i for i in account_ids.split(",") if i]
    report = await build_report(start, end, ids)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    )
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#1E293B")
    brass = colors.HexColor("#B45309")
    muted = colors.HexColor("#64748B")

    h_title = ParagraphStyle("title", parent=styles["Title"], fontName="Times-Bold", fontSize=18, textColor=navy, alignment=TA_CENTER, spaceAfter=2)
    h_sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=11, textColor=muted, alignment=TA_CENTER, spaceAfter=2)
    h_acc = ParagraphStyle("acc", parent=styles["Heading2"], fontName="Times-Bold", fontSize=13, textColor=navy, spaceBefore=14, spaceAfter=4)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=10, textColor=brass, fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=3)
    normal = ParagraphStyle("n", parent=styles["Normal"], fontSize=9)

    elems = []
    church = report["church"]
    elems.append(Paragraph(church.get("church_name", "Church"), h_title))
    elems.append(Paragraph("Treasurer's Report", h_sub))
    elems.append(Paragraph(f"{fmt_date(start)} &mdash; {fmt_date(end)}", h_sub))
    elems.append(Spacer(1, 6))
    elems.append(HRFlowable(width="100%", thickness=1.2, color=navy))

    for acc in report["accounts"]:
        title = acc["mask"] or acc["name"]
        elems.append(Paragraph(f"Account {title} &nbsp; <font size=9 color='#64748B'>{acc['name']}</font>", h_acc))
        elems.append(Paragraph(f"Balance Forward as of {fmt_date(start)}: <b>{money(acc['balance_forward'])}</b>", normal))

        # Expenses
        elems.append(Paragraph("Expenses", label))
        exp_data = [["Date", "Check #", "Payee", "Memo / Reason", "Amount"]]
        for e in acc["expenses"]:
            exp_data.append([fmt_date(e["date"]), e["check_number"] or "", e["payee"] or "", e["memo"] or "", money(e["amount"])])
        if len(exp_data) == 1:
            exp_data.append(["", "", "No expenses", "", ""])
        exp_data.append(["", "", "", "Total Expenses", money(acc["total_expenses"])])
        t = Table(exp_data, colWidths=[0.75 * inch, 0.7 * inch, 2.2 * inch, 2.45 * inch, 0.9 * inch])
        t.setStyle(_table_style(navy, len(exp_data)))
        elems.append(t)

        # Income
        elems.append(Paragraph("Income", label))
        inc_data = [["Date", "Source", "Memo", "Amount"]]
        for i in acc["incomes"]:
            inc_data.append([fmt_date(i["date"]), i["label"], i.get("memo", "") or "", money(i["amount"])])
        if len(inc_data) == 1:
            inc_data.append(["", "No income", "", ""])
        inc_data.append(["", "", "Total Income", money(acc["total_income"])])
        ti = Table(inc_data, colWidths=[0.75 * inch, 2.9 * inch, 2.45 * inch, 0.9 * inch])
        ti.setStyle(_table_style(navy, len(inc_data)))
        elems.append(ti)

        # Summary
        elems.append(Spacer(1, 6))
        summ = [
            ["Balance Forward", money(acc["balance_forward"])],
            ["Total Income", money(acc["total_income"])],
            ["Less Expenses", f"({money(acc['total_expenses'])})"],
            [f"New Balance as of {fmt_date(end)}", money(acc["new_balance"])],
        ]
        ts = Table(summ, colWidths=[5.0 * inch, 2.0 * inch])
        ts.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, -1), (-1, -1), navy),
            ("LINEABOVE", (0, -1), (-1, -1), 1, navy),
            ("LINEBELOW", (1, -1), (1, -1), 2.5, navy),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elems.append(ts)

    if include_category and report["category_summary"]:
        elems.append(Paragraph("Income &amp; Expense by Category", h_acc))
        cat_data = [["Category", "Type", "Amount"]]
        for c in report["category_summary"]:
            cat_data.append([c["category"], c["type"].title(), money(c["amount"])])
        tc = Table(cat_data, colWidths=[3.5 * inch, 2.0 * inch, 1.5 * inch])
        tc.setStyle(_table_style(navy, len(cat_data), total_row=False))
        elems.append(tc)

    if include_funds and report["fund_balances"]:
        elems.append(Paragraph("Fund Balances", h_acc))
        f_data = [["Fund", "Balance"]]
        for f in report["fund_balances"]:
            f_data.append([f["name"], money(f["balance"])])
        tf = Table(f_data, colWidths=[5.0 * inch, 2.0 * inch])
        tf.setStyle(_table_style(navy, len(f_data), total_row=False))
        elems.append(tf)

    elems.append(Spacer(1, 30))
    elems.append(Paragraph("Respectfully submitted,", normal))
    elems.append(Spacer(1, 22))
    elems.append(Paragraph("______________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: ____________", normal))
    tname = church.get("treasurer_name") or ""
    elems.append(Paragraph(f"{tname}, Treasurer" if tname else "Treasurer", ParagraphStyle("t", parent=normal, textColor=muted, fontSize=8)))

    doc.build(elems)
    buf.seek(0)
    filename = f"treasurers-report-{start}-to-{end}.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


def _table_style(navy, nrows, total_row=True):
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#E5E0D8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#FAF8F3")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if total_row:
        style += [
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, navy),
            ("TEXTCOLOR", (0, -1), (-1, -1), navy),
        ]
    return TableStyle(style)


# ----------------------------- Church settings -----------------------------
@api_router.get("/settings/church")
async def get_church(user: dict = Depends(get_current_user)):
    doc = await db.settings.find_one({"id": "church"}, {"_id": 0})
    if not doc:
        doc = {"id": "church", "church_name": os.environ.get("CHURCH_NAME", "Church"), "treasurer_name": "", "meeting_day": ""}
    return doc


@api_router.put("/settings/church")
async def update_church(data: ChurchSettings, user: dict = Depends(get_current_user)):
    doc = {"id": "church", **data.model_dump()}
    await db.settings.update_one({"id": "church"}, {"$set": doc}, upsert=True)
    return doc


@api_router.get("/")
async def root():
    return {"message": "Church Treasury API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- Seeding -----------------------------
async def seed():
    await db.users.create_index("email", unique=True)

    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": new_id(), "email": admin_email, "name": "Treasurer",
            "role": "admin", "password_hash": hash_password(admin_password),
            "created_at": now_iso(),
        })
        logger.info("Seeded admin user")

    if await db.accounts.count_documents({}) == 0:
        accounts = [
            {"id": new_id(), "name": "General Operating Checking", "mask": "*3217", "opening_balance": 76880.68, "opening_date": "2025-12-31", "active": True, "created_at": now_iso()},
            {"id": new_id(), "name": "Savings", "mask": "*6715", "opening_balance": 54375.81, "opening_date": "2025-12-31", "active": True, "created_at": now_iso()},
            {"id": new_id(), "name": "Building Fund Savings", "mask": "*1180", "opening_balance": 0.0, "opening_date": "2025-12-31", "active": True, "created_at": now_iso()},
        ]
        await db.accounts.insert_many(accounts)
        acc_checking = accounts[0]["id"]

        funds = [
            {"id": new_id(), "name": "General Fund", "description": "Day-to-day operating fund", "active": True, "created_at": now_iso()},
            {"id": new_id(), "name": "Building Fund", "description": "Property and building projects", "active": True, "created_at": now_iso()},
            {"id": new_id(), "name": "Missions Fund", "description": "Missions and outreach giving", "active": True, "created_at": now_iso()},
        ]
        await db.funds.insert_many(funds)
        general_fund = funds[0]["id"]

        income_cats = ["Deposit", "Interest Paid", "Tithes & Offerings"]
        expense_cats = ["Utilities", "Donations / Missions", "Maintenance", "Supplies", "Salary", "Insurance", "Cleaning", "Literature"]
        cats = [{"id": new_id(), "name": n, "type": "income", "active": True, "created_at": now_iso()} for n in income_cats]
        cats += [{"id": new_id(), "name": n, "type": "expense", "active": True, "created_at": now_iso()} for n in expense_cats]
        await db.categories.insert_many(cats)
        cat_by_name = {c["name"]: c["id"] for c in cats}

        payee_names = [
            "William Spears", "Frontier Communications", "Mason County PSD", "Hope Gas",
            "Appalachian Power (Church)", "Appalachian Power (Lights)", "St. Jude Donation",
            "ECCHO Donation", "CEF of Greater Huntington", "Rock of Ages Ministry",
            "Our Daily Bread Ministries", "Henderson Insurance", "Jodi Sovine Mowing",
            "Walmart", "Sam's Club", "Amazon",
        ]
        payees = [{"id": new_id(), "name": n, "active": True, "created_at": now_iso()} for n in payee_names]
        await db.payees.insert_many(payees)
        payee_by_name = {p["name"]: p["id"] for p in payees}

        coa = [
            {"code": "1000", "name": "General Operating Checking", "group": "Asset"},
            {"code": "1010", "name": "Savings", "group": "Asset"},
            {"code": "1020", "name": "Building Fund Savings", "group": "Asset"},
            {"code": "2000", "name": "Accounts Payable", "group": "Liability"},
            {"code": "3000", "name": "General Fund Balance", "group": "Equity"},
            {"code": "3010", "name": "Building Fund Balance", "group": "Equity"},
            {"code": "3020", "name": "Missions Fund Balance", "group": "Equity"},
            {"code": "4000", "name": "Tithes & Offerings", "group": "Income"},
            {"code": "4010", "name": "Deposit", "group": "Income"},
            {"code": "4020", "name": "Interest Paid", "group": "Income"},
            {"code": "5000", "name": "Utilities", "group": "Expense"},
            {"code": "5010", "name": "Donations / Missions", "group": "Expense"},
            {"code": "5020", "name": "Maintenance", "group": "Expense"},
            {"code": "5030", "name": "Supplies", "group": "Expense"},
            {"code": "5040", "name": "Salary", "group": "Expense"},
            {"code": "5050", "name": "Insurance", "group": "Expense"},
            {"code": "5060", "name": "Cleaning", "group": "Expense"},
        ]
        await db.coa.insert_many([{**c, "id": new_id(), "active": True, "created_at": now_iso()} for c in coa])

        # sample transactions for June 2026 on checking to populate the first report
        samples = [
            {"type": "expense", "date": "2026-06-03", "amount": 144.76, "payee": "Frontier Communications", "check_number": "4035", "category": "Utilities", "memo": "Internet/Phone Service"},
            {"type": "expense", "date": "2026-06-08", "amount": 69.10, "payee": "Hope Gas", "check_number": "4038", "category": "Utilities", "memo": "Gas Service"},
            {"type": "expense", "date": "2026-06-12", "amount": 124.07, "payee": "Appalachian Power (Church)", "check_number": "4045", "category": "Utilities", "memo": "Electric Service (Church)"},
            {"type": "expense", "date": "2026-06-15", "amount": 300.00, "payee": "CEF of Greater Huntington", "check_number": "4041", "category": "Donations / Missions", "memo": "Donation"},
            {"type": "expense", "date": "2026-06-20", "amount": 125.00, "payee": "Jodi Sovine Mowing", "check_number": "4044", "category": "Maintenance", "memo": "Mowing"},
            {"type": "income", "date": "2026-06-07", "amount": 1420.10, "category": "Deposit", "memo": "Sunday offering"},
            {"type": "income", "date": "2026-06-14", "amount": 1410.00, "category": "Deposit", "memo": "Sunday offering"},
            {"type": "income", "date": "2026-06-21", "amount": 1091.00, "category": "Deposit", "memo": "Sunday offering"},
            {"type": "income", "date": "2026-06-30", "amount": 34.64, "category": "Interest Paid", "memo": "Monthly interest"},
        ]
        docs = []
        for s in samples:
            docs.append({
                "id": new_id(), "type": s["type"], "date": s["date"], "account_id": acc_checking,
                "to_account_id": None, "amount": s["amount"],
                "payee_id": payee_by_name.get(s.get("payee")), "check_number": s.get("check_number", ""),
                "category_id": cat_by_name.get(s.get("category")), "fund_id": general_fund,
                "memo": s.get("memo", ""), "created_at": now_iso(), "created_by": "seed",
            })
        await db.transactions.insert_many(docs)
        logger.info("Seeded accounts, funds, categories, payees, COA, sample transactions")

    if not await db.settings.find_one({"id": "church"}):
        await db.settings.insert_one({
            "id": "church", "church_name": os.environ.get("CHURCH_NAME", "Providence Baptist Church"),
            "treasurer_name": "", "meeting_day": "",
        })


@app.on_event("startup")
async def startup():
    await seed()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
