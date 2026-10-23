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
from contextlib import asynccontextmanager
import csv
import json
import glob
import asyncio
import smtplib
import socket
import ssl
from email.message import EmailMessage
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
import io
import bcrypt
import jwt
import base64
import secrets
import hmac
from pymongo.errors import DuplicateKeyError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from datetime import datetime, timezone, timedelta, date

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = "HS256"

# ----------------------------- Receipt storage (MongoDB GridFS — fully local) -----------------------------
import re
from xml.sax.saxutils import escape as xml_escape

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


# ----------------------------- Expense payment methods -----------------------------
# How an expense left the bank account. Only "check" uses a check number.
PAYMENT_METHODS = {
    "check": "Check",
    "debit": "Debit Card",
    "credit": "Credit Card",
    "ach": "ACH / Bank Draft",
    "online": "Online Payment",
    "wire": "Wire Transfer",
    "cash": "Cash",
    "other": "Other",
}
PAYMENT_METHOD_ALIASES = {
    "chk": "check", "cheque": "check", "debit card": "debit", "credit card": "credit",
    "ach / bank draft": "ach", "bank draft": "ach", "draft": "ach", "eft": "ach",
    "online payment": "online", "wire transfer": "wire",
}


def normalize_payment_method(value: Optional[str]) -> str:
    """Map a label or alias (e.g. 'Debit Card', 'chk') to a PAYMENT_METHODS key; '' if unknown/blank."""
    v = (value or "").strip().lower()
    if v in PAYMENT_METHODS:
        return v
    if v in PAYMENT_METHOD_ALIASES:
        return PAYMENT_METHOD_ALIASES[v]
    for key, label in PAYMENT_METHODS.items():
        if v == label.lower():
            return key
    return ""


def effective_payment_method(txn: dict) -> str:
    """Payment method for an expense; older entries without one are treated as checks if they carry a check number."""
    if txn.get("type") != "expense":
        return ""
    pm = txn.get("payment_method") or ""
    if not pm and (txn.get("check_number") or "").strip():
        pm = "check"
    return pm


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
    "settings.manage": "Manage accounts, funds, categories and payees",
    "users.manage": "Manage users and roles (Administrators only)",
    "data.manage": "Back up and restore the database (Administrators only)",
}

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await startup()
    yield
    await shutdown()


app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ----------------------------- Auth helpers -----------------------------
BCRYPT_MAX_BYTES = 72  # bcrypt only uses the first 72 bytes of a password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # Older bcrypt versions silently used only the first 72 bytes; do the same so existing
    # long passwords keep working (bcrypt 5 raises an error instead).
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:BCRYPT_MAX_BYTES], hashed.encode("utf-8"))
    except Exception:
        return False


# Sessions: a token lasts SESSION_IDLE_HOURS. While the person is active, responses carry a
# fresh token (X-Session-Token) about once an hour, so an idle or stolen token expires soon.
# No session can be renewed past SESSION_MAX_DAYS after the password was last entered.
SESSION_IDLE = timedelta(hours=float(os.environ.get("SESSION_IDLE_HOURS", "12") or 12))
SESSION_MAX = timedelta(days=float(os.environ.get("SESSION_MAX_DAYS", "7") or 7))
SESSION_REFRESH_AFTER = timedelta(hours=1)
SESSION_HEADER = "X-Session-Token"


def create_access_token(user_id: str, email: str, version: int = 0, auth_time: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    auth_time = int(auth_time if auth_time is not None else now.timestamp())
    payload = {
        "sub": user_id,
        "email": email,
        "ver": int(version or 0),  # session version; bumping it on the user signs out older tokens
        "iat": int(now.timestamp()),
        "auth_time": auth_time,    # when the password was last entered
        "exp": min(now + SESSION_IDLE, datetime.fromtimestamp(auth_time, timezone.utc) + SESSION_MAX),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _session_times(payload: dict) -> tuple:
    """(issued_at, auth_time) as epoch seconds; older 7-day tokens had neither."""
    iat = payload.get("iat")
    if iat is None:
        iat = int(payload.get("exp", 0)) - 7 * 86400
    return int(iat), int(payload.get("auth_time") or iat)


# Permissions that only Administrators hold; custom roles can never include them.
ADMIN_ONLY_PERMISSIONS = {"users.manage", "data.manage"}
ASSIGNABLE_PERMISSIONS = [p for p in ALL_PERMISSIONS if p not in ADMIN_ONLY_PERMISSIONS]


async def resolve_permissions(user: dict):
    if user.get("role") == "admin":
        return list(ALL_PERMISSIONS), "Administrator"
    role = None
    if user.get("role_id"):
        role = await db.roles.find_one({"id": user["role_id"]}, {"_id": 0})
    if role:
        perms = [p for p in role.get("permissions", []) if p not in ADMIN_ONLY_PERMISSIONS]
        return perms, role.get("name", "")
    return [], user.get("role", "")


# While a user must choose a new password, only these endpoints work for them.
PASSWORD_CHANGE_ALLOWED_PATHS = {"/api/auth/me", "/api/auth/change-password", "/api/settings/church"}


async def get_current_user(request: Request, response: Response) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None
    user = await user_from_token(token)
    sess = user["_session"]
    now = datetime.now(timezone.utc).timestamp()
    if now - sess["iat"] > SESSION_REFRESH_AFTER.total_seconds():
        # Active session: hand back a fresh token (same login time, so the 7-day cap still applies).
        response.headers[SESSION_HEADER] = create_access_token(user["id"], user["email"], sess["ver"], sess["auth_time"])
    if user.get("must_change_password") and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise HTTPException(status_code=403, detail="Please choose a new password before continuing.")
    return user


async def user_from_token(token: Optional[str]) -> dict:
    """Validate a JWT and load the user with resolved permissions."""
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
    if int(payload.get("ver", 0) or 0) != int(user.get("token_version", 0) or 0):
        raise HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    iat, auth_time = _session_times(payload)
    if datetime.now(timezone.utc).timestamp() - auth_time > SESSION_MAX.total_seconds():
        raise HTTPException(status_code=401, detail="For your security, please sign in again.")
    user["_session"] = {"iat": iat, "auth_time": auth_time, "ver": int(payload.get("ver", 0) or 0)}
    user.pop("token_version", None)
    perms, role_name = await resolve_permissions(user)
    user["permissions"] = perms
    user["role_name"] = role_name
    return user


def public_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if not k.startswith("_")}


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
async def require_users(user: dict = Depends(get_current_user)) -> dict:
    """Managing users and roles is reserved for Administrators."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only an administrator can manage users and roles")
    return user
require_data = require_permission("data.manage")


# Headers for anything containing church data: don't let browsers or proxies keep a copy,
# and don't let a browser reinterpret a file as a different (e.g. HTML) type.
PRIVATE_DOWNLOAD_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def private_download_headers(filename: Optional[str] = None, inline: bool = False) -> dict:
    headers = dict(PRIVATE_DOWNLOAD_HEADERS)
    if filename:
        safe = re.sub(r'[^A-Za-z0-9._-]', "_", filename)[:150] or "download"
        headers["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{safe}"'
    return headers


def is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Only an administrator can perform this action")
    return user


async def revoke_sessions(user_id: str) -> int:
    """Sign a user out everywhere by bumping their session version. Returns the new version."""
    await db.users.update_one({"id": user_id}, {"$inc": {"token_version": 1}})
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "token_version": 1})
    return int((doc or {}).get("token_version", 0) or 0)


async def audit(actor: Optional[dict], action: str, target: Optional[dict] = None, details: str = "", request: Optional[Request] = None):
    """Append to the security audit log (user, role and sign-in management)."""
    try:
        await db.audit_log.insert_one({
            "id": new_id(), "at": now_iso(), "action": action,
            "actor_id": (actor or {}).get("id"), "actor_email": (actor or {}).get("email", "") if actor else "System",
            "target_id": (target or {}).get("id"), "target_email": (target or {}).get("email") or (target or {}).get("name", ""),
            "details": details[:500], "ip": client_ip(request) if request else "",
        })
    except Exception as e:  # auditing must never break the action itself
        logger.error(f"Audit write failed: {e}")


def ensure_can_grant(actor: dict, permissions: List[str]):
    """Non-admins may only grant permissions they themselves hold (prevents privilege escalation)."""
    if is_admin(actor):
        return
    extra = set(permissions) - set(actor.get("permissions", []))
    if extra:
        raise HTTPException(status_code=403, detail="You cannot grant permissions you do not have yourself")


async def ensure_can_manage_user(actor: dict, target: dict):
    """Non-admins may only change, reset, sign out or delete users whose permissions
    they fully hold themselves — never someone more privileged."""
    if is_admin(actor):
        return
    if target.get("role") == "admin":
        raise HTTPException(status_code=403, detail="Only an administrator can manage an administrator account")
    target_perms, _ = await resolve_permissions(target)
    if set(target_perms) - set(actor.get("permissions", [])):
        raise HTTPException(status_code=403, detail="You can't manage a user who has permissions you don't have")


async def ensure_can_assign_role(actor: dict, role_id: Optional[str]):
    if is_admin(actor) or not role_id:
        return
    role = await db.roles.find_one({"id": role_id})
    if not role:
        raise HTTPException(status_code=400, detail="Role not found")
    if role.get("is_system"):
        raise HTTPException(status_code=403, detail="Only an administrator can assign the Administrator role")
    ensure_can_grant(actor, role.get("permissions", []))


def validate_strong_password(pw: str):
    if len(pw.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise HTTPException(status_code=400, detail=f"Password must be {BCRYPT_MAX_BYTES} characters or fewer.")
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


class PasswordChangeInput(BaseModel):
    current_password: str
    new_password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    password: Optional[str] = None


class SetupInput(BaseModel):
    name: str
    email: EmailStr
    password: str
    setup_code: str = ""


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
    opening_balance: float = 0.0
    opening_date: str = ""
    parent_id: Optional[str] = None
    active: bool = True


class CategoryInput(BaseModel):
    name: str
    type: str = "expense"  # income | expense
    active: bool = True


class PayeeInput(BaseModel):
    name: str
    active: bool = True


class FundSplit(BaseModel):
    fund_id: str
    amount: float


class TransactionInput(BaseModel):
    type: str  # income | expense | transfer
    date: str  # YYYY-MM-DD
    account_id: str
    to_account_id: Optional[str] = None
    amount: float
    payee_id: Optional[str] = None
    payment_method: Optional[str] = ""  # expenses only — see PAYMENT_METHODS
    check_number: Optional[str] = ""
    category_id: Optional[str] = None
    fund_id: Optional[str] = None
    fund_splits: Optional[List[FundSplit]] = None
    memo: Optional[str] = ""
    cleared: bool = False


class FundActivityInput(BaseModel):
    type: str  # move | adjust
    date: str  # YYYY-MM-DD
    amount: float
    from_fund_id: Optional[str] = None
    to_fund_id: Optional[str] = None
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
    query = {"$or": [{"account_id": account["id"]}, {"to_account_id": account["id"]}], "voided": {"$ne": True}}
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
        "voided": {"$ne": True},
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
        "must_change_password": bool(user.get("must_change_password")),
    }


# ----------------------------- Login throttling -----------------------------
# Failed sign-ins are tracked per (email, IP) and per IP. Locking the email+IP pair
# (rather than the email alone) stops guessing without letting a stranger lock out
# a real user from their own computer.
LOGIN_WINDOW = timedelta(minutes=15)       # failures counted within this window
LOGIN_LOCK = timedelta(minutes=15)         # lock lasts this long after the last failure
MAX_FAILS_PER_ACCOUNT_IP = 5
MAX_FAILS_PER_IP = 20
LOGIN_HISTORY_DAYS = 30                    # attempts older than this are auto-deleted
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode("utf-8")


def _utcnow() -> datetime:
    # MongoDB returns naive UTC datetimes, so compare in naive UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def client_ip(request: Request) -> str:
    """Real visitor IP. nginx sets X-Real-IP (from Cloudflare's CF-Connecting-IP when the
    request came through the trusted tunnel). The backend is only reachable through nginx."""
    ip = (request.headers.get("x-real-ip") or "").strip()
    if not ip and request.client:
        ip = request.client.host
    return ip[:64] or "unknown"


def _fail_query(**extra) -> dict:
    return {"success": False, "cleared": {"$ne": True}, **extra}


async def login_lock_seconds(email: str, ip: str) -> int:
    """Seconds until this email+IP (or this IP) may try again; 0 if not locked."""
    now = _utcnow()
    since = now - LOGIN_WINDOW
    until = None
    pair = await db.login_attempts.find(
        _fail_query(email=email, ip=ip, at={"$gte": since}), {"_id": 0, "at": 1}
    ).sort("at", -1).to_list(MAX_FAILS_PER_ACCOUNT_IP)
    if len(pair) >= MAX_FAILS_PER_ACCOUNT_IP:
        until = _naive_utc(pair[0]["at"]) + LOGIN_LOCK
    if await db.login_attempts.count_documents(_fail_query(ip=ip, at={"$gte": since})) >= MAX_FAILS_PER_IP:
        last = await db.login_attempts.find_one(_fail_query(ip=ip), {"_id": 0, "at": 1}, sort=[("at", -1)])
        ip_until = _naive_utc(last["at"]) + LOGIN_LOCK
        until = max(until, ip_until) if until else ip_until
    if not until or until <= now:
        return 0
    return int((until - now).total_seconds()) + 1


async def record_login_attempt(email: str, ip: str, success: bool, user_agent: str = ""):
    await db.login_attempts.insert_one({
        "email": email, "ip": ip, "success": success, "at": _utcnow(), "user_agent": user_agent[:200],
    })
    if success:
        # a good sign-in resets the counter for this email from this IP
        await db.login_attempts.update_many(_fail_query(email=email, ip=ip), {"$set": {"cleared": True}})


# ----------------------------- Auth routes -----------------------------
@api_router.get("/auth/setup-status")
async def setup_status():
    count = await db.users.count_documents({})
    if count == 0:
        current_setup_code()  # make sure a code exists (and is logged) before anyone is asked for it
    return {"needs_setup": count == 0, "requires_code": True}


# ----------------------------- First-run setup code -----------------------------
# Until the first Administrator exists, setup requires a one-time code so a stranger who
# reaches a fresh install can't claim it. install.sh puts SETUP_CODE in .env and shows it;
# if none is set, the backend makes one and prints it in its log.
_SETUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I
_generated_setup_code: Optional[str] = None


def _normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def current_setup_code() -> str:
    global _generated_setup_code
    env_code = _normalize_code(os.environ.get("SETUP_CODE", ""))
    if env_code:
        return env_code
    if not _generated_setup_code:
        raw = "".join(secrets.choice(_SETUP_ALPHABET) for _ in range(16))
        _generated_setup_code = raw
        pretty = "-".join(raw[i:i + 4] for i in range(0, 16, 4))
        logger.warning("=" * 64)
        logger.warning(f"  Grace Treasury setup code: {pretty}")
        logger.warning("  Enter it on the setup page to create the first Administrator.")
        logger.warning("=" * 64)
    return _generated_setup_code


async def claim_first_setup() -> None:
    """Atomically claim first-run setup; only one request can ever win (MongoDB _id is unique)."""
    try:
        await db.setup_claim.insert_one({"_id": "first-admin", "at": _utcnow()})
    except DuplicateKeyError:
        # A crashed attempt can leave a claim with no admin; let it expire after two minutes.
        claim = await db.setup_claim.find_one({"_id": "first-admin"})
        stale = claim and (_utcnow() - _naive_utc(claim["at"])).total_seconds() > 120
        if stale and await db.users.count_documents({}) == 0:
            await db.setup_claim.delete_one({"_id": "first-admin", "at": claim["at"]})
            return await claim_first_setup()
        raise HTTPException(status_code=400, detail="Setup has already been completed")


@api_router.post("/auth/setup")
async def setup(data: SetupInput, request: Request):
    if await db.users.count_documents({}) > 0:
        raise HTTPException(status_code=400, detail="Setup has already been completed")
    ip = client_ip(request)
    wait = await login_lock_seconds("__setup__", ip)
    if wait:
        raise HTTPException(status_code=429, detail="Too many wrong setup codes. Please wait and try again.",
                            headers={"Retry-After": str(wait)})
    if not hmac.compare_digest(_normalize_code(data.setup_code), current_setup_code()):
        await record_login_attempt("__setup__", ip, False, request.headers.get("user-agent", ""))
        logger.warning(f"Setup attempt with a wrong setup code from {ip}")
        raise HTTPException(status_code=403, detail="That setup code isn't right. It was shown when Grace Treasury was "
                                                    "installed, and is saved as SETUP_CODE in the .env file.")
    validate_strong_password(data.password)
    await claim_first_setup()
    try:
        await seed_starter_data()
        admin_role = await db.roles.find_one({"name": "Administrator"})
        uid = new_id()
        doc = {
            "id": uid, "email": data.email.lower(), "name": data.name,
            "role": "admin", "role_id": admin_role["id"] if admin_role else None,
            "password_hash": hash_password(data.password), "created_at": now_iso(),
        }
        await db.users.insert_one(doc)
    except Exception:
        await db.setup_claim.delete_one({"_id": "first-admin"})  # let setup be retried
        raise
    token = create_access_token(uid, doc["email"])
    await audit(doc, "setup.admin_created", doc, f"from {ip}", request)
    return {"token": token, "user": await shape_user(doc)}


@api_router.post("/auth/login")
async def login(data: LoginInput, request: Request):
    email = data.email.lower()
    ip = client_ip(request)
    wait = await login_lock_seconds(email, ip)
    if wait:
        minutes = max(1, -(-wait // 60))
        logger.warning(f"Login blocked (locked out): email={email} ip={ip}")
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed sign-in attempts. Please wait {minutes} minute{'s' if minutes != 1 else ''} and try again.",
            headers={"Retry-After": str(wait)},
        )
    user = await db.users.find_one({"email": email})
    # always run bcrypt so response time doesn't reveal whether the email exists
    ok = verify_password(data.password, user["password_hash"] if user else _DUMMY_HASH) and bool(user)
    await record_login_attempt(email, ip, ok, request.headers.get("user-agent", ""))
    if not ok:
        logger.warning(f"Failed login: email={email} ip={ip}")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"], user.get("token_version", 0))
    return {"token": token, "user": await shape_user(user)}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api_router.post("/auth/change-password")
async def change_password(data: PasswordChangeInput, request: Request, user: dict = Depends(get_current_user)):
    """Change your own password. Signs out every other session; returns a fresh token for this one."""
    ip = client_ip(request)
    wait = await login_lock_seconds(user["email"], ip)
    if wait:
        raise HTTPException(status_code=429, detail="Too many wrong passwords. Please wait and try again.", headers={"Retry-After": str(wait)})
    full = await db.users.find_one({"id": user["id"]})
    if not verify_password(data.current_password, full["password_hash"]):
        await record_login_attempt(user["email"], ip, False, request.headers.get("user-agent", ""))
        raise HTTPException(status_code=400, detail="Your current password is not correct")
    validate_strong_password(data.new_password)
    if data.new_password == data.current_password:
        raise HTTPException(status_code=400, detail="Choose a password different from your current one")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password_hash": hash_password(data.new_password), "must_change_password": False,
        "password_changed_at": now_iso(),
    }})
    version = await revoke_sessions(user["id"])
    await audit(user, "self.password_change", user, "Changed own password; other sessions signed out", request)
    await notify_account_change("password_changed", user, user)
    updated = await db.users.find_one({"id": user["id"]})
    return {"token": create_access_token(user["id"], user["email"], version), "user": await shape_user(updated)}


@api_router.post("/auth/sign-out-everywhere")
async def sign_out_everywhere(request: Request, user: dict = Depends(get_current_user)):
    """Sign out all of your other sessions (other computers/phones); this one stays signed in."""
    version = await revoke_sessions(user["id"])
    await audit(user, "self.sign_out_everywhere", user, "", request)
    return {"token": create_access_token(user["id"], user["email"], version, user["_session"]["auth_time"])}


@api_router.get("/permissions")
async def list_permissions(user: dict = Depends(require_users)):
    return [{"key": k, "label": PERMISSION_LABELS[k]} for k in ASSIGNABLE_PERMISSIONS]


# ----------------------------- Security: sign-in activity (admins) -----------------------------
class LoginClearInput(BaseModel):
    email: Optional[str] = None
    ip: Optional[str] = None


@api_router.get("/security/login-attempts")
async def login_attempts_summary(days: int = Query(7, ge=1, le=LOGIN_HISTORY_DAYS), user: dict = Depends(require_admin)):
    """Failed sign-ins grouped by email + IP, newest first, with any active lock."""
    now = _utcnow()
    since = now - timedelta(days=days)
    groups: dict = {}
    async for a in db.login_attempts.find({"success": False, "at": {"$gte": since}}, {"_id": 0}).sort("at", -1):
        key = (a.get("email", ""), a.get("ip", ""))
        g = groups.get(key)
        if not g:
            g = groups[key] = {"email": key[0], "ip": key[1], "failures": 0, "last_attempt": _naive_utc(a["at"]), "user_agent": a.get("user_agent", "")}
        g["failures"] += 1
    out = []
    for g in groups.values():
        wait = await login_lock_seconds(g["email"], g["ip"])
        g["locked_until"] = (now + timedelta(seconds=wait)).replace(tzinfo=timezone.utc).isoformat() if wait else None
        g["last_attempt"] = g["last_attempt"].replace(tzinfo=timezone.utc).isoformat()
        out.append(g)
    out.sort(key=lambda g: g["last_attempt"], reverse=True)
    return {"days": days, "groups": out[:500]}


@api_router.post("/security/login-attempts/clear")
async def clear_login_lock(data: LoginClearInput, request: Request, user: dict = Depends(require_admin)):
    """Unlock an email+IP (or a whole IP) so the person can try again right away."""
    if not data.email and not data.ip:
        raise HTTPException(status_code=400, detail="Choose an email or IP address to unlock")
    q = _fail_query()
    if data.email:
        q["email"] = data.email.lower()
    if data.ip:
        q["ip"] = data.ip
    res = await db.login_attempts.update_many(q, {"$set": {"cleared": True}})
    logger.info(f"Login lock cleared by {user['email']}: email={data.email} ip={data.ip}")
    await audit(user, "login.unlock", {"email": data.email or ""}, f"IP: {data.ip}" if data.ip else "", request)
    return {"ok": True, "cleared": res.modified_count}


@api_router.get("/security/audit")
async def audit_log(limit: int = Query(200, ge=1, le=1000), user: dict = Depends(require_admin)):
    """Recent user, role and sign-in management actions, newest first."""
    return await db.audit_log.find({}, {"_id": 0}).sort("at", -1).to_list(limit)


def _date_ok(v) -> bool:
    try:
        check_date(v)
        return True
    except HTTPException:
        return False


def _amount_ok(v, allow_negative=False) -> bool:
    try:
        check_amount(v, allow_negative=allow_negative)
        return True
    except HTTPException:
        return False


@api_router.get("/security/data-check")
async def data_check(request: Request, user: dict = Depends(require_admin)):
    """Read-only scan for records that break today's rules (older data, imports, direct edits).
    Changes nothing."""
    accounts = {a["id"]: a for a in await db.accounts.find({}, {"_id": 0}).to_list(10000)}
    cats = {c["id"]: c for c in await db.categories.find({}, {"_id": 0}).to_list(10000)}
    payees = {p["id"] for p in await db.payees.find({}, {"_id": 0, "id": 1}).to_list(100000)}
    funds = {f["id"]: f for f in await db.funds.find({}, {"_id": 0}).to_list(10000)}
    issues = []

    def add(kind, rec, problem):
        if len(issues) < 1000:
            acct = accounts.get(rec.get("account_id"), {})
            issues.append({"kind": kind, "id": rec.get("id"), "date": rec.get("date") or rec.get("opening_date") or "",
                           "amount": rec.get("amount"), "account": acct.get("mask") or acct.get("name") or "",
                           "memo": (rec.get("memo") or rec.get("name") or "")[:80], "problem": problem})

    n_txn = 0
    async for t in db.transactions.find({}, {"_id": 0}):
        n_txn += 1
        tt = t.get("type")
        if tt not in TXN_TYPES:
            add("transaction", t, f"Unknown type '{tt}' (left out of all balances)")
        if not _date_ok(t.get("date")):
            add("transaction", t, f"Invalid date '{t.get('date')}'")
        if not _amount_ok(t.get("amount")):
            add("transaction", t, f"Invalid amount '{t.get('amount')}' (must be over $0.00 with 2 decimals)")
        if t.get("account_id") not in accounts:
            add("transaction", t, "Bank account no longer exists")
        if tt == "transfer":
            if not t.get("to_account_id"):
                add("transaction", t, "Transfer has no destination account")
            elif t.get("to_account_id") == t.get("account_id"):
                add("transaction", t, "Transfer goes to the same account it comes from")
            elif t.get("to_account_id") not in accounts:
                add("transaction", t, "Transfer destination account no longer exists")
        elif tt in ("income", "expense"):
            if t.get("payee_id") and t["payee_id"] not in payees:
                add("transaction", t, "Payee no longer exists")
            if t.get("category_id"):
                c = cats.get(t["category_id"])
                if not c:
                    add("transaction", t, "Category no longer exists")
                elif c.get("type") != tt:
                    add("transaction", t, f"Category '{c.get('name')}' is for {c.get('type')}, but this is {tt}")
            splits = t.get("fund_splits") or []
            if splits:
                if any(sp.get("fund_id") not in funds for sp in splits):
                    add("transaction", t, "A fund in its split no longer exists (that part is missing from fund balances)")
                try:
                    if abs(round(sum(float(sp.get("amount") or 0) for sp in splits), 2) - round(float(t.get("amount") or 0), 2)) > 0.01:
                        add("transaction", t, "Fund split doesn't add up to the transaction amount")
                except (TypeError, ValueError):
                    add("transaction", t, "Fund split has an invalid amount")
            elif t.get("fund_id") and t["fund_id"] not in funds:
                add("transaction", t, "Fund no longer exists (missing from fund balances)")

    n_act = 0
    async for a in db.fund_activity.find({}, {"_id": 0}):
        n_act += 1
        if not _date_ok(a.get("date")):
            add("fund activity", a, f"Invalid date '{a.get('date')}'")
        if a.get("type") == "move":
            if not _amount_ok(a.get("amount")):
                add("fund activity", a, "Fund move amount must be over $0.00")
            if a.get("from_fund_id") not in funds or a.get("to_fund_id") not in funds:
                add("fund activity", a, "A fund in this move no longer exists")
        elif a.get("type") == "adjust":
            if not _amount_ok(a.get("amount"), allow_negative=True):
                add("fund activity", a, "Adjustment amount is zero or invalid")
            if a.get("fund_id") not in funds:
                add("fund activity", a, "The adjusted fund no longer exists")
        else:
            add("fund activity", a, f"Unknown fund activity type '{a.get('type')}'")

    for acc in accounts.values():
        if acc.get("opening_date") and not _date_ok(acc["opening_date"]):
            add("bank account", acc, f"Invalid opening date '{acc['opening_date']}'")
    for f in funds.values():
        if f.get("opening_date") and not _date_ok(f["opening_date"]):
            add("fund", f, f"Invalid opening date '{f['opening_date']}'")
        if f.get("parent_id") and f["parent_id"] not in funds:
            add("fund", f, "Its parent fund no longer exists (shown at top level)")
    for c in cats.values():
        if c.get("type") not in ("income", "expense"):
            add("category", c, f"Unknown category type '{c.get('type')}'")

    summary = {}
    for i in issues:
        summary[i["problem"].split(" '")[0]] = summary.get(i["problem"].split(" '")[0], 0) + 1
    await audit(user, "data.check", None, f"{len(issues)} issue(s) found", request)
    return {"checked": {"transactions": n_txn, "fund_activity": n_act, "accounts": len(accounts), "funds": len(funds),
                        "categories": len(cats), "payees": len(payees)},
            "issue_count": len(issues), "summary": summary, "issues": issues}


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
async def create_role(data: RoleInput, request: Request, user: dict = Depends(require_users)):
    perms = [p for p in data.permissions if p in ASSIGNABLE_PERMISSIONS]
    ensure_can_grant(user, perms)
    doc = {"id": new_id(), "name": data.name.strip(), "permissions": perms, "is_system": False, "created_at": now_iso()}
    await db.roles.insert_one(doc)
    await audit(user, "role.create", {"id": doc["id"], "name": doc["name"]}, ", ".join(perms) or "no permissions", request)
    return clean(doc)


@api_router.put("/roles/{role_id}")
async def update_role(role_id: str, data: RoleInput, request: Request, user: dict = Depends(require_users)):
    role = await db.roles.find_one({"id": role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="The Administrator role cannot be modified")
    perms = [p for p in data.permissions if p in ASSIGNABLE_PERMISSIONS]
    # must already hold everything the role grants now and after the change
    ensure_can_grant(user, list(set(perms) | set(role.get("permissions", []))))
    await db.roles.update_one({"id": role_id}, {"$set": {"name": data.name.strip(), "permissions": perms}})
    added = sorted(set(perms) - set(role.get("permissions", [])))
    removed = sorted(set(role.get("permissions", [])) - set(perms))
    if added or removed or data.name.strip() != role.get("name"):
        detail = "; ".join(x for x in [f"added: {', '.join(added)}" if added else "", f"removed: {', '.join(removed)}" if removed else ""] if x)
        await audit(user, "role.update", {"id": role_id, "name": data.name.strip()}, detail or "renamed", request)
    return await db.roles.find_one({"id": role_id}, {"_id": 0})


@api_router.delete("/roles/{role_id}")
async def delete_role(role_id: str, request: Request, user: dict = Depends(require_users)):
    role = await db.roles.find_one({"id": role_id})
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.get("is_system"):
        raise HTTPException(status_code=400, detail="The Administrator role cannot be deleted")
    ensure_can_grant(user, role.get("permissions", []))
    if await db.users.count_documents({"role_id": role_id}) > 0:
        raise HTTPException(status_code=400, detail="This role is assigned to one or more users. Reassign them first.")
    await db.roles.delete_one({"id": role_id})
    await audit(user, "role.delete", {"id": role_id, "name": role.get("name", "")}, "", request)
    return {"ok": True}


# ----------------------------- Users -----------------------------
@api_router.get("/auth/users")
async def list_users(user: dict = Depends(require_users)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0, "token_version": 0}).to_list(1000)
    roles = {r["id"]: r["name"] for r in await db.roles.find({}, {"_id": 0}).to_list(1000)}
    for u in users:
        u["role_name"] = "Administrator" if u.get("role") == "admin" else roles.get(u.get("role_id"), "")
    return users


@api_router.post("/auth/users")
async def create_user(data: UserCreate, request: Request, user: dict = Depends(require_users)):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists")
    validate_strong_password(data.password)
    await ensure_can_assign_role(user, data.role_id)
    role = await db.roles.find_one({"id": data.role_id}) if data.role_id else None
    doc = {
        "id": new_id(),
        "email": data.email.lower(),
        "name": data.name,
        "role": "admin" if (role and role.get("is_system")) else "user",
        "role_id": data.role_id,
        "password_hash": hash_password(data.password),
        "must_change_password": True,  # the person who set it shouldn't know their final password
        "token_version": 0,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await audit(user, "user.create", doc, f"Role: {role.get('name') if role else 'none'}", request)
    await notify_account_change("created", doc, user, role.get("name") if role else "none")
    return await shape_user(doc)


@api_router.put("/auth/users/{user_id}")
async def update_user(user_id: str, data: UserUpdate, request: Request, user: dict = Depends(require_users)):
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    is_self = user_id == user["id"]
    if not is_self:
        await ensure_can_manage_user(user, target)
    if data.role_id is not None:
        await ensure_can_assign_role(user, data.role_id)
    if data.password and is_self:
        raise HTTPException(status_code=400, detail="To change your own password, use Change Password in your account menu")
    update = {}
    events = []
    if data.name is not None and data.name != target.get("name"):
        update["name"] = data.name
        events.append(("user.rename", f"{target.get('name')} → {data.name}"))
    role_changed = False
    if data.role_id is not None and (data.role_id or None) != target.get("role_id"):
        if is_self and target.get("role") == "admin":
            raise HTTPException(status_code=400, detail="You cannot change your own administrator role")
        old_role = await db.roles.find_one({"id": target.get("role_id")}) if target.get("role_id") else None
        role = await db.roles.find_one({"id": data.role_id}) if data.role_id else None
        update["role_id"] = data.role_id or None
        update["role"] = "admin" if (role and role.get("is_system")) else "user"
        role_changed = True
        events.append(("user.role_change", f"{(old_role or {}).get('name', 'none')} → {(role or {}).get('name', 'none')}"))
    if data.password:
        validate_strong_password(data.password)
        update["password_hash"] = hash_password(data.password)
        update["must_change_password"] = True
        events.append(("user.password_reset", "Temporary password set; must change at next sign-in"))
    if update:
        await db.users.update_one({"id": user_id}, {"$set": update})
    if data.password or (role_changed and not is_self):
        await revoke_sessions(user_id)  # old sessions stop working immediately
    for action, details in events:
        await audit(user, action, target, details, request)
        if action == "user.password_reset":
            await notify_account_change("password_reset", target, user)
        elif action == "user.role_change" and not is_self:
            await notify_account_change("role_change", target, user, details)
    updated = await db.users.find_one({"id": user_id})
    return await shape_user(updated)


@api_router.post("/auth/users/{user_id}/sign-out")
async def sign_out_user(user_id: str, request: Request, user: dict = Depends(require_users)):
    """Sign a user out of every device right now."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user_id != user["id"]:
        await ensure_can_manage_user(user, target)
    await revoke_sessions(user_id)
    await audit(user, "user.sign_out", target, "Signed out of all devices", request)
    return {"ok": True}


@api_router.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, request: Request, user: dict = Depends(require_users)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await ensure_can_manage_user(user, target)
    await db.users.delete_one({"id": user_id})
    await audit(user, "user.delete", target, "", request)
    return {"ok": True}


# ----------------------------- Generic CRUD factory -----------------------------
# ----------------------------- Validation helpers -----------------------------
TXN_TYPES = ("income", "expense", "transfer")
MAX_AMOUNT = 1_000_000_000


def check_date(value, label: str = "Date", required: bool = True) -> str:
    """A real calendar date in YYYY-MM-DD form."""
    v = (value or "").strip() if isinstance(value, str) else ""
    if not v:
        if required:
            raise HTTPException(status_code=400, detail=f"{label} is required")
        return ""
    try:
        d = datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} must be a real date in YYYY-MM-DD form")
    if not (1900 <= d.year <= 2200):
        raise HTTPException(status_code=400, detail=f"{label} looks wrong (year {d.year})")
    return v


def check_amount(value, label: str = "Amount", allow_negative: bool = False) -> float:
    """Greater than zero (or non-zero when negatives are allowed), at most 2 decimal places."""
    try:
        amt = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{label} must be a number")
    if amt != amt or abs(amt) >= MAX_AMOUNT:  # NaN or absurd
        raise HTTPException(status_code=400, detail=f"{label} is not a valid amount")
    if allow_negative:
        if amt == 0:
            raise HTTPException(status_code=400, detail=f"{label} can't be zero")
    elif amt <= 0:
        raise HTTPException(status_code=400, detail=f"{label} must be greater than zero")
    if abs(round(amt, 2) - amt) > 1e-9:
        raise HTTPException(status_code=400, detail=f"{label} can have at most 2 decimal places")
    return round(amt, 2)


def check_name(value, label: str = "Name") -> str:
    v = (value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail=f"{label} is required")
    if len(v) > 200:
        raise HTTPException(status_code=400, detail=f"{label} is too long")
    return v


async def require_ref(collection: str, item_id: Optional[str], label: str) -> Optional[dict]:
    if not item_id:
        return None
    doc = await db[collection].find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=400, detail=f"That {label} doesn't exist (it may have been deleted)")
    return doc


# How each kind of item is referenced, for refusing deletes of things still in use.
USAGE_QUERIES = {
    "accounts": lambda i: [("transactions", {"$or": [{"account_id": i}, {"to_account_id": i}]})],
    "categories": lambda i: [("transactions", {"category_id": i})],
    "payees": lambda i: [("transactions", {"payee_id": i})],
    "funds": lambda i: [("transactions", {"$or": [{"fund_id": i}, {"fund_splits.fund_id": i}]}),
                        ("fund_activity", {"$or": [{"fund_id": i}, {"from_fund_id": i}, {"to_fund_id": i}]})],
}
USAGE_LABELS = {"accounts": "bank account", "categories": "category", "payees": "payee", "funds": "fund"}


async def ensure_not_in_use(collection: str, item_id: str):
    txns = acts = 0
    for coll, q in USAGE_QUERIES[collection](item_id):
        n = await db[coll].count_documents(q)
        if coll == "transactions":
            txns += n
        else:
            acts += n
    if txns or acts:
        parts = []
        if txns:
            parts.append(f"{txns} transaction{'s' if txns != 1 else ''}")
        if acts:
            parts.append(f"{acts} fund move{'s' if acts != 1 else ''}/adjustment{'s' if acts != 1 else ''}")
        raise HTTPException(status_code=409, detail=f"This {USAGE_LABELS[collection]} is used by {' and '.join(parts)}, "
                                                    "so it can't be deleted. Mark it inactive instead to hide it from new entries.")


async def validate_item(collection: str, doc: dict, item_id: Optional[str] = None) -> dict:
    doc["name"] = check_name(doc.get("name"))
    if collection == "categories" and doc.get("type") not in ("income", "expense"):
        raise HTTPException(status_code=400, detail="Category type must be income or expense")
    if collection in ("accounts", "funds"):
        doc["opening_date"] = check_date(doc.get("opening_date"), "Opening date", required=False)
        try:
            doc["opening_balance"] = round(float(doc.get("opening_balance") or 0), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Opening balance must be a number")
    return doc


def register_crud(path: str, collection: str, model):
    @api_router.get(f"/{path}")
    async def list_items(user: dict = Depends(get_current_user), _coll=collection):
        items = await db[_coll].find({}, {"_id": 0}).sort("name", 1).to_list(1000)
        return items

    @api_router.post(f"/{path}")
    async def create_item(data: model, user: dict = Depends(require_settings), _coll=collection):
        doc = await validate_item(_coll, data.model_dump())
        doc["id"] = new_id()
        doc["created_at"] = now_iso()
        await db[_coll].insert_one(doc)
        return clean(doc)

    @api_router.put(f"/{path}/{{item_id}}")
    async def update_item(item_id: str, data: model, user: dict = Depends(require_settings), _coll=collection):
        existing = await db[_coll].find_one({"id": item_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        await db[_coll].update_one({"id": item_id}, {"$set": await validate_item(_coll, data.model_dump(), item_id)})
        updated = await db[_coll].find_one({"id": item_id}, {"_id": 0})
        return updated

    @api_router.delete(f"/{path}/{{item_id}}")
    async def delete_item(item_id: str, user: dict = Depends(require_settings), _coll=collection):
        await ensure_not_in_use(_coll, item_id)
        await db[_coll].delete_one({"id": item_id})
        return {"ok": True}


register_crud("accounts", "accounts", AccountInput)
register_crud("categories", "categories", CategoryInput)
register_crud("payees", "payees", PayeeInput)


# ----------------------------- Funds (custom: supports nesting) -----------------------------
async def validate_fund_parent(parent_id: Optional[str], fund_id: Optional[str]):
    if not parent_id:
        return
    if parent_id == fund_id:
        raise HTTPException(status_code=400, detail="A fund cannot be its own parent")
    cur = parent_id
    seen = set()
    while cur:
        if cur == fund_id:
            raise HTTPException(status_code=400, detail="That would create a loop between funds")
        if cur in seen:
            break
        seen.add(cur)
        p = await db.funds.find_one({"id": cur}, {"_id": 0, "parent_id": 1})
        if not p:
            if cur == parent_id:
                raise HTTPException(status_code=400, detail="Parent fund not found")
            break
        cur = p.get("parent_id")


@api_router.get("/funds")
async def list_funds(user: dict = Depends(get_current_user)):
    return await db.funds.find({}, {"_id": 0}).sort("name", 1).to_list(1000)


@api_router.post("/funds")
async def create_fund(data: FundInput, user: dict = Depends(require_settings)):
    await validate_fund_parent(data.parent_id, None)
    doc = await validate_item("funds", data.model_dump())
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    await db.funds.insert_one(doc)
    return clean(doc)


@api_router.put("/funds/{fund_id}")
async def update_fund(fund_id: str, data: FundInput, user: dict = Depends(require_settings)):
    existing = await db.funds.find_one({"id": fund_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Fund not found")
    await validate_fund_parent(data.parent_id, fund_id)
    await db.funds.update_one({"id": fund_id}, {"$set": await validate_item("funds", data.model_dump(), fund_id)})
    return await db.funds.find_one({"id": fund_id}, {"_id": 0})


@api_router.delete("/funds/{fund_id}")
async def delete_fund(fund_id: str, user: dict = Depends(require_settings)):
    await ensure_not_in_use("funds", fund_id)
    f = await db.funds.find_one({"id": fund_id}, {"_id": 0})
    if f:
        # keep any children in the tree by re-parenting them to this fund's parent
        await db.funds.update_many({"parent_id": fund_id}, {"$set": {"parent_id": f.get("parent_id")}})
    await db.funds.delete_one({"id": fund_id})
    return {"ok": True}


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
    search: Optional[str] = Query(None, max_length=100),
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
        check_date(start, "Start date", required=False); check_date(end, "End date", required=False)
        drange = {}
        if start:
            drange["$gte"] = start
        if end:
            drange["$lte"] = end
        query["date"] = drange
    if search and search.strip():
        # Treat the search box as plain text (re.escape), so characters like . ( * + match
        # themselves and can't be used to build slow patterns.
        pattern = re.escape(search.strip())
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"memo": {"$regex": pattern, "$options": "i"}},
                {"check_number": {"$regex": pattern, "$options": "i"}},
            ]
        }]
    items = await db.transactions.find(query, {"_id": 0}).sort("date", -1).to_list(5000)

    # Within the same date, show higher check numbers first (checks before non-check
    # entries like deposits/transfers). Check numbers are stored as strings.
    def _check_sort_key(t):
        raw = (t.get("check_number") or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return int(digits) if digits else -1

    items.sort(key=lambda t: (t.get("date", ""), _check_sort_key(t)), reverse=True)
    ids = [t["id"] for t in items]
    counts = {}
    if ids:
        async for f in db.files.find({"transaction_id": {"$in": ids}, "is_deleted": False}, {"_id": 0, "transaction_id": 1}):
            counts[f["transaction_id"]] = counts.get(f["transaction_id"], 0) + 1
    for t in items:
        t["attachment_count"] = counts.get(t["id"], 0)
        t["payment_method"] = effective_payment_method(t)
    return items


@api_router.get("/payment-methods")
async def list_payment_methods(user: dict = Depends(get_current_user)):
    return [{"id": k, "label": v} for k, v in PAYMENT_METHODS.items()]


def normalize_txn_payment(data: TransactionInput) -> dict:
    """Validate the payment method and keep the check number only for checks."""
    doc = data.model_dump()
    if data.type == "expense":
        raw = (data.payment_method or "").strip()
        pm = normalize_payment_method(raw)
        if raw and not pm:
            raise HTTPException(status_code=400, detail="Choose a valid payment method")
        if not pm:
            # older API clients: treat as a check when a check number is given
            pm = "check" if (data.check_number or "").strip() else "other"
        doc["payment_method"] = pm
        doc["check_number"] = (data.check_number or "").strip() if pm == "check" else ""
    else:
        doc["payment_method"] = ""
        doc["check_number"] = ""
    return doc


def validate_fund_allocation(data: TransactionInput):
    """When a transaction splits across funds, the parts must add up to the total."""
    if data.type == "transfer" or not data.fund_splits:
        return
    for s in data.fund_splits:
        check_amount(s.amount, "Each fund split")
    if len({s.fund_id for s in data.fund_splits}) != len(data.fund_splits):
        raise HTTPException(status_code=400, detail="Each fund can only appear once in a split")
    total = round(sum(s.amount for s in data.fund_splits), 2)
    if abs(total - round(data.amount, 2)) > 0.01:
        raise HTTPException(status_code=400, detail="Fund splits must add up to the transaction amount")


async def validate_transaction(data: TransactionInput) -> dict:
    """All the rules a transaction must meet, whoever sends it. Returns the document to save."""
    if data.type not in TXN_TYPES:
        raise HTTPException(status_code=400, detail="Type must be income, expense or transfer")
    check_date(data.date)
    data.amount = check_amount(data.amount)
    if not data.account_id:
        raise HTTPException(status_code=400, detail="Choose a bank account")
    await require_ref("accounts", data.account_id, "bank account")
    if data.type == "transfer":
        if not data.to_account_id:
            raise HTTPException(status_code=400, detail="A transfer needs a destination account")
        if data.to_account_id == data.account_id:
            raise HTTPException(status_code=400, detail="A transfer must go to a different account")
        await require_ref("accounts", data.to_account_id, "destination account")
        # transfers don't carry payee, category or fund
        data.payee_id = data.category_id = data.fund_id = None
        data.fund_splits = None
    else:
        data.to_account_id = None
        await require_ref("payees", data.payee_id, "payee")
        cat = await require_ref("categories", data.category_id, "category")
        if cat and cat.get("type") != data.type:
            raise HTTPException(status_code=400, detail=f"That category is for {cat.get('type')}, not {data.type}")
        if data.fund_splits:
            data.fund_id = None
            for sp in data.fund_splits:
                await require_ref("funds", sp.fund_id, "fund")
        else:
            await require_ref("funds", data.fund_id, "fund")
    validate_fund_allocation(data)
    doc = normalize_txn_payment(data)
    doc["memo"] = (doc.get("memo") or "")[:1000]
    return doc


@api_router.post("/transactions")
async def create_transaction(data: TransactionInput, user: dict = Depends(require_txn_manage)):
    doc = await validate_transaction(data)
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
    doc = await validate_transaction(data)
    doc["updated_at"] = now_iso()
    await db.transactions.update_one({"id": txn_id}, {"$set": doc})
    updated = await db.transactions.find_one({"id": txn_id}, {"_id": 0})
    return updated


@api_router.delete("/transactions/{txn_id}")
async def delete_transaction(txn_id: str, user: dict = Depends(require_txn_manage)):
    await db.transactions.delete_one({"id": txn_id})
    await db.files.update_many({"transaction_id": txn_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


class ClearedInput(BaseModel):
    cleared: bool


class VoidInput(BaseModel):
    voided: bool


@api_router.patch("/transactions/{txn_id}/cleared")
async def set_cleared(txn_id: str, data: ClearedInput, user: dict = Depends(require_txn_manage)):
    existing = await db.transactions.find_one({"id": txn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if data.cleared and existing.get("voided"):
        raise HTTPException(status_code=400, detail="This entry is voided. Restore it before marking it cleared.")
    await db.transactions.update_one({"id": txn_id}, {"$set": {"cleared": data.cleared}})
    return {"ok": True, "cleared": data.cleared}


@api_router.patch("/transactions/{txn_id}/void")
async def set_voided(txn_id: str, data: VoidInput, user: dict = Depends(require_txn_manage)):
    existing = await db.transactions.find_one({"id": txn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Transaction not found")
    update = {"voided": data.voided}
    # A voided entry is removed from all balances, so it can't also be reconciled as cleared.
    if data.voided:
        update["cleared"] = False
    await db.transactions.update_one({"id": txn_id}, {"$set": update})
    return {"ok": True, "voided": data.voided}


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
    query = {"$or": [{"account_id": account_id}, {"to_account_id": account_id}], "voided": {"$ne": True}}
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
async def download_attachment(file_id: str, user: dict = Depends(require_txn_view)):
    record = await db.files.find_one({"id": file_id, "is_deleted": False})
    if not record or not record.get("gridfs_id"):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        stream = await fs_bucket.open_download_stream(ObjectId(record["gridfs_id"]))
        content = await stream.read()
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=content, media_type=record.get("content_type", "application/octet-stream"),
                    headers=private_download_headers(record.get("original_filename") or "receipt", inline=True))


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
IMPORT_COLUMNS = ["Date", "Type", "Account", "To Account", "Amount", "Payment Method", "Check#", "Payee", "Category", "Fund", "Memo"]


@api_router.get("/import/template")
async def import_template(user: dict = Depends(require_txn_manage)):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(IMPORT_COLUMNS)
    writer.writerow(["2026-06-07", "income", "*1234", "", "1420.10", "", "", "", "Deposit", "General Fund", "Sunday offering"])
    writer.writerow(["2026-06-03", "expense", "*1234", "", "144.76", "Check", "4035", "Frontier Communications", "Utilities", "General Fund", "Internet/Phone Service"])
    writer.writerow(["2026-06-15", "transfer", "*1234", "*5678", "500.00", "", "", "", "", "", "Move to savings"])
    out.seek(0)
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers=private_download_headers("transaction-import-template.csv"),
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

        # payment method (expenses only). Optional column: blank = Check when a Check# is given, else Other.
        payment_method = ""
        check_no = (row.get("Check#") or "").strip()
        if ttype == "expense":
            raw_pm = (row.get("Payment Method") or "").strip()
            payment_method = normalize_payment_method(raw_pm)
            if raw_pm and not payment_method:
                errors.append({"row": i, "reason": f"Invalid Payment Method '{raw_pm}' (use {', '.join(PAYMENT_METHODS.values())})"})
                continue
            if not payment_method:
                payment_method = "check" if check_no else "other"
            if payment_method != "check":
                check_no = ""
        else:
            check_no = ""

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
            "payee_id": payee_id, "payment_method": payment_method, "check_number": check_no,
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


# ----------------------------- Fund balances & activity -----------------------------
async def compute_fund_balances(up_to: Optional[str] = None):
    """Fund balances = opening balance + income/expense (incl. splits) + fund moves/adjustments.
    up_to is an inclusive end date (YYYY-MM-DD) or None for all-time."""
    funds = await db.funds.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    fmap = {}
    for f in funds:
        ob = float(f.get("opening_balance", 0.0) or 0.0)
        od = f.get("opening_date") or ""
        if up_to is not None and od and od > up_to:
            ob = 0.0
        fmap[f["id"]] = {**f, "balance": ob}

    txn_q = {"type": {"$in": ["income", "expense"]}, "voided": {"$ne": True}}
    if up_to is not None:
        txn_q["date"] = {"$lte": up_to}
    async for t in db.transactions.find(txn_q, {"_id": 0}):
        sign = 1.0 if t["type"] == "income" else -1.0
        splits = t.get("fund_splits")
        if splits:
            for s in splits:
                fid = s.get("fund_id")
                if fid in fmap:
                    fmap[fid]["balance"] += sign * float(s.get("amount", 0) or 0)
        else:
            fid = t.get("fund_id")
            if fid in fmap:
                fmap[fid]["balance"] += sign * float(t["amount"])

    act_q = {}
    if up_to is not None:
        act_q["date"] = {"$lte": up_to}
    async for a in db.fund_activity.find(act_q, {"_id": 0}):
        amt = float(a.get("amount", 0) or 0)
        if a.get("type") == "move":
            if a.get("from_fund_id") in fmap:
                fmap[a["from_fund_id"]]["balance"] -= amt
            if a.get("to_fund_id") in fmap:
                fmap[a["to_fund_id"]]["balance"] += amt
        elif a.get("type") == "adjust":
            if a.get("fund_id") in fmap:
                fmap[a["fund_id"]]["balance"] += amt

    for fid in fmap:
        fmap[fid]["balance"] = round(fmap[fid]["balance"], 2)

    # Roll up child balances into parents (supports multi-level nesting).
    by_id = fmap
    children: dict = {}
    for fid, f in fmap.items():
        pid = f.get("parent_id")
        if pid not in fmap:
            pid = None
        children.setdefault(pid, []).append(fid)

    rolled: dict = {}

    def roll(fid, stack):
        if fid in rolled:
            return rolled[fid]
        total = fmap[fid]["balance"]
        for c in children.get(fid, []):
            if c in stack:
                continue
            total += roll(c, stack | {fid})
        rolled[fid] = round(total, 2)
        return rolled[fid]

    for fid in fmap:
        roll(fid, set())

    ordered = []

    def emit(fid, depth):
        f = fmap[fid]
        ordered.append({
            **f,
            "balance": f["balance"],
            "rolled_balance": rolled[fid],
            "depth": depth,
            "has_children": bool(children.get(fid)),
        })
        for c in sorted(children.get(fid, []), key=lambda i: by_id[i].get("name", "").lower()):
            emit(c, depth + 1)

    for rid in sorted(children.get(None, []), key=lambda i: by_id[i].get("name", "").lower()):
        emit(rid, 0)
    return ordered


@api_router.get("/fund-activity")
async def list_fund_activity(user: dict = Depends(require_txn_view)):
    funds = {f["id"]: f["name"] for f in await db.funds.find({}, {"_id": 0}).to_list(1000)}
    items = await db.fund_activity.find({}, {"_id": 0}).sort("date", -1).to_list(5000)
    for a in items:
        a["from_fund_name"] = funds.get(a.get("from_fund_id"), "")
        a["to_fund_name"] = funds.get(a.get("to_fund_id"), "")
        a["fund_name"] = funds.get(a.get("fund_id"), "")
    return items


@api_router.post("/fund-activity")
async def create_fund_activity(data: FundActivityInput, user: dict = Depends(require_txn_manage)):
    if data.type not in ("move", "adjust"):
        raise HTTPException(status_code=400, detail="Invalid fund activity type")
    check_date(data.date)
    if data.type == "move":
        if not data.from_fund_id or not data.to_fund_id:
            raise HTTPException(status_code=400, detail="Choose both a source and a destination fund")
        if data.from_fund_id == data.to_fund_id:
            raise HTTPException(status_code=400, detail="Source and destination funds must differ")
        data.amount = check_amount(data.amount, "Amount")
        await require_ref("funds", data.from_fund_id, "source fund")
        await require_ref("funds", data.to_fund_id, "destination fund")
        data.fund_id = None
    else:  # adjust
        if not data.fund_id:
            raise HTTPException(status_code=400, detail="Choose a fund to adjust")
        data.amount = check_amount(data.amount, "The adjustment", allow_negative=True)
        await require_ref("funds", data.fund_id, "fund")
        data.from_fund_id = data.to_fund_id = None
    doc = data.model_dump()
    doc["memo"] = (doc.get("memo") or "")[:1000]
    doc["id"] = new_id()
    doc["created_at"] = now_iso()
    doc["created_by"] = user["id"]
    await db.fund_activity.insert_one(doc)
    return clean(doc)


@api_router.delete("/fund-activity/{activity_id}")
async def delete_fund_activity(activity_id: str, user: dict = Depends(require_txn_manage)):
    await db.fund_activity.delete_one({"id": activity_id})
    return {"ok": True}


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

    # fund balances (opening + income/expense splits + fund activity)
    fund_balances = await compute_fund_balances()

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
            "voided": {"$ne": True},
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
                pm = effective_payment_method(t)
                txn_type_label = PAYMENT_METHODS.get(pm, "")
                if t["type"] == "transfer":
                    dest = account_names.get(t.get("to_account_id"), {})
                    label_payee = f"Transfer to {dest.get('mask') or dest.get('name', 'account')}"
                    txn_type_label = "Transfer"
                expenses.append({
                    "date": t["date"],
                    "payment_method": pm,
                    "transaction_type": txn_type_label,
                    "check_number": t.get("check_number", "") if pm == "check" else "",
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
        "voided": {"$ne": True},
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

    # fund balances as of end (opening + income/expense splits + fund activity; parents roll up children)
    fb = await compute_fund_balances(end)
    fund_balances = [{"name": v["name"], "balance": v["rolled_balance"], "own_balance": v["balance"], "depth": v["depth"], "has_children": v["has_children"]} for v in fb]

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
    check_date(start, "Start date"); check_date(end, "End date")
    if start > end:
        raise HTTPException(status_code=400, detail="The start date must be on or before the end date")
    ids = [i for i in account_ids.split(",") if i]
    return await build_report(start, end, ids)


# ----------------------------- PDF -----------------------------
def esc(value) -> str:
    """Make text safe to put inside ReportLab Paragraph markup: < > & print as themselves
    instead of being read as formatting tags (e.g. <font>, <a href>, <img src>)."""
    return xml_escape(str(value if value is not None else ""), {'"': "&quot;", "'": "&#39;"})


def money(v: float) -> str:
    v = round(float(v or 0), 2) + 0.0  # + 0.0 turns -0.0 into 0.0
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


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
    check_date(start, "Start date"); check_date(end, "End date")
    if start > end:
        raise HTTPException(status_code=400, detail="The start date must be on or before the end date")
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
    elems.append(Paragraph(esc(church.get("church_name") or "Church"), h_title))
    elems.append(Paragraph("Treasurer's Report", h_sub))
    elems.append(Paragraph(f"{esc(fmt_date(start))} &mdash; {esc(fmt_date(end))}", h_sub))
    elems.append(Spacer(1, 6))
    elems.append(HRFlowable(width="100%", thickness=1.2, color=navy))

    for idx, acc in enumerate(report["accounts"]):
        # each bank account after the first starts on its own page
        if idx > 0:
            elems.append(PageBreak())
        title = acc["mask"] or acc["name"]
        elems.append(Paragraph(f"Account {esc(title)} &nbsp; <font size=9 color='#64748B'>{esc(acc['name'])}</font>", h_acc))
        elems.append(Paragraph(f"Balance Forward as of {esc(fmt_date(start))}: <b>{money(acc['balance_forward'])}</b>", normal))

        # Expenses
        elems.append(Paragraph("Expenses", label))
        exp_data = [["Date", "Type", "Check #", "Payee", "Memo / Reason", "Amount"]]
        for e in acc["expenses"]:
            exp_data.append([fmt_date(e["date"]), e.get("transaction_type") or "", e["check_number"] or "", e["payee"] or "", e["memo"] or "", money(e["amount"])])
        if len(exp_data) == 1:
            exp_data.append(["", "", "", "No expenses", "", ""])
        exp_data.append(["", "", "", "", "Total Expenses", money(acc["total_expenses"])])
        t = Table(exp_data, colWidths=[0.75 * inch, 1.05 * inch, 0.6 * inch, 1.85 * inch, 1.85 * inch, 0.9 * inch])
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

    show_category = include_category and report["category_summary"]
    show_funds = include_funds and report["fund_balances"]
    # category summary + fund balances close the report on a final page
    if show_category or show_funds:
        elems.append(PageBreak())

    if show_category:
        elems.append(Paragraph("Income &amp; Expense by Category", h_acc))
        cat_data = [["Category", "Type", "Amount"]]
        for c in report["category_summary"]:
            cat_data.append([c["category"], c["type"].title(), money(c["amount"])])
        tc = Table(cat_data, colWidths=[3.5 * inch, 2.0 * inch, 1.5 * inch])
        tc.setStyle(_table_style(navy, len(cat_data), total_row=False))
        elems.append(tc)

    if show_funds:
        elems.append(Paragraph("Fund Balances", h_acc))
        f_data = [["Fund", "Balance"]]
        for f in report["fund_balances"]:
            f_data.append([("    " * f.get("depth", 0)) + f["name"], money(f["balance"])])
        tf = Table(f_data, colWidths=[5.0 * inch, 2.0 * inch])
        tf.setStyle(_table_style(navy, len(f_data), total_row=False))
        elems.append(tf)

    elems.append(Spacer(1, 30))
    elems.append(Paragraph("Respectfully submitted,", normal))
    elems.append(Spacer(1, 22))
    elems.append(Paragraph("______________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: ____________", normal))
    tname = church.get("treasurer_name") or ""
    elems.append(Paragraph(f"{esc(tname)}, Treasurer" if tname else "Treasurer", ParagraphStyle("t", parent=normal, textColor=muted, fontSize=8)))

    doc.build(elems)
    buf.seek(0)
    filename = f"treasurers-report-{start}-to-{end}.pdf"
    return StreamingResponse(buf, media_type="application/pdf", headers=private_download_headers(filename))


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


# ----------------------------- Secrets at rest -----------------------------
# Secrets the app must keep in its own database (the SMTP password, the backup encryption key)
# are sealed with a key derived from JWT_SECRET, so a copied database or dump alone doesn't
# reveal them. Changing JWT_SECRET means re-entering the SMTP password and backup passphrase.
_AT_REST_KEY = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                    info=b"grace-treasury/secrets-at-rest/v1").derive(JWT_SECRET.encode("utf-8"))
SEALED_PREFIX = "enc:v1:"
_SEAL_AAD = b"grace-treasury-secret"


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


def seal(plain: str) -> str:
    if not plain:
        return ""
    if plain.startswith(SEALED_PREFIX):
        return plain
    nonce = secrets.token_bytes(12)
    return SEALED_PREFIX + _b64e(nonce + AESGCM(_AT_REST_KEY).encrypt(nonce, plain.encode("utf-8"), _SEAL_AAD))


def unseal(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(SEALED_PREFIX):
        return value  # stored before encryption existed; sealed on the next startup
    try:
        raw = _b64d(value[len(SEALED_PREFIX):])
        return AESGCM(_AT_REST_KEY).decrypt(raw[:12], raw[12:], _SEAL_AAD).decode("utf-8")
    except Exception:
        logger.error("Could not decrypt a stored secret — was JWT_SECRET changed? Re-enter it in Settings.")
        return ""


# ----------------------------- Data backup / restore -----------------------------
EXPORT_COLLECTIONS = ["users", "roles", "accounts", "funds", "categories", "payees", "transactions", "fund_activity", "files", "settings"]
# Settings documents that stay on this server and are never written into a backup.
SERVER_ONLY_SETTINGS = {"backup_encryption"}

BACKUP_FORMAT = "grace-treasury-encrypted-backup"
BACKUP_AAD = BACKUP_FORMAT.encode("ascii")
SCRYPT_PARAMS = {"n": 2 ** 15, "r": 8, "p": 1}
MIN_PASSPHRASE = 12


class PassphraseInput(BaseModel):
    passphrase: str


class RestoreInput(BaseModel):
    passphrase: Optional[str] = None


def derive_backup_key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))


async def get_backup_crypto() -> Optional[dict]:
    """The active backup key and KDF parameters, or None if no passphrase has been set."""
    doc = await db.settings.find_one({"id": "backup_encryption"}, {"_id": 0})
    if not doc or not doc.get("key"):
        return None
    key_b64 = unseal(doc["key"])
    if not key_b64:
        return None
    return {"key": _b64d(key_b64), "kdf": {"name": "scrypt", "salt": doc["salt"], "n": doc["n"], "r": doc["r"], "p": doc["p"]}}


def encrypt_backup(payload: dict, crypto: dict) -> dict:
    nonce = secrets.token_bytes(12)
    body = json.dumps(payload).encode("utf-8")
    return {
        "format": BACKUP_FORMAT, "version": 1, "exported_at": payload.get("exported_at"),
        "note": "Encrypted Grace Treasury backup. Restore it in Grace Treasury with your backup passphrase.",
        "kdf": crypto["kdf"], "nonce": _b64e(nonce),
        "ciphertext": _b64e(AESGCM(crypto["key"]).encrypt(nonce, body, BACKUP_AAD)),
    }


def is_encrypted_backup(payload) -> bool:
    return isinstance(payload, dict) and payload.get("format") == BACKUP_FORMAT


async def decrypt_backup(envelope: dict, passphrase: Optional[str]) -> dict:
    if not passphrase:
        raise HTTPException(status_code=400, detail="This backup is encrypted. Enter its backup passphrase to restore it.")
    try:
        kdf = envelope["kdf"]
        key = await asyncio.to_thread(derive_backup_key, passphrase, _b64d(kdf["salt"]), int(kdf["n"]), int(kdf["r"]), int(kdf["p"]))
        plain = AESGCM(key).decrypt(_b64d(envelope["nonce"]), _b64d(envelope["ciphertext"]), BACKUP_AAD)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=400, detail="This encrypted backup file is damaged or incomplete")
    except Exception:  # InvalidTag: wrong passphrase or altered file
        raise HTTPException(status_code=400, detail="That passphrase doesn't match this backup (or the file was altered)")
    return json.loads(plain.decode("utf-8"))


async def build_export_payload() -> dict:
    """Everything needed to rebuild the treasury, minus server-only secrets (SMTP password, backup key)."""
    payload = {"version": 1, "app": "church-treasury", "exported_at": now_iso(), "data": {}}
    for coll in EXPORT_COLLECTIONS:
        docs = await db[coll].find({}, {"_id": 0}).to_list(100000)
        if coll == "settings":
            docs = [d for d in docs if d.get("id") not in SERVER_ONLY_SETTINGS]
            for d in docs:
                if d.get("id") == "email":
                    d.pop("smtp_password", None)
        payload["data"][coll] = docs
    return payload


async def build_backup_file() -> tuple:
    """(bytes, encrypted?) for a backup — encrypted whenever a passphrase is set."""
    payload = await build_export_payload()
    crypto = await get_backup_crypto()
    if crypto:
        return json.dumps(encrypt_backup(payload, crypto)).encode("utf-8"), True
    return json.dumps(payload, indent=2).encode("utf-8"), False


def backup_filename(encrypted: bool) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{BACKUP_PREFIX}{stamp}{'-enc' if encrypted else ''}.json"


async def apply_restore(payload, passphrase: Optional[str], actor: dict, request: Optional[Request], source: str) -> dict:
    if is_encrypted_backup(payload):
        payload = await decrypt_backup(payload, passphrase)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("users"), list) or len(data["users"]) == 0:
        raise HTTPException(status_code=400, detail="This is not a valid backup, or it has no users (restoring it would lock you out)")

    # Server-only secrets are never in a backup, so keep this server's copies.
    keep = {d["id"]: d for d in await db.settings.find({"id": {"$in": list(SERVER_ONLY_SETTINGS)}}, {"_id": 0}).to_list(10)}
    current_email = await db.settings.find_one({"id": "email"}, {"_id": 0}) or {}

    counts = {}
    for coll in EXPORT_COLLECTIONS:
        docs = data.get(coll)
        if not isinstance(docs, list):
            continue
        if coll == "settings":
            docs = [d for d in docs if isinstance(d, dict) and d.get("id") not in SERVER_ONLY_SETTINGS]
            for d in docs:
                if d.get("id") == "email":
                    # older backups may carry a plain-text password; otherwise keep the current one
                    d["smtp_password"] = seal(d.get("smtp_password") or "") or current_email.get("smtp_password", "")
        await db[coll].delete_many({})
        if docs:
            for d in docs:
                d.pop("_id", None)
            await db[coll].insert_many(docs)
        counts[coll] = len(docs)
    for doc in keep.values():
        await db.settings.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
    # Every session from before the restore ends now.
    await db.users.update_many({}, {"$inc": {"token_version": 1}})
    await audit(actor, "data.restore", None, source, request)
    return {"ok": True, "restored": counts}


@api_router.get("/data/export")
async def export_data(request: Request, user: dict = Depends(require_data)):
    body, encrypted = await build_backup_file()
    filename = backup_filename(encrypted)
    await audit(user, "data.export", None, f"{filename} ({'encrypted' if encrypted else 'NOT encrypted'})", request)
    return Response(content=body, media_type="application/json",
                    headers=private_download_headers(filename))


@api_router.post("/data/import")
async def import_data(request: Request, file: UploadFile = File(...), passphrase: Optional[str] = Form(None),
                      user: dict = Depends(require_admin)):
    try:
        payload = json.loads((await file.read()).decode("utf-8-sig", errors="replace"))
    except Exception:
        raise HTTPException(status_code=400, detail="This file is not a valid backup (JSON could not be read)")
    return await apply_restore(payload, passphrase, user, request, f"Uploaded file {os.path.basename(file.filename or '')}")


# ----------------------------- Backup encryption passphrase -----------------------------
@api_router.get("/settings/backup-encryption")
async def get_backup_encryption(user: dict = Depends(require_data)):
    doc = await db.settings.find_one({"id": "backup_encryption"}, {"_id": 0, "set_at": 1, "key": 1})
    return {"enabled": bool(doc and doc.get("key")), "set_at": (doc or {}).get("set_at")}


@api_router.put("/settings/backup-encryption")
async def set_backup_passphrase(data: PassphraseInput, request: Request, user: dict = Depends(require_data)):
    pw = data.passphrase or ""
    if len(pw) < MIN_PASSPHRASE:
        raise HTTPException(status_code=400, detail=f"Use a passphrase of at least {MIN_PASSPHRASE} characters (a few unrelated words works well)")
    salt = secrets.token_bytes(16)
    key = await asyncio.to_thread(derive_backup_key, pw, salt, **SCRYPT_PARAMS)
    existed = await db.settings.find_one({"id": "backup_encryption"})
    doc = {"id": "backup_encryption", "salt": _b64e(salt), **SCRYPT_PARAMS, "key": seal(_b64e(key)), "set_at": now_iso()}
    await db.settings.update_one({"id": "backup_encryption"}, {"$set": doc}, upsert=True)
    await audit(user, "backup.passphrase_changed" if existed else "backup.passphrase_set", None, "", request)
    return {"enabled": True, "set_at": doc["set_at"]}


# ----------------------------- Scheduled backups -----------------------------
BACKUP_PREFIX = "church-treasury-backup-"
DEFAULT_BACKUP_SETTINGS = {"id": "backup", "enabled": True, "time": "02:00", "retention": 14}
scheduler = AsyncIOScheduler()


class BackupSettings(BaseModel):
    enabled: bool = True
    time: str = "02:00"
    retention: int = 14


# Exactly the names this app writes: church-treasury-backup-YYYYMMDD-HHMMSS[-enc].json
BACKUP_NAME_RE = re.compile(r"church-treasury-backup-\d{8}-\d{6}(-enc)?\.json")


def find_backup(name: str) -> tuple:
    """Find a backup by name among the files actually in BACKUP_DIR.

    The request's name is only compared against the directory listing; the name and path
    returned come from the listing itself, so request data never becomes a file path. The
    match must be a regular file directly inside BACKUP_DIR (no symlinks, no subfolders)."""
    if not isinstance(name, str) or not BACKUP_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid backup file name")
    root = os.path.realpath(BACKUP_DIR)
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.name == name and entry.is_file(follow_symlinks=False):
                full = os.path.realpath(entry.path)
                if os.path.dirname(full) == root:
                    return entry.name, full
    raise HTTPException(status_code=404, detail="Backup not found")


def secure_backup_dir():
    try:
        os.chmod(BACKUP_DIR, 0o700)
    except OSError:
        pass


def write_private_file(path: str, data: bytes):
    """Write a file readable only by the app's own user (mode 600)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(path, 0o600)


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
    body, encrypted = await build_backup_file()
    fname = backup_filename(encrypted)
    write_private_file(os.path.join(BACKUP_DIR, fname), body)
    cfg = await get_backup_settings()
    apply_retention(int(cfg.get("retention", 14)))
    if not encrypted:
        logger.warning(f"Backup written WITHOUT encryption: {fname} — set a backup passphrase in Settings → Backup & Restore")
    else:
        logger.info(f"Encrypted backup written: {fname}")
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
        name = os.path.basename(path)
        out.append({
            "name": name,
            "size": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
            "encrypted": name.endswith("-enc.json"),
        })
    return out


@api_router.post("/backups/run")
async def run_backup_now(request: Request, user: dict = Depends(require_data)):
    name = await run_backup()
    await audit(user, "backup.run", None, name, request)
    return {"ok": True, "name": name, "encrypted": name.endswith("-enc.json")}


@api_router.get("/backups/{name}/download")
async def download_backup(name: str, request: Request, user: dict = Depends(require_data)):
    base, full = find_backup(name)
    with open(full, "rb") as f:
        content = f.read()
    await audit(user, "backup.download", None, base, request)
    return Response(content=content, media_type="application/json", headers=private_download_headers(base))


@api_router.delete("/backups/{name}")
async def delete_backup(name: str, request: Request, user: dict = Depends(require_data)):
    try:
        base, full = find_backup(name)
    except HTTPException as e:
        if e.status_code == 404:
            return {"ok": True}  # already gone
        raise
    os.remove(full)
    await audit(user, "backup.delete", None, base, request)
    return {"ok": True}


@api_router.post("/backups/{name}/restore")
async def restore_backup(name: str, request: Request, data: Optional[RestoreInput] = None, user: dict = Depends(require_admin)):
    base, full = find_backup(name)
    try:
        with open(full) as f:
            payload = json.load(f)
    except Exception:
        raise HTTPException(status_code=400, detail="This backup file could not be read")
    return await apply_restore(payload, (data.passphrase if data else None), user, request, f"Server backup {base}")


# ----------------------------- Email backups (SMTP) -----------------------------
DEFAULT_EMAIL_SETTINGS = {
    "id": "email", "enabled": False, "smtp_host": "", "smtp_port": 587,
    "smtp_username": "", "smtp_password": "", "use_tls": True,
    "from_address": "", "to_address": "", "notify_users": True,
}


# Standard mail-submission ports only, so the email settings can't be used to probe other services.
ALLOWED_SMTP_PORTS = {25, 465, 587, 2525}
_HOSTNAME_RE = re.compile(r"(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?")
_IPV4_RE = re.compile(r"\d{1,3}(\.\d{1,3}){3}")


def validate_smtp_target(host: str, port: int):
    if host and not (_HOSTNAME_RE.fullmatch(host) or _IPV4_RE.fullmatch(host)):
        raise HTTPException(status_code=400, detail="Enter just the mail server's name, e.g. smtp.gmail.com (no http:// or port)")
    if port not in ALLOWED_SMTP_PORTS:
        raise HTTPException(status_code=400, detail="Use a standard mail port: 587 (STARTTLS), 465 (SSL), 25 or 2525")


class DisallowedSmtpPort(Exception):
    pass


def friendly_smtp_error(e: Exception) -> str:
    """A helpful message for the admin; the technical details go only to the server log."""
    logger.warning(f"SMTP error: {type(e).__name__}: {e}")
    if isinstance(e, DisallowedSmtpPort):
        return "The saved mail port isn't allowed. Use 587 (STARTTLS), 465 (SSL), 25 or 2525, then save."
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "The mail server rejected the username or password. (For Gmail, use an app password.)"
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the recipient address."
    if isinstance(e, smtplib.SMTPSenderRefused):
        return "The mail server refused the From address. Many providers require it to match the username."
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return "This mail server doesn't support STARTTLS on that port. Use port 465 for SSL, or 587 with STARTTLS."
    if isinstance(e, ssl.SSLError):
        return "A secure connection couldn't be set up. Port 465 uses SSL; port 587 uses STARTTLS. Check the port and setting."
    if isinstance(e, socket.gaierror):
        return "Couldn't find that mail server. Check the SMTP host name."
    if isinstance(e, (TimeoutError, socket.timeout)):
        return "The mail server didn't respond in time. Check the host and port."
    if isinstance(e, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, ConnectionError, OSError)):
        return "Couldn't connect to the mail server. Check the host and port."
    if isinstance(e, smtplib.SMTPException):
        return "The mail server reported an error. The server log has the details."
    return "The email couldn't be sent. The server log has the details."


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: Optional[str] = None  # None/omitted = keep existing
    use_tls: bool = True
    from_address: str = ""
    to_address: str = ""
    notify_users: bool = True


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
    if port not in ALLOWED_SMTP_PORTS:
        raise DisallowedSmtpPort(f"Port {port} is not an allowed mail port")
    username = cfg.get("smtp_username") or ""
    password = unseal(cfg.get("smtp_password") or "")
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


# ----------------------------- Account-change email notices -----------------------------
NOTICE_TEXT = {
    "created": ("{church} treasury: your account was created",
                "{actor} created a Grace Treasury account for you ({email}) with the role: {detail}.\n\n"
                "They will give you a temporary password. You'll be asked to choose your own the first time you sign in."),
    "password_reset": ("{church} treasury: your password was reset",
                       "{actor} reset the password for your Grace Treasury account ({email}).\n\n"
                       "You have been signed out everywhere. Use the temporary password they give you, then choose a new one."),
    "role_change": ("{church} treasury: your access changed",
                    "{actor} changed your Grace Treasury role ({email}): {detail}.\n\nYou have been signed out and will need to sign in again."),
    "password_changed": ("{church} treasury: your password was changed",
                         "The password for your Grace Treasury account ({email}) was just changed, and other devices were signed out."),
}


_notice_tasks: set = set()


async def notify_account_change(kind: str, target: dict, actor: Optional[dict] = None, detail: str = ""):
    """Email the affected user about a change to their account, if SMTP is configured.
    Never includes passwords; failures are logged and never block the action."""
    to = (target or {}).get("email")
    if not to:
        return
    cfg = await get_email_settings()
    if not cfg.get("smtp_host") or cfg.get("notify_users", True) is False:
        return
    church = (await db.settings.find_one({"id": "church"}, {"_id": 0}) or {}).get("church_name") or "Church"
    subject_t, body_t = NOTICE_TEXT[kind]
    actor_name = (actor or {}).get("name") or (actor or {}).get("email") or "An administrator"
    when = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    fmt = {"church": church, "actor": actor_name, "email": to, "detail": detail}
    body = body_t.format(**fmt) + f"\n\nWhen: {when}\n\nIf you didn't expect this, contact your church administrator right away."

    async def _send():
        try:
            await asyncio.to_thread(_send_email_sync, {**cfg, "to_address": to}, subject_t.format(**fmt), body)
            logger.info(f"Account notice '{kind}' emailed to {to}")
        except Exception as e:
            logger.error(f"Account notice '{kind}' to {to} failed: {e}")
    task = asyncio.create_task(_send())  # don't make the admin wait on SMTP
    _notice_tasks.add(task)
    task.add_done_callback(_notice_tasks.discard)


async def maybe_email_backup(fname: str):
    cfg = await get_email_settings()
    if not cfg.get("enabled") or not cfg.get("smtp_host") or not cfg.get("to_address"):
        return
    if not fname.endswith("-enc.json"):
        logger.warning(f"Not emailing {fname}: backups are only emailed when encrypted. Set a backup passphrase.")
        return
    try:
        fname, full = find_backup(fname)
        with open(full, "rb") as f:
            data = f.read()
        church = await db.settings.find_one({"id": "church"}, {"_id": 0}) or {}
        name = church.get("church_name") or "Church Treasury"
        await asyncio.to_thread(
            _send_email_sync, cfg,
            f"{name} — Treasury backup {fname}",
            f"Attached is the automatic, encrypted database backup from {name}.\n\nFile: {fname}\n"
            "Keep it somewhere safe for off-site safekeeping. Restoring it requires the backup passphrase.",
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
        "notify_users": cfg.get("notify_users", True) is not False,
        "has_password": bool(cfg.get("smtp_password")),
    }


@api_router.put("/settings/email")
async def update_email_config(data: EmailConfig, request: Request, user: dict = Depends(require_data)):
    validate_smtp_target(data.smtp_host.strip(), int(data.smtp_port or 587))
    existing = await get_email_settings()
    if (existing.get("notify_users", True) is not False) != data.notify_users:
        await audit(user, "settings.account_notices", None, "Turned on" if data.notify_users else "Turned off", request)
    doc = {
        "id": "email",
        "enabled": data.enabled,
        "smtp_host": data.smtp_host.strip(),
        "smtp_port": int(data.smtp_port or 587),
        "smtp_username": data.smtp_username.strip(),
        "use_tls": data.use_tls,
        "from_address": data.from_address.strip(),
        "to_address": data.to_address.strip(),
        "notify_users": data.notify_users,
        "smtp_password": existing.get("smtp_password", "") if data.smtp_password in (None, "") else seal(data.smtp_password),
    }
    await db.settings.update_one({"id": "email"}, {"$set": doc}, upsert=True)
    labels = {"enabled": "backup emails", "smtp_host": "host", "smtp_port": "port", "smtp_username": "username",
              "use_tls": "STARTTLS", "from_address": "from", "to_address": "send to"}
    changes = [f"{label}: {existing.get(k, '') or '—'} → {doc[k] if doc[k] not in ('', None) else '—'}"
               for k, label in labels.items() if existing.get(k) != doc[k] and not (k == "smtp_port" and existing.get(k) in (None, "") and doc[k] == 587)]
    if doc["smtp_password"] != existing.get("smtp_password", ""):
        changes.append("password changed")
    if changes:
        await audit(user, "settings.email_changed", None, "; ".join(changes), request)
    return {"ok": True}


@api_router.post("/email/test")
async def send_test_email(request: Request, user: dict = Depends(require_data)):
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
        msg = friendly_smtp_error(e)
        await audit(user, "email.test", None, f"Failed to {cfg.get('to_address')} via {cfg.get('smtp_host')}:{cfg.get('smtp_port')}: {msg}", request)
        raise HTTPException(status_code=400, detail=msg)
    await audit(user, "email.test", None, f"Sent to {cfg.get('to_address')} via {cfg.get('smtp_host')}:{cfg.get('smtp_port')}", request)
    return {"ok": True}


@api_router.post("/backups/{name}/email")
async def email_backup(name: str, request: Request, user: dict = Depends(require_data)):
    base, full = find_backup(name)
    if not base.endswith("-enc.json"):
        raise HTTPException(status_code=400, detail="Only encrypted backups can be emailed. Set a backup passphrase, then use Back Up Now.")
    cfg = await get_email_settings()
    if not cfg.get("smtp_host") or not cfg.get("to_address"):
        raise HTTPException(status_code=400, detail="Email is not configured. Set it up under Email Backups first.")
    try:
        await maybe_email_backup_force(base, full, cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=friendly_smtp_error(e))
    await audit(user, "backup.email", None, f"{base} → {cfg.get('to_address')}", request)
    return {"ok": True}


async def maybe_email_backup_force(fname: str, full: str, cfg: dict):
    with open(full, "rb") as f:
        data = f.read()
    church = await db.settings.find_one({"id": "church"}, {"_id": 0}) or {}
    name = church.get("church_name") or "Church Treasury"
    await asyncio.to_thread(
        _send_email_sync, cfg,
        f"{name} — Treasury backup {fname}",
        f"Attached is an encrypted database backup from {name}.\n\nFile: {fname}\nRestoring it requires the backup passphrase.",
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
    await db.login_attempts.create_index("at", expireAfterSeconds=LOGIN_HISTORY_DAYS * 86400)
    await db.login_attempts.create_index([("email", 1), ("ip", 1), ("at", -1)])
    await db.login_attempts.create_index([("ip", 1), ("at", -1)])
    await db.audit_log.create_index([("at", -1)])


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

    # Church settings (blank, editable by the treasurer)
    if not await db.settings.find_one({"id": "church"}):
        await db.settings.insert_one({"id": "church", "church_name": "Your Church Name", "treasurer_name": "", "meeting_day": ""})


async def strip_admin_only_permissions():
    """Upgrade step: custom roles may no longer hold Administrator-only permissions."""
    async for role in db.roles.find({"is_system": {"$ne": True}, "permissions": {"$in": list(ADMIN_ONLY_PERMISSIONS)}}, {"_id": 0}):
        removed = sorted(set(role.get("permissions", [])) & ADMIN_ONLY_PERMISSIONS)
        await db.roles.update_one({"id": role["id"]}, {"$pull": {"permissions": {"$in": removed}}})
        await audit(None, "role.update", {"id": role["id"], "name": role.get("name", "")},
                    f"removed: {', '.join(removed)} (now Administrator-only)")
        logger.warning(f"Removed {removed} from role '{role.get('name')}' — user management is now Administrator-only")


async def seal_stored_secrets():
    """Upgrade step: encrypt an SMTP password stored in plain text by older versions."""
    doc = await db.settings.find_one({"id": "email"}, {"_id": 0, "smtp_password": 1})
    pw = (doc or {}).get("smtp_password") or ""
    if pw and not pw.startswith(SEALED_PREFIX):
        await db.settings.update_one({"id": "email"}, {"$set": {"smtp_password": seal(pw)}})
        logger.info("Encrypted the stored SMTP password")


async def startup():
    await ensure_indexes()
    try:
        await strip_admin_only_permissions()
    except Exception as e:
        logger.error(f"Role permission upgrade failed: {e}")
    try:
        await seal_stored_secrets()
    except Exception as e:
        logger.error(f"Sealing stored secrets failed: {e}")
    secure_backup_dir()
    try:
        await get_backup_settings()
        await reschedule_backup()
        if not scheduler.running:
            scheduler.start()
        logger.info("Backup scheduler started")
    except Exception as e:
        logger.error(f"Backup scheduler failed to start: {e}")


async def shutdown():
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()
