# Tài liệu API Backend – Parental Control App

Phiên bản 0.1 (API mẫu) · Cập nhật 25/11/2026 · Người phụ trách: backend

> Tài liệu kỹ thuật bên trong backend (kiến trúc, luồng xử lý, cách mở rộng): xem
> [`../docs/backend.md`](../docs/backend.md).

## 1. Tổng quan

```
[App Android của trẻ] ──X-Device-Token──▶ [Backend :8080] ◀──Bearer token── [Web phụ huynh]
                                              │        │
                                   POST /predict      Telegram Bot API
                                              ▼        ▼
                                   [AI service :8000]  [Telegram của phụ huynh]
```

- App Android gửi nội dung quét được lên backend. Backend gọi AI, kết hợp với
  từ khóa của phụ huynh, trả về hành động (chặn / cảnh báo / cho phép), lưu nhật ký
  và gửi cảnh báo Telegram.
- Web phụ huynh và app Android **chỉ gọi backend**, không gọi thẳng AI service.
- Base URL: `http://<IP máy chạy backend>:8080/api/v1`
- Thử API trực tiếp: `http://<IP>:8080/docs` (Swagger, bấm "Try it out").

## 2. Chạy thử và dữ liệu demo

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env  → điền TELEGRAM_BOT_TOKEN
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

Chạy AI service ở cổng 8000 (`uvicorn ai_service:app --port 8000`). Nếu AI không chạy,
backend vẫn hoạt động nhưng chỉ phân loại bằng từ khóa.

| Dữ liệu demo | Giá trị |
|---|---|
| Tài khoản phụ huynh | `parent@parentalcontrol.vn` / `Parent@123` |
| Thiết bị demo | `DEV-8841`, token `demo-device-token` |
| Nhật ký mẫu | 6 bản ghi giống `mock_data.json`, 1 yêu cầu mở khóa đang chờ |

Dữ liệu nằm trong bộ nhớ: tắt server là mất hết, khởi động lại thì dữ liệu demo được nạp lại.

## 3. Quy ước chung

**Xác thực**

| Ai gọi | Header |
|---|---|
| Web phụ huynh | `Authorization: Bearer <token>` (lấy từ `/auth/login`) |
| App Android | `X-Device-Token: <device_token>` (lấy từ `/devices/pair`) |

**Định dạng**

- JSON, UTF-8. Thời gian dạng `"YYYY-MM-DD HH:MM"` theo giờ server; ngày dạng `YYYY-MM-DD`.
- Nhãn `label`: `0` = Safe (an toàn), `1` = Warning (cảnh báo), `2` = Danger (nguy hiểm).
- `source`: `ai` (mô hình quyết định), `rules` (từ khóa quyết định, hoặc AI không chạy), `demo`.
- `confidence`: số từ 0 đến 1 **chỉ khi `source = "ai"`**; ngược lại là `null`
  → giao diện hiển thị "—", không tự bịa số.

**Hành động `action`** (backend quyết định, Android chỉ việc làm theo)

| label | Điều kiện | action | Android cần làm |
|---|---|---|---|
| 2 | `block_danger` bật và (confidence ≥ `danger_threshold` hoặc khớp từ khóa) | `Blocked` | Hiện màn hình khóa (overlay) |
| 2 | Các trường hợp còn lại | `Warned` | Không chặn |
| 1 | `warn_notify` bật | `Warned` | Không chặn |
| 1 | `warn_notify` tắt | `Logged` | Không làm gì |
| 0 | | `Allowed` | Không làm gì |

Cách kết hợp: lấy nhãn của AI; nếu từ khóa của phụ huynh cho nhãn **cao hơn** thì dùng nhãn
từ khóa. Mặc định `danger_threshold = 0.75`.

**Lỗi**: luôn có dạng `{"detail": "..."}` (riêng lỗi 422 do sai kiểu dữ liệu thì `detail` là một danh sách).

| Mã | Ý nghĩa |
|---|---|
| 400 | PIN sai hoặc hết hạn |
| 401 | Thiếu hoặc sai token |
| 404 | Không tìm thấy (hoặc không thuộc tài khoản của bạn) |
| 409 | Trùng (email đã đăng ký, từ khóa đã có, yêu cầu đã xử lý) |
| 422 | Dữ liệu gửi lên không hợp lệ |
| 503 | Server chưa cấu hình Telegram bot |

## 4. Danh sách endpoint

Tất cả đường dẫn đều có tiền tố `/api/v1` (trừ `/health`).

**Auth**

| Phương thức | Đường dẫn | Ai gọi | Xác thực | Mô tả |
|---|---|---|---|---|
| POST | `/auth/register` | Web | – | Đăng ký (`name`, `email`, `password` 6–16 ký tự, có chữ hoa, số, ký tự đặc biệt) |
| POST | `/auth/login` | Web | – | Đăng nhập, nhận `token` |
| POST | `/auth/logout` | Web | Bearer | Hủy token |
| GET | `/auth/me` | Web | Bearer | Thông tin tài khoản |

**Ghép nối & thiết bị**

| Phương thức | Đường dẫn | Ai gọi | Xác thực | Mô tả |
|---|---|---|---|---|
| POST | `/pairing/pin` | Web | Bearer | Tạo PIN 6 số, hạn 10 phút, dùng 1 lần |
| POST | `/devices/pair` | Android | – | Gửi PIN, nhận `device_token` |
| GET | `/devices` | Web | Bearer | Danh sách thiết bị |
| PATCH | `/devices/{device_id}` | Web | Bearer | Đổi `daily_limit_hours` (1–12) |
| DELETE | `/devices/{device_id}` | Web | Bearer | Hủy ghép nối |

**Thiết bị trẻ (Android)**

| Phương thức | Đường dẫn | Xác thực | Mô tả |
|---|---|---|---|
| POST | `/device/messages` | Device | Gửi nội dung quét được, nhận kết quả và `action` |
| POST | `/device/heartbeat` | Device | Báo thời gian dùng máy, nhận cấu hình mới nhất |
| GET | `/device/config` | Device | Lấy cấu hình (giới hạn giờ, settings, từ khóa) |
| POST | `/device/unlock-requests` | Device | Xin mở khóa |
| GET | `/device/unlock-requests/{id}` | Device | Hỏi trạng thái yêu cầu |

**Phụ huynh**

| Phương thức | Đường dẫn | Xác thực | Mô tả |
|---|---|---|---|
| GET | `/logs?label=&date=&device_id=&limit=` | Bearer | Nhật ký, mới nhất trước (`limit` mặc định 50) |
| GET | `/stats?date=` | Bearer | Đếm theo nhãn; không có `date` thì đếm tất cả |
| POST | `/predict` | Bearer | Kiểm tra thủ công một câu (có ghi nhật ký, không gửi Telegram) |
| GET | `/unlock-requests?status=` | Bearer | Danh sách yêu cầu mở khóa (`pending`/`approved`/`rejected`) |
| POST | `/unlock-requests/{id}/resolve` | Bearer | Duyệt: `{"decision": "approved" \| "rejected"}` |
| GET / POST | `/rules` | Bearer | Xem / thêm từ khóa (`keyword`, `level`: `Danger` \| `Warning`) |
| DELETE | `/rules/{rule_id}` | Bearer | Xóa từ khóa |
| GET / PUT | `/settings` | Bearer | Xem / cập nhật `block_danger`, `warn_notify`, `danger_threshold` |
| POST | `/telegram/link` | Bearer | Tạo link liên kết Telegram (hạn 10 phút) |
| DELETE | `/telegram/link` | Bearer | Hủy liên kết Telegram |

**Hệ thống**: `GET /health` → `{"status": "ok", "telegram_bot": true}`

## 5. Ví dụ request / response

**Đăng nhập** – `POST /api/v1/auth/login`

```json
{ "email": "parent@parentalcontrol.vn", "password": "Parent@123" }
```
```json
{
  "token": "q8Zx...",
  "user": { "id": 101, "name": "Demo", "email": "parent@parentalcontrol.vn", "telegram_linked": false }
}
```

**Ghép nối thiết bị** – `POST /api/v1/devices/pair` (không cần token)

```json
{ "pin": "739204", "device_name": "Galaxy A15 - Minh", "os": "Android 14" }
```
```json
{
  "device_id": "DEV-5127",
  "device_token": "kP3...",
  "config": { "daily_limit_hours": 3, "settings": { "...": "..." }, "rules": [] }
}
```

**Gửi nội dung quét được** – `POST /api/v1/device/messages`, header `X-Device-Token: demo-device-token`

```json
{ "app": "Messenger", "text": "Tan học mày đợi đấy, tao gọi người chặn đánh" }
```
```json
{
  "log_id": 120,
  "label": 2,
  "category": "Danger",
  "confidence": 0.9642,
  "source": "ai",
  "action": "Blocked"
}
```
`timestamp` là tùy chọn; không gửi thì backend dùng giờ hiện tại.

**Heartbeat** – `POST /api/v1/device/heartbeat`

```json
{ "screen_time_minutes": 105 }
```
```json
{
  "daily_limit_hours": 3,
  "settings": { "block_danger": true, "warn_notify": true, "danger_threshold": 0.75 },
  "rules": [ { "id": 102, "keyword": "chặn đánh", "level": "Danger" } ]
}
```

**Xin mở khóa** – `POST /api/v1/device/unlock-requests`

```json
{ "app": "Messenger", "reason": "Bạn con trêu đùa thôi ạ", "log_id": 120 }
```
```json
{
  "id": "REQ-121", "device_id": "DEV-8841", "app": "Messenger",
  "reason": "Bạn con trêu đùa thôi ạ", "log_id": 120,
  "created_at": "2026-11-25 15:30", "status": "pending", "resolved_at": null
}
```
Sau đó Android gọi `GET /device/unlock-requests/REQ-121` mỗi 5 giây cho tới khi
`status` khác `pending`.

**Nhật ký** – `GET /api/v1/logs?label=2&limit=20`

```json
{
  "total": 2,
  "items": [
    {
      "id": 111, "device_id": "DEV-8841", "timestamp": "2026-11-21 19:05",
      "app": "Messenger", "text": "Tan học mày đợi đấy, tao gọi người chặn đánh",
      "label": 2, "category": "Danger", "confidence": 0.9642,
      "source": "demo", "action": "Blocked"
    }
  ]
}
```

**Thiết bị** – `GET /api/v1/devices`

```json
[
  {
    "id": "DEV-8841", "name": "Galaxy A15 - Minh", "os": "Android 14",
    "status": "online", "screen_time_minutes": 105, "daily_limit_hours": 3,
    "last_seen": "2026-11-25 15:29", "paired_at": "2026-11-25 15:00"
  }
]
```
`status = "online"` khi thiết bị gửi heartbeat trong vòng 2 phút gần nhất.

**Lỗi**

```json
{ "detail": "Mã PIN sai hoặc đã hết hạn" }
```

## 6. Telegram bot

**Liên kết tài khoản**
1. Trên web, phụ huynh bấm "Kết nối Telegram", web gọi `POST /telegram/link` và nhận `url`.
2. Mở `url` (dạng `https://t.me/<tên_bot>?start=<mã>`) rồi bấm **Start**.
3. Bot xác nhận đã liên kết. `GET /auth/me` sẽ trả `telegram_linked: true`.

**Lệnh**: `/status` (thiết bị và thống kê hôm nay), `/pending` (yêu cầu mở khóa đang chờ),
`/unlink`, `/help`.

**Thông báo tự động**
- Nội dung **Nguy hiểm**: luôn gửi.
- Nội dung **Cảnh báo**: gửi nếu `warn_notify` bật.
- **Yêu cầu mở khóa**: luôn gửi, kèm hai nút ✅ Mở khóa / ❌ Từ chối. Bấm nút
  có tác dụng giống `POST /unlock-requests/{id}/resolve`.
- Kiểm tra thủ công trên web: không gửi.

## 7. Việc của từng phần để tích hợp

**Web phụ huynh**
- Bỏ `localStorage` cho tài khoản và dữ liệu. Đăng nhập bằng `/auth/login`, lưu `token`
  vào `sessionStorage`, và gửi header `Authorization` trong mọi request.
- Thay `AI_API_URL` bằng `POST /api/v1/predict`.
- Nhật ký lấy từ `GET /logs` (mảng nằm trong `items`). KPI lấy từ `GET /stats?date=<hôm nay>`.
- PIN: `POST /pairing/pin`. Thiết bị: `GET /devices`. Mở khóa: `GET /unlock-requests?status=pending`
  rồi gọi `resolve`. Bảng quy tắc và hai ô tick: `/rules`, `/settings`.
- Đổi tên trường: `screenTimeToday` → `screen_time_minutes` (phút), `dailyLimitHours` →
  `daily_limit_hours`, `time` (mở khóa) → `created_at`.
- `confidence` có thể là `null`, khi đó hiển thị "—".
- Hiển thị nội dung tin nhắn bằng `textContent` (không dùng `innerHTML`) để tránh XSS.

**App Android**
- Màn hình nhập PIN gọi `POST /devices/pair`, lưu `device_token` (nên dùng EncryptedSharedPreferences).
  Trước khi làm xong màn hình này, có thể dùng `demo-device-token` để thử.
- Gửi heartbeat mỗi 60 giây và áp dụng cấu hình nhận về.
- Mỗi nội dung quét được gửi qua `POST /device/messages`; khi `action = "Blocked"` thì hiện overlay khóa.
- Nút xin mở khóa: `POST /device/unlock-requests`, rồi hỏi lại trạng thái mỗi 5 giây.
- Địa chỉ backend: máy ảo dùng `http://10.0.2.2:8080`; máy thật dùng IP LAN của máy chạy
  backend (cùng Wi‑Fi). Android 9 trở lên chặn HTTP thường, cần bật
  `android:usesCleartextTraffic="true"` cho bản demo.

**AI service**
- Giữ nguyên định dạng `POST /predict` → `{"label": 0|1|2, "confidence": 0..1}`, chạy ở cổng 8000.
- Backend gọi AI từ phía server nên phần AI không cần bật CORS cho web nữa.
- Khi lỗi, nên trả mã HTTP 4xx/5xx (đừng trả 200 kèm `error`).

## 8. Giới hạn của bản mẫu

- Dữ liệu lưu trong bộ nhớ, mất khi tắt server.
- Token đăng nhập không hết hạn. Mật khẩu đã được băm (PBKDF2).
- Chạy HTTP, chưa có HTTPS.
- Bot dùng polling: **mỗi token bot chỉ được chạy ở một nơi tại một thời điểm**
  (hai máy cùng chạy sẽ báo lỗi Conflict).
- Android hỏi trạng thái mở khóa bằng polling, chưa có push notification.
