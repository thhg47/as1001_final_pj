"""API mẫu cho Parental Control App.

Chạy:      uvicorn main:app --reload --port 8080
Swagger:   http://127.0.0.1:8080/docs
"""
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()  # phải chạy trước khi import các module đọc biến môi trường

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import telegram_bot  # noqa: E402
from classifier import classify  # noqa: E402
from store import TIME_FMT, device_status, store, verify_password  # noqa: E402

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
TIME_RE = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await telegram_bot.start_bot()
    yield
    await telegram_bot.stop_bot()


app = FastAPI(title="Parental Control API (mẫu)", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api/v1")


# ---------- Schemas ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_RE, max_length=254)
    password: str = Field(min_length=6, max_length=16)


class LoginIn(BaseModel):
    email: str
    password: str


class PairIn(BaseModel):
    pin: str = Field(min_length=6, max_length=7, description="'739204' hoặc '739 204'")
    device_name: str = Field(min_length=1, max_length=100)
    os: str = Field("Android", max_length=50)


class DeviceUpdateIn(BaseModel):
    daily_limit_hours: int = Field(ge=1, le=12)


class HeartbeatIn(BaseModel):
    screen_time_minutes: int = Field(ge=0, le=1440)


class MessageIn(BaseModel):
    app: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=5000)
    timestamp: Optional[str] = Field(None, pattern=TIME_RE)


class CheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class UnlockIn(BaseModel):
    app: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    log_id: Optional[int] = None


class ResolveIn(BaseModel):
    decision: Literal["approved", "rejected"]


class RuleIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    level: Literal["Danger", "Warning"]


class SettingsIn(BaseModel):
    block_danger: bool
    warn_notify: bool
    danger_threshold: float = Field(ge=0, le=1)


# ---------- Helpers ----------
def bearer(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def current_user(authorization: str = Header(default="")) -> dict:
    user_id = store.tokens.get(bearer(authorization))
    if user_id is None:
        raise HTTPException(401, "Chưa đăng nhập hoặc token không hợp lệ")
    return store.users[user_id]


async def current_device(x_device_token: str = Header(default="")) -> dict:
    device_id = store.device_tokens.get(x_device_token)
    if device_id is None:
        raise HTTPException(401, "Thiết bị chưa ghép nối hoặc token không hợp lệ")
    return store.devices[device_id]


def require_text(text: str) -> None:
    if not text.strip():
        raise HTTPException(422, "Nội dung không được để trống")


def public_user(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"],
            "telegram_linked": u["telegram_chat_id"] is not None}


def public_device(d: dict) -> dict:
    return {
        "id": d["id"], "name": d["name"], "os": d["os"], "status": device_status(d),
        "screen_time_minutes": d["screen_time_minutes"],
        "daily_limit_hours": d["daily_limit_hours"],
        "last_seen": d["last_seen"].strftime(TIME_FMT) if d["last_seen"] else None,
        "paired_at": d["paired_at"],
    }


def strip_owner(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "user_id"}


def device_config(device: dict) -> dict:
    uid = device["user_id"]
    return {"daily_limit_hours": device["daily_limit_hours"],
            "settings": store.settings[uid], "rules": store.rules[uid]}


def owned_device(device_id: str, user: dict) -> dict:
    device = store.devices.get(device_id)
    if not device or device["user_id"] != user["id"]:
        raise HTTPException(404, "Không tìm thấy thiết bị")
    return device


# ---------- Auth ----------
@api.post("/auth/register", status_code=201, tags=["Auth"])
async def register(body: RegisterIn):
    pw = body.password
    if not (re.search(r"[A-Z]", pw) and re.search(r"\d", pw) and re.search(r"[^A-Za-z0-9]", pw)):
        raise HTTPException(422, "Mật khẩu cần ít nhất 1 chữ in hoa, 1 chữ số và 1 ký tự đặc biệt")
    email = body.email.strip().lower()
    if store.find_user(email):
        raise HTTPException(409, "Email này đã được đăng ký")
    return public_user(store.create_user(body.name.strip(), email, pw))


@api.post("/auth/login", tags=["Auth"])
async def login(body: LoginIn):
    user = store.find_user(body.email.strip())
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Email hoặc mật khẩu không chính xác")
    return {"token": store.issue_token(user["id"]), "user": public_user(user)}


@api.post("/auth/logout", status_code=204, tags=["Auth"])
async def logout(authorization: str = Header(default="")):
    store.tokens.pop(bearer(authorization), None)
    return Response(status_code=204)


@api.get("/auth/me", tags=["Auth"])
async def me(user: dict = Depends(current_user)):
    return public_user(user)


# ---------- Ghép nối & thiết bị ----------
@api.post("/pairing/pin", tags=["Ghép nối & thiết bị"])
async def create_pin(user: dict = Depends(current_user)):
    while True:
        pin = f"{secrets.randbelow(900000) + 100000}"
        if pin not in store.pins:
            break
    expires = store.put_code(store.pins, pin, user["id"])
    return {"pin": pin, "expires_at": expires.strftime(TIME_FMT)}


@api.post("/devices/pair", status_code=201, tags=["Ghép nối & thiết bị"])
async def pair_device(body: PairIn):
    user_id = store.take_code(store.pins, body.pin.replace(" ", ""))
    if user_id is None:
        raise HTTPException(400, "Mã PIN sai hoặc đã hết hạn")
    device = store.create_device(user_id, body.device_name.strip(), body.os.strip())
    return {"device_id": device["id"], "device_token": device["token"], "config": device_config(device)}


@api.get("/devices", tags=["Ghép nối & thiết bị"])
async def list_devices(user: dict = Depends(current_user)):
    return [public_device(d) for d in store.devices_of(user["id"])]


@api.patch("/devices/{device_id}", tags=["Ghép nối & thiết bị"])
async def update_device(device_id: str, body: DeviceUpdateIn, user: dict = Depends(current_user)):
    device = owned_device(device_id, user)
    device["daily_limit_hours"] = body.daily_limit_hours
    return public_device(device)


@api.delete("/devices/{device_id}", status_code=204, tags=["Ghép nối & thiết bị"])
async def unpair_device(device_id: str, user: dict = Depends(current_user)):
    device = owned_device(device_id, user)
    store.device_tokens.pop(device["token"], None)
    del store.devices[device_id]
    return Response(status_code=204)


# ---------- Thiết bị trẻ (Android) ----------
@api.post("/device/heartbeat", tags=["Thiết bị trẻ (Android)"])
async def heartbeat(body: HeartbeatIn, device: dict = Depends(current_device)):
    device["screen_time_minutes"] = body.screen_time_minutes
    device["last_seen"] = datetime.now()
    return device_config(device)


@api.get("/device/config", tags=["Thiết bị trẻ (Android)"])
async def get_device_config(device: dict = Depends(current_device)):
    device["last_seen"] = datetime.now()
    return device_config(device)


@api.post("/device/messages", tags=["Thiết bị trẻ (Android)"])
async def report_message(body: MessageIn, device: dict = Depends(current_device)):
    require_text(body.text)
    uid = device["user_id"]
    device["last_seen"] = datetime.now()
    result = await classify(body.text, store.rules[uid], store.settings[uid])
    entry = store.add_log(uid, device["id"], body.app.strip(), body.text, result, body.timestamp)
    if entry["label"] == 2 or (entry["label"] == 1 and store.settings[uid]["warn_notify"]):
        await telegram_bot.notify_log(uid, entry)
    return {"log_id": entry["id"], **result}


@api.post("/device/unlock-requests", status_code=201, tags=["Thiết bị trẻ (Android)"])
async def request_unlock(body: UnlockIn, device: dict = Depends(current_device)):
    req = store.create_unlock(device["user_id"], device["id"], body.app.strip(),
                              body.reason.strip(), body.log_id)
    await telegram_bot.notify_unlock(device["user_id"], req)
    return strip_owner(req)


@api.get("/device/unlock-requests/{req_id}", tags=["Thiết bị trẻ (Android)"])
async def unlock_status(req_id: str, device: dict = Depends(current_device)):
    req = store.unlock_requests.get(req_id)
    if not req or req["device_id"] != device["id"]:
        raise HTTPException(404, "Không tìm thấy yêu cầu")
    return strip_owner(req)


# ---------- Phụ huynh: nhật ký, thống kê, kiểm tra thủ công ----------
@api.get("/logs", tags=["Phụ huynh"])
async def list_logs(
    label: Optional[int] = Query(None, ge=0, le=2),
    date: Optional[str] = Query(None, pattern=DATE_RE),
    device_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(current_user),
):
    items = [
        e for e in store.logs_of(user["id"])
        if (label is None or e["label"] == label)
        and (date is None or e["timestamp"].startswith(date))
        and (device_id is None or e["device_id"] == device_id)
    ]
    return {"total": len(items), "items": [strip_owner(e) for e in items[:limit]]}


@api.get("/stats", tags=["Phụ huynh"])
async def stats(date: Optional[str] = Query(None, pattern=DATE_RE), user: dict = Depends(current_user)):
    logs = [e for e in store.logs_of(user["id"]) if date is None or e["timestamp"].startswith(date)]
    return {
        "date": date,
        "total": len(logs),
        "safe": sum(1 for e in logs if e["label"] == 0),
        "warning": sum(1 for e in logs if e["label"] == 1),
        "danger": sum(1 for e in logs if e["label"] == 2),
    }


@api.post("/predict", tags=["Phụ huynh"])
async def manual_check(body: CheckIn, user: dict = Depends(current_user)):
    require_text(body.text)
    uid = user["id"]
    result = await classify(body.text, store.rules[uid], store.settings[uid])
    entry = store.add_log(uid, None, "Kiểm tra thủ công", body.text, result)
    return {"log_id": entry["id"], **result}


# ---------- Phụ huynh: yêu cầu mở khóa ----------
@api.get("/unlock-requests", tags=["Phụ huynh"])
async def list_unlocks(
    status: Optional[Literal["pending", "approved", "rejected"]] = None,
    user: dict = Depends(current_user),
):
    items = [strip_owner(r) for r in store.unlock_requests.values()
             if r["user_id"] == user["id"] and (status is None or r["status"] == status)]
    return sorted(items, key=lambda r: r["created_at"], reverse=True)


@api.post("/unlock-requests/{req_id}/resolve", tags=["Phụ huynh"])
async def resolve_unlock(req_id: str, body: ResolveIn, user: dict = Depends(current_user)):
    req = store.unlock_requests.get(req_id)
    if not req or req["user_id"] != user["id"]:
        raise HTTPException(404, "Không tìm thấy yêu cầu")
    if req["status"] != "pending":
        raise HTTPException(409, "Yêu cầu này đã được xử lý")
    store.resolve_unlock(req, body.decision)
    return strip_owner(req)


# ---------- Phụ huynh: quy tắc & cài đặt ----------
@api.get("/rules", tags=["Quy tắc & cài đặt"])
async def list_rules(user: dict = Depends(current_user)):
    return store.rules[user["id"]]


@api.post("/rules", status_code=201, tags=["Quy tắc & cài đặt"])
async def add_rule(body: RuleIn, user: dict = Depends(current_user)):
    rules = store.rules[user["id"]]
    keyword = body.keyword.strip()
    if not keyword:
        raise HTTPException(422, "Từ khóa không được để trống")
    if any(r["keyword"].lower() == keyword.lower() for r in rules):
        raise HTTPException(409, "Từ khóa này đã có trong danh sách")
    rule = {"id": store.next_id(), "keyword": keyword, "level": body.level}
    rules.insert(0, rule)
    return rule


@api.delete("/rules/{rule_id}", status_code=204, tags=["Quy tắc & cài đặt"])
async def delete_rule(rule_id: int, user: dict = Depends(current_user)):
    rules = store.rules[user["id"]]
    remaining = [r for r in rules if r["id"] != rule_id]
    if len(remaining) == len(rules):
        raise HTTPException(404, "Không tìm thấy từ khóa")
    store.rules[user["id"]] = remaining
    return Response(status_code=204)


@api.get("/settings", tags=["Quy tắc & cài đặt"])
async def get_settings(user: dict = Depends(current_user)):
    return store.settings[user["id"]]


@api.put("/settings", tags=["Quy tắc & cài đặt"])
async def put_settings(body: SettingsIn, user: dict = Depends(current_user)):
    store.settings[user["id"]] = body.model_dump()
    return store.settings[user["id"]]


# ---------- Telegram ----------
@api.post("/telegram/link", tags=["Telegram"])
async def telegram_link(user: dict = Depends(current_user)):
    if not telegram_bot.is_enabled():
        raise HTTPException(503, "Server chưa cấu hình Telegram bot")
    code = secrets.token_urlsafe(16)
    expires = store.put_code(store.telegram_codes, code, user["id"])
    return {"url": telegram_bot.deep_link(code), "expires_at": expires.strftime(TIME_FMT)}


@api.delete("/telegram/link", status_code=204, tags=["Telegram"])
async def telegram_unlink(user: dict = Depends(current_user)):
    user["telegram_chat_id"] = None
    return Response(status_code=204)


@app.get("/health", tags=["Hệ thống"])
async def health():
    return {"status": "ok", "telegram_bot": telegram_bot.is_enabled()}


app.include_router(api)
