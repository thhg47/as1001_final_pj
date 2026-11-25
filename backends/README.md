# Backend – Parental Control App

API trung gian giữa **web phụ huynh**, **app Android của trẻ**, **AI service** và **Telegram bot**.
Viết bằng FastAPI (cùng công nghệ với `ai_service.py`).

| Thành phần | Cổng |
|---|---|
| Backend (thư mục này) | `8080` |
| AI service (`ai_service.py`) | `8000` |

## Chạy nhanh

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

Sau đó mở **http://127.0.0.1:8080/docs** để thử API ngay trên trình duyệt (Swagger).

- Không cần AI service vẫn chạy được; khi đó backend chỉ phân loại bằng từ khóa.
- Không cần Telegram token vẫn chạy được; khi đó chỉ không có bot (`/telegram/link` trả 503).
- Tài khoản demo: `parent@parentalcontrol.vn` / `Parent@123`. Token thiết bị demo: `demo-device-token`.

## Cấu trúc

| File | Vai trò |
|---|---|
| `main.py` | Khởi tạo FastAPI, CORS, schema request, toàn bộ endpoint `/api/v1/...` |
| `store.py` | Kho dữ liệu trong bộ nhớ + dữ liệu demo + băm mật khẩu |
| `classifier.py` | Gọi AI service, so khớp từ khóa, quyết định `Blocked` / `Warned` / `Logged` / `Allowed` |
| `telegram_bot.py` | Bot Telegram: liên kết tài khoản, gửi cảnh báo, nút duyệt mở khóa |
| `.env.example` | Mẫu biến môi trường (chép thành `.env`) |
| `API.md` | **Tài liệu API cho cả nhóm** (endpoint, ví dụ, việc của từng phần) |

Tài liệu kỹ thuật chi tiết (kiến trúc, luồng xử lý, mô hình dữ liệu, cách kiểm thử và mở rộng):
[`../docs/backend.md`](../docs/backend.md).

> ⚠️ File `.env` chứa token bot – **không commit**. `.gitignore` đã loại trừ sẵn.
