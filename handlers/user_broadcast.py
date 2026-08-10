import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import database as db
from config import BROADCAST_DELAY
from services.telegram_client import send_message_to, is_connected
from services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

WAIT_USER_MESSAGE, CONFIRM_USER_BROADCAST = range(40, 42)

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


async def user_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    lic = db.get_license(user_id)
    if not lic or not db.is_license_active(user_id):
        await query.edit_message_text(
            "╭─ ⚠️ LISENSI TIDAK AKTIF\n"
            "│\n"
            "│ Lisensi kamu sudah habis atau belum aktif.\n"
            "╰─ Silakan order untuk melanjutkan.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
            ]),
        )
        return ConversationHandler.END

    max_grup = lic["max_grup"]
    targets = db.get_active_targets()
    available = len(targets)
    use_count = min(max_grup, available)

    context.user_data["ub_max_grup"] = max_grup
    context.user_data["ub_use_count"] = use_count

    await query.edit_message_text(
        f"╭─ 📢 BROADCAST\n"
        f"│\n"
        f"│ 🎫 Paket    : {lic['paket']}\n"
        f"│ 👥 Max Grup : {max_grup}\n"
        f"│ 📊 Tersedia : {available} grup\n"
        f"│ 🚀 Akan kirim ke {use_count} grup\n"
        f"│\n"
        f"╰─ Ketik pesan yang ingin dibroadcast 👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Batal", callback_data="cb_dashboard")]
        ]),
    )
    return WAIT_USER_MESSAGE


async def wait_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message.text.strip()
    if len(message) > 4096:
        await update.message.reply_text("❌ Pesan terlalu panjang (maks 4096 karakter).")
        return WAIT_USER_MESSAGE

    context.user_data["ub_message"] = message
    use_count = context.user_data.get("ub_use_count", 0)

    preview = message if len(message) <= 200 else message[:200] + "..."

    await update.message.reply_text(
        f"╭─ 📢 PREVIEW BROADCAST\n"
        f"│\n"
        f"│ Pesan:\n"
        f"│  {preview}\n"
        f"│\n"
        f"│ Akan dikirim ke {use_count} grup.\n"
        f"╰─ Konfirmasi kirim?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 KIRIM", callback_data="ub_confirm"),
                InlineKeyboardButton("❌ BATAL", callback_data="cb_dashboard"),
            ]
        ]),
    )
    return CONFIRM_USER_BROADCAST


async def confirm_user_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    message   = context.user_data.get("ub_message", "")
    use_count = context.user_data.get("ub_use_count", 0)
    user_id   = query.from_user.id

    if not message or not use_count:
        await query.edit_message_text("❌ Data tidak valid.", reply_markup=_BACK_BTN)
        return ConversationHandler.END

    targets = db.get_active_targets()[:use_count]
    status_msg = await query.edit_message_text(
        f"📢 Memulai broadcast ke *{use_count}* grup...",
        parse_mode="Markdown",
    )

    context.user_data.clear()
    context.application.create_task(
        _run_user_broadcast(message, targets, status_msg, user_id)
    )
    return ConversationHandler.END


async def _run_user_broadcast(message: str, targets, status_msg, user_id: int) -> None:
    rate = RateLimiter()
    success = failed = 0
    total = len(targets)
    last_edit = [0.0]

    # Simpan ke DB
    broadcast_id = db.create_broadcast(message, test_mode=False)
    db.start_broadcast(broadcast_id)
    for target in targets:
        db.add_broadcast_target(broadcast_id, target["id"])

    for i, target in enumerate(targets):
        chat_id = target["chat_id"]
        title   = target["title"]
        target_id = target["id"]

        if not await is_connected():
            failed += 1
            db.update_broadcast_target(broadcast_id, target_id, "failed", "Tidak terkoneksi")
            continue

        try:
            await send_message_to(chat_id, message)
            success += 1
            db.update_broadcast_target(broadcast_id, target_id, "success")
            logger.info(f"[USER {user_id}] Broadcast ke {title}: berhasil")
        except Exception as e:
            failed += 1
            db.update_broadcast_target(broadcast_id, target_id, "failed", str(e))
            logger.error(f"[USER {user_id}] Broadcast ke {title}: {e}")

        import time
        now = time.time()
        if (now - last_edit[0]) >= 3 or i == total - 1:
            try:
                await status_msg.edit_text(
                    f"📢 *Broadcast Progress*\n\n"
                    f"📨 Terkirim : {i+1}/{total}\n"
                    f"✅ Berhasil : {success}\n"
                    f"❌ Gagal    : {failed}",
                    parse_mode="Markdown",
                )
                last_edit[0] = now
            except Exception:
                pass

        await rate.wait()

    db.finish_broadcast(broadcast_id, "completed")

    try:
        await status_msg.edit_text(
            f"🎉 *Broadcast Selesai!*\n\n"
            f"📨 Total    : {total}\n"
            f"✅ Berhasil : {success}\n"
            f"❌ Gagal    : {failed}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
            ]),
        )
    except Exception:
        pass


async def cancel_user_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Broadcast dibatalkan.", reply_markup=_BACK_BTN)
    return ConversationHandler.END


def build_user_broadcast_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(user_broadcast_start, pattern="^cb_user_broadcast$"),
        ],
        states={
            WAIT_USER_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_user_message)
            ],
            CONFIRM_USER_BROADCAST: [
                CallbackQueryHandler(confirm_user_broadcast, pattern="^ub_confirm$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^cb_dashboard$"),
            MessageHandler(filters.COMMAND, cancel_user_broadcast),
        ],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
