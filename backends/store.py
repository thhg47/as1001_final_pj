"""Kho dữ liệu trong bộ nhớ cho API mẫu.

Dữ liệu mất khi tắt server; dữ liệu demo được nạp lại mỗi lần khởi động.
Khi cần lưu lâu dài, chỉ cần thay lớp Store bằng SQLite/PostgreSQL.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

CATEGORIES = {0: "Safe", 1: "Warning", 2: "Danger"}
DEFAULT_SETTINGS = {"block_danger": True, "warn_notify": True, "danger_threshold": 0.75}
DEFAULT_RULES = [("chặn đánh", "Danger"), ("hack facebook", "Danger"), ("đồ ngu", "Warning")]
DEMO_EMAIL = "parent@parentalcontrol.vn"
DEMO_PASSWORD = "Parent@123"
DEMO_DEVICE_TOKEN = "demo-device-token"
ONLINE_WINDOW = timedelta(minutes=2)
TIME_FMT = "%Y-%m-%d %H:%M"


def now_str() -> str:
    return datetime.now().strftime(TIME_FMT)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt = stored.split("$", 1)[0]
    return secrets.compare_digest(hash_password(password, salt), stored)


def device_status(device: dict) -> str:
    last = device["last_seen"]
    return "online" if last and datetime.now() - last < ONLINE_WINDOW else "offline"


class Store:
    def __init__(self):
        self.users: dict[int, dict] = {}
        self.tokens: dict[str, int] = {}           # token đăng nhập -> user_id
        self.pins: dict[str, dict] = {}            # PIN ghép nối -> {user_id, expires_at}
        self.telegram_codes: dict[str, dict] = {}  # mã liên kết Telegram -> {user_id, expires_at}
        self.devices: dict[str, dict] = {}         # device_id -> thiết bị
        self.device_tokens: dict[str, str] = {}    # token thiết bị -> device_id
        self.logs: list[dict] = []                 # nhật ký, mới nhất ở đầu
        self.unlock_requests: dict[str, dict] = {}
        self.rules: dict[int, list[dict]] = {}     # user_id -> danh sách từ khóa
        self.settings: dict[int, dict] = {}        # user_id -> cấu hình
        self._seq = 100
        self._seed_demo()

    def next_id(self) -> int:
        self._seq += 1
        return self._seq

    # ---------- Phụ huynh ----------
    def create_user(self, name: str, email: str, password: str) -> dict:
        uid = self.next_id()
        user = {
            "id": uid, "name": name, "email": email.lower(),
            "password_hash": hash_password(password), "telegram_chat_id": None,
        }
        self.users[uid] = user
        self.rules[uid] = [{"id": self.next_id(), "keyword": k, "level": lv} for k, lv in DEFAULT_RULES]
        self.settings[uid] = dict(DEFAULT_SETTINGS)
        return user

    def find_user(self, email: str) -> dict | None:
        email = email.lower()
        return next((u for u in self.users.values() if u["email"] == email), None)

    def user_by_chat(self, chat_id: int) -> dict | None:
        return next((u for u in self.users.values() if u["telegram_chat_id"] == chat_id), None)

    def issue_token(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self.tokens[token] = user_id
        return token

    # ---------- Mã dùng một lần (PIN ghép nối, mã liên kết Telegram) ----------
    @staticmethod
    def put_code(table: dict, code: str, user_id: int, minutes: int = 10) -> datetime:
        expires = datetime.now() + timedelta(minutes=minutes)
        table[code] = {"user_id": user_id, "expires_at": expires}
        return expires

    @staticmethod
    def take_code(table: dict, code: str) -> int | None:
        """Lấy và xóa mã; trả về user_id nếu mã còn hạn."""
        entry = table.pop(code, None)
        if entry and entry["expires_at"] > datetime.now():
            return entry["user_id"]
        return None

    # ---------- Thiết bị ----------
    def create_device(self, user_id: int, name: str, os_name: str,
                      device_id: str | None = None, token: str | None = None) -> dict:
        while device_id is None or device_id in self.devices:
            device_id = f"DEV-{secrets.randbelow(9000) + 1000}"
        token = token or secrets.token_urlsafe(32)
        device = {
            "id": device_id, "user_id": user_id, "name": name, "os": os_name,
            "token": token, "daily_limit_hours": 3, "screen_time_minutes": 0,
            "last_seen": None, "paired_at": now_str(),
        }
        self.devices[device_id] = device
        self.device_tokens[token] = device_id
        return device

    def devices_of(self, user_id: int) -> list[dict]:
        return [d for d in self.devices.values() if d["user_id"] == user_id]

    # ---------- Nhật ký & mở khóa ----------
    def add_log(self, user_id: int, device_id: str | None, app: str, text: str,
                result: dict, timestamp: str | None = None) -> dict:
        entry = {
            "id": self.next_id(), "user_id": user_id, "device_id": device_id,
            "timestamp": timestamp or now_str(), "app": app, "text": text, **result,
        }
        self.logs.insert(0, entry)
        return entry

    def logs_of(self, user_id: int) -> list[dict]:
        return [e for e in self.logs if e["user_id"] == user_id]

    def create_unlock(self, user_id: int, device_id: str, app: str, reason: str,
                      log_id: int | None = None) -> dict:
        req = {
            "id": f"REQ-{self.next_id()}", "user_id": user_id, "device_id": device_id,
            "app": app, "reason": reason, "log_id": log_id, "created_at": now_str(),
            "status": "pending", "resolved_at": None,
        }
        self.unlock_requests[req["id"]] = req
        return req

    def resolve_unlock(self, req: dict, decision: str) -> None:
        req["status"] = decision
        req["resolved_at"] = now_str()

    # ---------- Dữ liệu demo (giống mock_data.json) ----------
    def _seed_demo(self) -> None:
        user = self.create_user("Demo", DEMO_EMAIL, DEMO_PASSWORD)
        uid = user["id"]
        self.rules[uid].append({"id": self.next_id(), "keyword": "bẩn bựa", "level": "Warning"})
        dev = self.create_device(uid, "Galaxy A15 - Minh", "Android 14",
                                 device_id="DEV-8841", token=DEMO_DEVICE_TOKEN)
        dev["screen_time_minutes"] = 105
        samples = [  # mới nhất trước
            ("2026-11-21 19:05", "Messenger", "Tan học mày đợi đấy, tao gọi người chặn đánh", 2, 0.9642, "Blocked"),
            ("2026-11-21 18:40", "Zalo", "Đồ ngu, có mỗi bài Toán dễ thế này mà cũng làm sai", 1, 0.8815, "Warned"),
            ("2026-11-21 17:15", "YouTube", "Hôm nay lớp con có bài kiểm tra Toán", 0, 0.9910, "Allowed"),
            ("2026-11-21 16:02", "Facebook", "Tao hack Facebook của mày bây giờ", 2, 0.9480, "Blocked"),
            ("2026-11-21 14:50", "TikTok", "Thằng này bẩn bựa vãi, đừng có chơi cùng nó", 1, 0.8530, "Warned"),
            ("2026-11-21 13:20", "Zalo", "Tối nay tớ qua nhà cậu lấy vở nhé", 0, 0.9854, "Allowed"),
        ]
        for ts, app, text, label, conf, action in reversed(samples):
            self.add_log(uid, dev["id"], app, text, {
                "label": label, "category": CATEGORIES[label],
                "confidence": conf, "source": "demo", "action": action,
            }, ts)
        self.create_unlock(uid, dev["id"], "Messenger",
                           "Con đang nhắn tin hỏi bài nhóm bạn, tin nhắn kia là bạn trêu đùa ạ.")


store = Store()
