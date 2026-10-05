from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query, UploadFile, File, Header, Form
from fastapi.responses import StreamingResponse, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
import csv
import json
import glob
import asyncio
import smtplib
from email.message import EmailMessage
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

# ----------------------------- Receipt storage (MongoDB GridFS — fully local) -----------------------------
import re

fs_bucket = AsyncIOMotorGridFSBucket(db, bucket_name="receipts")

BACKUP_DIR = os.environ.get("BACKUP_DIR") or str(ROOT_DIR / "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

ALLOWED_UPLOAD_TYPES = {
    "image/jpeg", "image/png", "image/heic", "image/heif", "image/webp", "application/pdf",
}
EXT_FOR_TYPE = {
    "image/jpeg": "jpg", "image/png": "png", "image/heic": "heic",
    "image/heif": "heif", "image/webp": "webp", "application/pdf": "pdf",
}


# ----------------------------- Permissions -----------------------------
ALL_PERMISSIONS = [
    "transactions.view",
    "transactions.manage",
    "reports.view",
    "settings.manage",
    "users.manage",
    "data.manage",
]
PERMISSION_LABELS = {
    "transactions.view": "View transactions, dashboard and balances",
    "transactions.manage": "Add, edit, delete, import transactions and reconcile",
    "reports.view": "View, print and export reports",
    "settings.manage": "Manage accounts, funds, categories, payees and chart of accounts",
    "users.manage": "Manage users and roles",
    "data.manage": "Back up and restore the database",
}

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


async def resolve_permissions(user: dict):
    if user.get("role") == "admin":
        return list(ALL_PERMISSIONS), "Administrator"
    role = None
    if user.get("role_id"):
        role = await db.roles.find_one({"id": user["role_id"]}, {"_id": 0})
    if role:
        return list(role.get("permissions", [])), role.get("name", "")
    return [], user.get("role", "")


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
    perms, role_name = await resolve_permissions(user)
    user["permissions"] = perms
    user["role_name"] = role_name
    return user


def require_permission(permission: str):
    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if permission not in user.get("permissions", []):
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return dependency


require_txn_view = require_permission("transactions.view")
require_txn_manage = require_permission("transactions.manage")
require_reports = require_permission("reports.view")
require_settings = require_permission("settings.manage")
require_users = require_permission("users.manage")
require_data = require_permission("data.manage")


def validate_strong_password(pw: str):
    if (
        len(pw) < 12
        or not re.search(r"[A-Z]", pw)
        or not re.search(r"[a-z]", pw)
        or not re.search(r"\d", pw)
        or not re.search(r"[^A-Za-z0-9]", pw)
    ):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 12 characters and include an uppercase letter, a lowercase letter, a number, and a symbol.",
        )


# ----------------------------- Models -----------------------------
class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role_id: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    password: Optional[str] = None


class SetupInput(BaseModel):
    name: str
    email: EmailStr
    password: str


class RoleInput(BaseModel):
    name: str
    permissions: List[str] = []


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
    cleared: bool = False


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


async def shape_user(user: dict):
    perms, role_name = await resolve_permissions(user)
    return {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "role": user.get("role", "user"), "role_id": user.get("role_id"),
        "role_name": role_name, "permissions": perms,
    }


# ----------------------------- Auth routes -----------------------------
@api_router.get("/auth/setup-status")
async def setup_status():
    count = await db.users.count_documents({})
    return {"needs_setup": count == 0}


@api_router.post("/auth/setup")
async def setup(data: SetupInput):
    if await db.users.count_documents({}) > 0:
        raise HTTPException(status_code=400, detail="Setup has already been completed")
    validate_strong_password(data.password)
    await seed_starter_data()
    admin_role = await db.roles.find_one({"name": "Administrator"})
    uid = new_id()
    doc = {
        "id": uid, "email": data.email.lower(), "name": data.name,
        "role": "admin", "role_id": admin_role["id"] if admin_role else None,
        "password_hash": hash_password(data.password), "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(uid, doc["email"])
    return {"token": token, "user": await shape_user(doc)}


@api_router.post("/auth/login")
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    return {"token": token, "user": await shape_user(user)}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api_router.get("/permissions")
async def list_permissions(user: dict = Depends(require_users)):
    return [{"key": k, "label": PERMISSION_LABELS[k]} for k in ALL_PERMISSIONS]


# ----------------------------- Roles -----------------------------
@api_router.get("/roles")
async def list_roles(user: dict = Depends(get_current_user)):
    roles = await db.roles.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    counts = {}
    async for u in db.users.find({}, {"_id": 0, "role_id": 1}):
        rid = u.get("role_id")
        if rid:
            counts[rid] = counts.get(rid, 0) + 1
    for r in roles:
        r["user_count"] = counts.get(r["id"], 0)
    return roles


@api_router.post("/roles")
async def create_role(data: RoleInput, user: dict = Depends(require_users)):
    perms = [p for p in data.permissions if p in ALL_PERMISSIONS]
    doc = {"id": new_id(), "name": data.name.strip(), "permissions": perms, "is_system": False, "created_at": now_iso()}
    await db.roles.insert_one(doc)
    return clean(doc)


@api_router.put("/roles/{role_id}")
async def update_role(role_id: str, data: RoleInput, user: dict = Depends(require_users)):
    role = await db.roles.find_one({"id": role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="The Administrator role cannot be modified")
    perms = [p for p in data.permissions if p in ALL_PERMISSIONS]
    await db.roles.update_one({"id": role_id}, {"$set": {"name": data.name.strip(), "permissions": perms}})
    return await db.roles.find_one({"id": role_id}, {"_id": 0})


@api_router.delete("/roles/{role_id}")
async def delete_role(role_id: str, user: dict = Depends(require_users)):
    role = await db.roles.find_one({"id": role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="The Administrator role cannot be deleted")
    if await db.users.count_documents({"role_id": role_id}) > 0:
        raise HTTPException(status_code=400, detail="This role is assigned to one or more users. Reassign them first.")
    await db.roles.delete_one({"id": role_id})
    return {"ok": True}


# ----------------------------- Users -----------------------------
@api_router.get("/auth/users")
async def list_users(user: dict = Depends(require_users)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    roles = {r["id"]: r["name"] for r in await db.roles.find({}, {"_id": 0}).to_list(1000)}
    for u in users:
        u["role_name"] = "Administrator" if u.get("role") == "admin" else roles.get(u.get("role_id"), "")
    return users


@api_router.post("/auth/users")
async def create_user(data: UserCreate, user: dict = Depends(require_users)):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    validate_strong_password(data.password)
    role = await db.roles.find_one({"id": data.role_id}) if data.role_id else None
    doc = {
        "id": new_id(),
        "email": data.email.lower(),
        "name": data.name,
        "role": "admin" if (role and role.get("is_system")) else "user",
        "role_id": data.role_id,
        "password_hash": hash_password(data.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return await shape_user(doc)


@api_router.put("/auth/users/{user_id}")
async def update_user(user_id: str, data: UserUpdate, user: dict = Depends(require_users)):
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    update = {}
    if data.name is not None:
        update["name"] = data.name
    if data.role_id is not None:
        if user_id == user["id"] and target.get("role") == "admin":
            raise HTTPException(status_code=400, detail="You cannot change your own administrator role")
        role = await db.roles.find_one({"id": data.role_id})
        update["role_id"] = data.role_id
        update["role"] = "admin" if (role and role.get("is_system")) else "user"
    if data.password:
        validate_strong_password(data.password)
        update["password_hash"] = hash_password(data.password)
    if update:
        await db.users.update_one({"id": user_id}, {"$set": update})
    updated = await db.users.find_one({"id": user_id})
    return await shape_user(updated)


@api_router.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_users)):
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
    async def create_item(data: model, user: dict = Depends(require_settings), _coll=collection):
        doc = data.model_dump()
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await db[_coll].insert_one(doc)
        return clean(doc)

    @api_router.put(f"/{path}/{{item_id}}")
    async def update_item(item_id: str, data: model, user: dict = Depends(require_settings), _coll=collection):
        existing = await db[_coll].find_one({"id": item_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        await db[_coll].update_one({"id": item_id}, {"$set": data.model_dump()})
        updated = await db[_coll].find_one({"id": item_id}, {"_id": 0})
        return updated

    @api_router.delete(f"/{path}/{{item_id}}")
    async def delete_item(item_id: str, user: dict = Depends(require_settings), _coll=collection):
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
    user: dict = Depends(require_txn_view),
    account_id: Optional[str] = None,
    fund_id: Optional[str] = None,
    category_id: Optional[str] = None,
    payee_id: Optional[str] = None,
    type: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    search: Optional[str] = None,
    cleared: Optional[bool] = None,
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
    if cleared is not None:
        query["cleared"] = cleared
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
    ids = [t["id"] for t in items]
    counts = {}
    if ids:
        async for f in db.files.find({"transaction_id": {"$in": ids}, "is_deleted": False}, {"_id": 0, "transaction_id": 1}):
            counts[f["transaction_id"]] = counts.get(f["transaction_id"], 0) + 1
    for t in items:
        t["attachment_count"] = counts.get(t["id"], 0)
    return items


@api_router.post("/transactions")
async def create_transaction(data: TransactionInput, user: dict = Depends(require_txn_manage)):
    if data.type == "transfer" and not data.to_account_id:
        raise HTTPException(status_code=400, detail="Transfer requires a destination account")
    doc = data.model_dump()
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.transactions.insert_one(doc)
    return clean(doc)


@api_router.put("/transactions/{txn_id}")
async def update_transaction(txn_id: str, data: TransactionInput, user: dict = Depends(require_txn_manage)):
    existing = await db.transactions.find_one({"id": txn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.transactions.update_one({"id": txn_id}, {"$set": data.model_dump()})
    updated = await db.transactions.find_one({"id": txn_id}, {"_id": 0})
    return updated


@api_router.delete("/transactions/{txn_id}")
async def delete_transaction(txn_id: str, user: dict = Depends(require_txn_manage)):
    await db.transactions.delete_one({"id": txn_id})
    await db.files.update_many({"transaction_id": txn_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


class ClearedInput(BaseModel):
    cleared: bool


@api_router.patch("/transactions/{txn_id}/cleared")
async def set_cleared(txn_id: str, data: ClearedInput, user: dict = Depends(require_txn_manage)):
    existing = await db.transactions.find_one({"id": txn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.transactions.update_one({"id": txn_id}, {"$set": {"cleared": data.cleared}})
    return {"ok": True, "cleared": data.cleared}


# ----------------------------- Reconciliation summary -----------------------------
@api_router.get("/accounts/{account_id}/reconcile")
async def reconcile_summary(account_id: str, user: dict = Depends(require_txn_view)):
    acc = await db.accounts.find_one({"id": account_id}, {"_id": 0})
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    current = await account_balance(acc)
    cleared_bal = float(acc.get("opening_balance", 0.0) or 0.0)
    uncleared_count = 0
    uncleared_total = 0.0
    query = {"$or": [{"account_id": account_id}, {"to_account_id": account_id}]}
    async for txn in db.transactions.find(query, {"_id": 0}):
        eff = await signed_amount_for_account(txn, account_id)
        if txn.get("cleared"):
            cleared_bal += eff
        else:
            uncleared_count += 1
            uncleared_total += eff
    return {
        "account_id": account_id,
        "current_balance": round(current, 2),
        "cleared_balance": round(cleared_bal, 2),
        "uncleared_count": uncleared_count,
        "uncleared_total": round(uncleared_total, 2),
    }


# ----------------------------- Receipt attachments -----------------------------
@api_router.post("/transactions/{txn_id}/attachments")
async def upload_attachment(txn_id: str, file: UploadFile = File(...), user: dict = Depends(require_txn_manage)):
    txn = await db.transactions.find_one({"id": txn_id})
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail="Only photos (JPG, PNG, HEIC, WEBP) and PDF files are allowed")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File is too large (max 15MB)")
    ext = EXT_FOR_TYPE.get(content_type, "bin")
    filename = file.filename or f"{new_id()}.{ext}"
    try:
        grid_id = await fs_bucket.upload_from_stream(filename, data, metadata={"content_type": content_type})
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=502, detail="Could not store the file. Please try again.")
    doc = {
        "id": new_id(),
        "transaction_id": txn_id,
        "gridfs_id": str(grid_id),
        "original_filename": file.filename,
        "content_type": content_type,
        "size": len(data),
        "is_deleted": False,
        "created_at": now_iso(),
    }
    await db.files.insert_one(doc)
    return clean(doc)


@api_router.get("/transactions/{txn_id}/attachments")
async def list_attachments(txn_id: str, user: dict = Depends(require_txn_view)):
    files = await db.files.find({"transaction_id": txn_id, "is_deleted": False}, {"_id": 0, "gridfs_id": 0}).to_list(100)
    return files


@api_router.get("/attachments/{file_id}/download")
async def download_attachment(file_id: str, request: Request, auth: Optional[str] = Query(None)):
    token = auth
    if not token:
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else None
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    record = await db.files.find_one({"id": file_id, "is_deleted": False})
    if not record or not record.get("gridfs_id"):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        stream = await fs_bucket.open_download_stream(ObjectId(record["gridfs_id"]))
        content = await stream.read()
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=content, media_type=record.get("content_type", "application/octet-stream"))


@api_router.delete("/attachments/{file_id}")
async def delete_attachment(file_id: str, user: dict = Depends(require_txn_manage)):
    record = await db.files.find_one({"id": file_id})
    await db.files.update_one({"id": file_id}, {"$set": {"is_deleted": True}})
    if record and record.get("gridfs_id"):
        try:
            await fs_bucket.delete(ObjectId(record["gridfs_id"]))
        except Exception:
            pass
    return {"ok": True}


# ----------------------------- CSV import -----------------------------
IMPORT_COLUMNS = ["Date", "Type", "Account", "To Account", "Amount", "Check#", "Payee", "Category", "Fund", "Memo"]


@api_router.get("/import/template")
async def import_template(user: dict = Depends(require_txn_manage)):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(IMPORT_COLUMNS)
    writer.writerow(["2026-06-07", "income", "*1234", "", "1420.10", "", "", "Deposit", "General Fund", "Sunday offering"])
    writer.writerow(["2026-06-03", "expense", "*1234", "", "144.76", "4035", "Frontier Communications", "Utilities", "General Fund", "Internet/Phone Service"])
    writer.writerow(["2026-06-15", "transfer", "*1234", "*5678", "500.00", "", "", "", "", "Move to savings"])
    out.seek(0)
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transaction-import-template.csv"},
    )


def parse_date(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


@api_router.post("/import/transactions")
async def import_transactions(file: UploadFile = File(...), user: dict = Depends(require_txn_manage)):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    accounts = await db.accounts.find({}, {"_id": 0}).to_list(1000)
    acc_lookup = {}
    for a in accounts:
        acc_lookup[a["mask"].lower().lstrip("*")] = a["id"]
        acc_lookup[a["name"].lower()] = a["id"]

    payees = {p["name"].lower(): p["id"] for p in await db.payees.find({}, {"_id": 0}).to_list(1000)}
    cats = {(c["name"].lower(), c["type"]): c["id"] for c in await db.categories.find({}, {"_id": 0}).to_list(1000)}
    funds = {f["name"].lower(): f["id"] for f in await db.funds.find({}, {"_id": 0}).to_list(1000)}

    created, errors = 0, []
    created_payees, created_cats, created_funds = 0, 0, 0
    docs = []

    def resolve_account(val):
        v = (val or "").strip().lower().lstrip("*")
        return acc_lookup.get(v)

    for i, row in enumerate(reader, start=2):
        ttype = (row.get("Type") or "").strip().lower()
        if ttype not in ("income", "expense", "transfer"):
            errors.append({"row": i, "reason": f"Invalid Type '{row.get('Type')}' (use income, expense, or transfer)"})
            continue
        d = parse_date(row.get("Date"))
        if not d:
            errors.append({"row": i, "reason": f"Invalid or missing Date '{row.get('Date')}'"})
            continue
        acc_id = resolve_account(row.get("Account"))
        if not acc_id:
            errors.append({"row": i, "reason": f"Account '{row.get('Account')}' not found — add it in Settings first"})
            continue
        try:
            amount = round(float((row.get("Amount") or "0").replace("$", "").replace(",", "").strip()), 2)
        except ValueError:
            errors.append({"row": i, "reason": f"Invalid Amount '{row.get('Amount')}'"})
            continue
        if amount <= 0:
            errors.append({"row": i, "reason": "Amount must be greater than zero"})
            continue

        to_acc_id = None
        if ttype == "transfer":
            to_acc_id = resolve_account(row.get("To Account"))
            if not to_acc_id:
                errors.append({"row": i, "reason": "Transfer requires a valid 'To Account'"})
                continue

        # payee (auto-create)
        payee_id = None
        pname = (row.get("Payee") or "").strip()
        if pname and ttype != "transfer":
            key = pname.lower()
            if key not in payees:
                pid = new_id()
                await db.payees.insert_one({"id": pid, "name": pname, "active": True, "created_at": now_iso()})
                payees[key] = pid
                created_payees += 1
            payee_id = payees[key]

        # category (auto-create)
        category_id = None
        cname = (row.get("Category") or "").strip()
        if cname and ttype != "transfer":
            ctype = "income" if ttype == "income" else "expense"
            key = (cname.lower(), ctype)
            if key not in cats:
                cid = new_id()
                await db.categories.insert_one({"id": cid, "name": cname, "type": ctype, "active": True, "created_at": now_iso()})
                cats[key] = cid
                created_cats += 1
            category_id = cats[key]

        # fund (auto-create)
        fund_id = None
        fname = (row.get("Fund") or "").strip()
        if fname:
            key = fname.lower()
            if key not in funds:
                fid = new_id()
                await db.funds.insert_one({"id": fid, "name": fname, "description": "", "active": True, "created_at": now_iso()})
                funds[key] = fid
                created_funds += 1
            fund_id = funds[key]

        docs.append({
            "id": new_id(), "type": ttype, "date": d, "account_id": acc_id,
            "to_account_id": to_acc_id, "amount": amount,
            "payee_id": payee_id, "check_number": (row.get("Check#") or "").strip(),
            "category_id": category_id, "fund_id": fund_id,
            "memo": (row.get("Memo") or "").strip(), "cleared": False,
            "created_at": now_iso(), "created_by": user["id"],
        })
        created += 1

    if docs:
        await db.transactions.insert_many(docs)

    return {
        "created": created,
        "errors": errors,
        "created_payees": created_payees,
        "created_categories": created_cats,
        "created_funds": created_funds,
    }


# ----------------------------- Dashboard -----------------------------
@api_router.get("/dashboard")
async def dashboard(user: dict = Depends(require_txn_view)):
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
    user: dict = Depends(require_reports),
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
    user: dict = Depends(require_reports),
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
async def update_church(data: ChurchSettings, user: dict = Depends(require_settings)):
    doc = {"id": "church", **data.model_dump()}
    await db.settings.update_one({"id": "church"}, {"$set": doc}, upsert=True)
    return doc


# ----------------------------- Data backup / restore -----------------------------
EXPORT_COLLECTIONS = ["users", "roles", "accounts", "funds", "categories", "payees", "coa", "transactions", "files", "settings"]


async def build_export_payload() -> dict:
    payload = {"version": 1, "app": "church-treasury", "exported_at": now_iso(), "data": {}}
    for coll in EXPORT_COLLECTIONS:
        docs = await db[coll].find({}, {"_id": 0}).to_list(100000)
        payload["data"][coll] = docs
    return payload


@api_router.get("/data/export")
async def export_data(user: dict = Depends(require_data)):
    payload = await build_export_payload()
    body = json.dumps(payload, indent=2)
    filename = f"church-treasury-backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api_router.post("/data/import")
async def import_data(file: UploadFile = File(...), user: dict = Depends(require_data)):
    import json as _json
    try:
        payload = _json.loads((await file.read()).decode("utf-8-sig", errors="replace"))
    except Exception:
        raise HTTPException(status_code=400, detail="This file is not a valid backup (JSON could not be read)")
    data = payload.get("data")
    if not isinstance(data, dict) or "users" not in data:
        raise HTTPException(status_code=400, detail="This does not look like a Church Treasury backup file")
    if not isinstance(data.get("users"), list) or len(data["users"]) == 0:
        raise HTTPException(status_code=400, detail="The backup has no users — restoring it would lock you out")

    counts = {}
    for coll in EXPORT_COLLECTIONS:
        docs = data.get(coll)
        if not isinstance(docs, list):
            continue
        await db[coll].delete_many({})
        if docs:
            for d in docs:
                d.pop("_id", None)
            await db[coll].insert_many(docs)
        counts[coll] = len(docs)
    return {"ok": True, "restored": counts}


# ----------------------------- Scheduled backups -----------------------------
BACKUP_PREFIX = "church-treasury-backup-"
DEFAULT_BACKUP_SETTINGS = {"id": "backup", "enabled": True, "time": "02:00", "retention": 14}
scheduler = AsyncIOScheduler()


class BackupSettings(BaseModel):
    enabled: bool = True
    time: str = "02:00"
    retention: int = 14


def _safe_backup_name(name: str) -> str:
    base = os.path.basename(name)
    if not base.startswith(BACKUP_PREFIX) or not base.endswith(".json") or "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid backup file name")
    return base


async def get_backup_settings() -> dict:
    doc = await db.settings.find_one({"id": "backup"}, {"_id": 0})
    if not doc:
        doc = dict(DEFAULT_BACKUP_SETTINGS)
        await db.settings.update_one({"id": "backup"}, {"$set": doc}, upsert=True)
    return doc


def apply_retention(retention: int):
    try:
        files = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{BACKUP_PREFIX}*.json")))
        if retention and len(files) > retention:
            for old in files[: len(files) - retention]:
                try:
                    os.remove(old)
                except OSError:
                    pass
    except Exception as e:
        logger.error(f"Retention cleanup failed: {e}")


async def run_backup() -> str:
    payload = await build_export_payload()
    fname = f"{BACKUP_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    full = os.path.join(BACKUP_DIR, fname)
    with open(full, "w") as f:
        json.dump(payload, f, indent=2)
    cfg = await get_backup_settings()
    apply_retention(int(cfg.get("retention", 14)))
    logger.info(f"Backup written: {fname}")
    return fname


async def scheduled_backup_job():
    cfg = await get_backup_settings()
    if cfg.get("enabled", True):
        fname = await run_backup()
        await maybe_email_backup(fname)


async def reschedule_backup():
    cfg = await get_backup_settings()
    try:
        scheduler.remove_job("nightly_backup")
    except Exception:
        pass
    if cfg.get("enabled", True):
        hh, mm = (cfg.get("time") or "02:00").split(":")
        scheduler.add_job(scheduled_backup_job, "cron", hour=int(hh), minute=int(mm), id="nightly_backup", replace_existing=True)


@api_router.get("/settings/backup")
async def get_backup_config(user: dict = Depends(require_data)):
    cfg = await get_backup_settings()
    cfg["backup_dir"] = BACKUP_DIR
    return cfg


@api_router.put("/settings/backup")
async def update_backup_config(data: BackupSettings, user: dict = Depends(require_data)):
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", data.time):
        raise HTTPException(status_code=400, detail="Time must be in 24-hour HH:MM format")
    doc = {"id": "backup", "enabled": data.enabled, "time": data.time, "retention": max(1, int(data.retention))}
    await db.settings.update_one({"id": "backup"}, {"$set": doc}, upsert=True)
    await reschedule_backup()
    return doc


@api_router.get("/backups")
async def list_backups(user: dict = Depends(require_data)):
    out = []
    for path in sorted(glob.glob(os.path.join(BACKUP_DIR, f"{BACKUP_PREFIX}*.json")), reverse=True):
        st = os.stat(path)
        out.append({
            "name": os.path.basename(path),
            "size": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        })
    return out


@api_router.post("/backups/run")
async def run_backup_now(user: dict = Depends(require_data)):
    name = await run_backup()
    return {"ok": True, "name": name}


@api_router.get("/backups/{name}/download")
async def download_backup(name: str, request: Request, auth: Optional[str] = Query(None)):
    token = auth or (request.headers.get("Authorization", "")[7:] if request.headers.get("Authorization", "").startswith("Bearer ") else None)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    base = _safe_backup_name(name)
    full = os.path.join(BACKUP_DIR, base)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Backup not found")
    with open(full, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={base}"})


@api_router.delete("/backups/{name}")
async def delete_backup(name: str, user: dict = Depends(require_data)):
    base = _safe_backup_name(name)
    full = os.path.join(BACKUP_DIR, base)
    if os.path.exists(full):
        os.remove(full)
    return {"ok": True}


@api_router.post("/backups/{name}/restore")
async def restore_backup(name: str, user: dict = Depends(require_data)):
    base = _safe_backup_name(name)
    full = os.path.join(BACKUP_DIR, base)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Backup not found")
    with open(full) as f:
        payload = json.load(f)
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("users"), list) or len(data["users"]) == 0:
        raise HTTPException(status_code=400, detail="This backup is invalid or has no users")
    counts = {}
    for coll in EXPORT_COLLECTIONS:
        docs = data.get(coll)
        if not isinstance(docs, list):
            continue
        await db[coll].delete_many({})
        if docs:
            for d in docs:
                d.pop("_id", None)
            await db[coll].insert_many(docs)
        counts[coll] = len(docs)
    return {"ok": True, "restored": counts}


# ----------------------------- Email backups (SMTP) -----------------------------
DEFAULT_EMAIL_SETTINGS = {
    "id": "email", "enabled": False, "smtp_host": "", "smtp_port": 587,
    "smtp_username": "", "smtp_password": "", "use_tls": True,
    "from_address": "", "to_address": "",
}


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: Optional[str] = None  # None/omitted = keep existing
    use_tls: bool = True
    from_address: str = ""
    to_address: str = ""


async def get_email_settings() -> dict:
    doc = await db.settings.find_one({"id": "email"}, {"_id": 0})
    if not doc:
        doc = dict(DEFAULT_EMAIL_SETTINGS)
        await db.settings.update_one({"id": "email"}, {"$set": doc}, upsert=True)
    return doc


def _send_email_sync(cfg: dict, subject: str, body: str, att_name=None, att_bytes=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_address") or cfg.get("smtp_username")
    msg["To"] = cfg.get("to_address")
    msg.set_content(body)
    if att_bytes is not None:
        msg.add_attachment(att_bytes, maintype="application", subtype="json", filename=att_name)
    host = cfg.get("smtp_host")
    port = int(cfg.get("smtp_port") or 587)
    username = cfg.get("smtp_username") or ""
    password = cfg.get("smtp_password") or ""
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            if username:
                s.login(username, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            if cfg.get("use_tls", True):
                s.starttls()
            if username:
                s.login(username, password)
            s.send_message(msg)


async def maybe_email_backup(fname: str):
    cfg = await get_email_settings()
    if not cfg.get("enabled") or not cfg.get("smtp_host") or not cfg.get("to_address"):
        return
    try:
        full = os.path.join(BACKUP_DIR, fname)
        with open(full, "rb") as f:
            data = f.read()
        church = await db.settings.find_one({"id": "church"}, {"_id": 0}) or {}
        name = church.get("church_name") or "Church Treasury"
        await asyncio.to_thread(
            _send_email_sync, cfg,
            f"{name} — Treasury backup {fname}",
            f"Attached is the automatic database backup from {name}.\n\nFile: {fname}\nKeep this somewhere safe for off-site safekeeping.",
            fname, data,
        )
        logger.info(f"Backup emailed to {cfg['to_address']}")
    except Exception as e:
        logger.error(f"Backup email failed: {e}")


@api_router.get("/settings/email")
async def get_email_config(user: dict = Depends(require_data)):
    cfg = await get_email_settings()
    return {
        "enabled": cfg.get("enabled", False),
        "smtp_host": cfg.get("smtp_host", ""),
        "smtp_port": cfg.get("smtp_port", 587),
        "smtp_username": cfg.get("smtp_username", ""),
        "use_tls": cfg.get("use_tls", True),
        "from_address": cfg.get("from_address", ""),
        "to_address": cfg.get("to_address", ""),
        "has_password": bool(cfg.get("smtp_password")),
    }


@api_router.put("/settings/email")
async def update_email_config(data: EmailConfig, user: dict = Depends(require_data)):
    existing = await get_email_settings()
    doc = {
        "id": "email",
        "enabled": data.enabled,
        "smtp_host": data.smtp_host.strip(),
        "smtp_port": int(data.smtp_port or 587),
        "smtp_username": data.smtp_username.strip(),
        "use_tls": data.use_tls,
        "from_address": data.from_address.strip(),
        "to_address": data.to_address.strip(),
        "smtp_password": existing.get("smtp_password", "") if data.smtp_password in (None, "") else data.smtp_password,
    }
    await db.settings.update_one({"id": "email"}, {"$set": doc}, upsert=True)
    return {"ok": True}


@api_router.post("/email/test")
async def send_test_email(user: dict = Depends(require_data)):
    cfg = await get_email_settings()
    if not cfg.get("smtp_host") or not cfg.get("to_address"):
        raise HTTPException(status_code=400, detail="Please set at least an SMTP host and a recipient address, then save.")
    try:
        await asyncio.to_thread(
            _send_email_sync, cfg,
            "Grace Treasury — test email",
            "This is a test email from your Grace Treasury app. If you received this, backup emailing is configured correctly.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not send email: {e}")
    return {"ok": True}


@api_router.post("/backups/{name}/email")
async def email_backup(name: str, user: dict = Depends(require_data)):
    base = _safe_backup_name(name)
    if not os.path.exists(os.path.join(BACKUP_DIR, base)):
        raise HTTPException(status_code=404, detail="Backup not found")
    cfg = await get_email_settings()
    if not cfg.get("smtp_host") or not cfg.get("to_address"):
        raise HTTPException(status_code=400, detail="Email is not configured. Set it up under Email Backups first.")
    try:
        await maybe_email_backup_force(base, cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not send email: {e}")
    return {"ok": True}


async def maybe_email_backup_force(fname: str, cfg: dict):
    full = os.path.join(BACKUP_DIR, fname)
    with open(full, "rb") as f:
        data = f.read()
    church = await db.settings.find_one({"id": "church"}, {"_id": 0}) or {}
    name = church.get("church_name") or "Church Treasury"
    await asyncio.to_thread(
        _send_email_sync, cfg,
        f"{name} — Treasury backup {fname}",
        f"Attached is a database backup from {name}.\n\nFile: {fname}",
        fname, data,
    )


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
async def ensure_indexes():
    await db.users.create_index("email", unique=True)


async def seed_starter_data():
    """Create generic, church-agnostic starter data on first setup.
    No bank accounts, payees, or transactions are created."""
    # Roles
    if await db.roles.count_documents({}) == 0:
        await db.roles.insert_many([
            {"id": new_id(), "name": "Administrator", "permissions": list(ALL_PERMISSIONS), "is_system": True, "created_at": now_iso()},
            {"id": new_id(), "name": "Bookkeeper", "permissions": ["transactions.view", "transactions.manage", "reports.view"], "is_system": False, "created_at": now_iso()},
            {"id": new_id(), "name": "Viewer", "permissions": ["transactions.view", "reports.view"], "is_system": False, "created_at": now_iso()},
        ])

    # Generic funds
    if await db.funds.count_documents({}) == 0:
        await db.funds.insert_one({"id": new_id(), "name": "General Fund", "description": "Day-to-day operating fund", "active": True, "created_at": now_iso()})

    # Generic categories
    if await db.categories.count_documents({}) == 0:
        income_cats = ["Tithes & Offerings", "Deposit", "Interest Paid", "Designated Gift"]
        expense_cats = ["Utilities", "Missions & Donations", "Maintenance", "Supplies", "Salary", "Insurance", "Cleaning", "Literature"]
        cats = [{"id": new_id(), "name": n, "type": "income", "active": True, "created_at": now_iso()} for n in income_cats]
        cats += [{"id": new_id(), "name": n, "type": "expense", "active": True, "created_at": now_iso()} for n in expense_cats]
        await db.categories.insert_many(cats)

    # Generic chart of accounts (no specific bank accounts)
    if await db.coa.count_documents({}) == 0:
        coa = [
            {"code": "1000", "name": "Checking Account", "group": "Asset"},
            {"code": "1010", "name": "Savings Account", "group": "Asset"},
            {"code": "2000", "name": "Accounts Payable", "group": "Liability"},
            {"code": "3000", "name": "General Fund Balance", "group": "Equity"},
            {"code": "4000", "name": "Tithes & Offerings", "group": "Income"},
            {"code": "4010", "name": "Deposit", "group": "Income"},
            {"code": "4020", "name": "Interest Paid", "group": "Income"},
            {"code": "5000", "name": "Utilities", "group": "Expense"},
            {"code": "5010", "name": "Missions & Donations", "group": "Expense"},
            {"code": "5020", "name": "Maintenance", "group": "Expense"},
            {"code": "5030", "name": "Supplies", "group": "Expense"},
            {"code": "5040", "name": "Salary", "group": "Expense"},
            {"code": "5050", "name": "Insurance", "group": "Expense"},
        ]
        await db.coa.insert_many([{**c, "id": new_id(), "active": True, "created_at": now_iso()} for c in coa])

    # Church settings (blank, editable by the treasurer)
    if not await db.settings.find_one({"id": "church"}):
        await db.settings.insert_one({"id": "church", "church_name": "Your Church Name", "treasurer_name": "", "meeting_day": ""})


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    try:
        await get_backup_settings()
        await reschedule_backup()
        if not scheduler.running:
            scheduler.start()
        logger.info("Backup scheduler started")
    except Exception as e:
        logger.error(f"Backup scheduler failed to start: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
