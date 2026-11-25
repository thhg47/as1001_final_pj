"""Telegram bot cho phụ huynh: nhận cảnh báo và duyệt yêu cầu mở khóa.

Bot chạy chung tiến trình với API (khởi động trong lifespan của FastAPI),
nên dùng chung kho dữ liệu `store`.
"""
import logging
import os
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from store import device_status, store

logger = logging.getLogger("telegram_bot")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
LEVEL_TEXT = {1: "🟠 CẢNH BÁO", 2: "🔴 NGUY HIỂM"}
HELP_TEXT = (
    "Các lệnh:\n"
    "/status – tình trạng thiết bị và thống kê hôm nay\n"
    "/pending – các yêu cầu mở khóa đang chờ\n"
    "/unlink – hủy liên kết tài khoản"
)

application: Application | None = None


def is_enabled() -> bool:
    return application is not None


def deep_link(code: str) -> str:
    return f"https://t.me/{application.bot.username}?start={code}"


def device_name(device_id: str | None) -> str:
    device = store.devices.get(device_id) if device_id else None
    return device["name"] if device else "Thiết bị"


def unlock_text(req: dict) -> str:
    return (
        f"🔓 Yêu cầu mở khóa – {device_name(req['device_id'])}\n"
        f"Ứng dụng: {req['app']}\n"
        f"Lý do: {req['reason']}\n"
        f"Lúc: {req['created_at']}"
    )


def unlock_buttons(req_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Mở khóa", callback_data=f"unlock:{req_id}:approved"),
        InlineKeyboardButton("❌ Từ chối", callback_data=f"unlock:{req_id}:rejected"),
    ]])


# ---------- Lệnh ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat_id = update.effective_chat.id

    if not context.args:
        user = store.user_by_chat(chat_id)
        if user:
            await msg.reply_text(f"Bạn đã liên kết với {user['email']}.\n\n{HELP_TEXT}")
        else:
            await msg.reply_text(
                "Xin chào! Hãy vào trang phụ huynh, bấm “Kết nối Telegram” "
                "rồi mở đường dẫn được tạo để liên kết tài khoản."
            )
        return

    user_id = store.take_code(store.telegram_codes, context.args[0])
    if user_id is None:
        await msg.reply_text("Mã liên kết không hợp lệ hoặc đã hết hạn. Hãy tạo mã mới trên trang phụ huynh.")
        return

    old = store.user_by_chat(chat_id)  # một chat chỉ gắn với một tài khoản
    if old:
        old["telegram_chat_id"] = None
    user = store.users[user_id]
    user["telegram_chat_id"] = chat_id
    await msg.reply_text(f"✅ Đã liên kết với tài khoản {user['email']}. Cảnh báo sẽ được gửi về đây.\n\n{HELP_TEXT}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = store.user_by_chat(update.effective_chat.id)
    if not user:
        await update.effective_message.reply_text("Chat này chưa liên kết tài khoản phụ huynh.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    logs = [e for e in store.logs_of(user["id"]) if e["timestamp"].startswith(today)]
    count = {lv: sum(1 for e in logs if e["label"] == lv) for lv in (0, 1, 2)}

    lines = ["📱 Thiết bị:"]
    devices = store.devices_of(user["id"])
    if not devices:
        lines.append("  (chưa ghép nối thiết bị nào)")
    for d in devices:
        lines.append(
            f"  • {d['name']} – {device_status(d)} – đã dùng {d['screen_time_minutes']} phút"
            f" / giới hạn {d['daily_limit_hours']} giờ"
        )
    lines.append(
        f"\n📊 Hôm nay: {len(logs)} lượt quét – an toàn {count[0]}, "
        f"cảnh báo {count[1]}, nguy hiểm {count[2]}"
    )
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = store.user_by_chat(update.effective_chat.id)
    if not user:
        await update.effective_message.reply_text("Chat này chưa liên kết tài khoản phụ huynh.")
        return
    pending = [r for r in store.unlock_requests.values()
               if r["user_id"] == user["id"] and r["status"] == "pending"]
    if not pending:
        await update.effective_message.reply_text("Không có yêu cầu mở khóa nào đang chờ.")
        return
    for req in pending:
        await update.effective_message.reply_text(unlock_text(req), reply_markup=unlock_buttons(req["id"]))


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = store.user_by_chat(update.effective_chat.id)
    if user:
        user["telegram_chat_id"] = None
    await update.effective_message.reply_text("Đã hủy liên kết. Bạn sẽ không nhận cảnh báo nữa.")


async def on_unlock_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    try:
        _, req_id, decision = query.data.split(":")
    except ValueError:
        await query.answer()
        return

    user = store.user_by_chat(update.effective_chat.id)
    req = store.unlock_requests.get(req_id)
    if not user or not req or req["user_id"] != user["id"] or decision not in ("approved", "rejected"):
        await query.answer("Không tìm thấy yêu cầu này.", show_alert=True)
        return
    if req["status"] != "pending":
        await query.answer("Yêu cầu này đã được xử lý trước đó.", show_alert=True)
        return

    store.resolve_unlock(req, decision)
    await query.answer("Đã lưu quyết định.")
    result = "✅ Đã cho phép mở khóa" if decision == "approved" else "❌ Đã từ chối"
    await query.edit_message_text(f"{unlock_text(req)}\n\n{result}")


# ---------- Gửi thông báo (được gọi từ API) ----------
async def send(user_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    if application is None:
        return
    chat_id = store.users[user_id]["telegram_chat_id"]
    if chat_id is None:
        return
    try:
        await application.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    except TelegramError as exc:
        logger.warning("Không gửi được tin Telegram: %s", exc)


async def notify_log(user_id: int, entry: dict) -> None:
    content = entry["text"] if len(entry["text"]) <= 500 else entry["text"][:500] + "…"
    conf = (f"{entry['confidence'] * 100:.2f}% (AI)"
            if entry["confidence"] is not None else "khớp từ khóa")
    await send(user_id, (
        f"{LEVEL_TEXT[entry['label']]} – {device_name(entry['device_id'])}\n"
        f"Ứng dụng: {entry['app']}\n"
        f"Nội dung: {content}\n"
        f"Độ tin cậy: {conf}\n"
        f"Xử lý: {entry['action']}\n"
        f"Lúc: {entry['timestamp']}"
    ))


async def notify_unlock(user_id: int, req: dict) -> None:
    await send(user_id, unlock_text(req), unlock_buttons(req["id"]))


# ---------- Khởi động / dừng ----------
async def start_bot() -> None:
    global application
    if not TOKEN:
        logger.warning("Chưa đặt TELEGRAM_BOT_TOKEN – API vẫn chạy nhưng không có Telegram bot.")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("unlink", cmd_unlink))
    app.add_handler(CallbackQueryHandler(on_unlock_button, pattern=r"^unlock:"))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    application = app
    logger.info("Telegram bot @%s đang chạy", app.bot.username)


async def stop_bot() -> None:
    if application is None:
        return
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
