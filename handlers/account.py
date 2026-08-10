import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import is_admin
from services import telegram_client
import database as db

logger = logging.getLogger(__name__)

# ConversationHandler states
WAIT_PHONE, WAIT_OTP, WAIT_2FA = range(3)

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


async def account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await _show_account(query)


async def _show_account(query_or_msg, edit: bool = True) -> None:
    me = await telegram_client.get_me()
    if me:
        text = (
            "👤 *TELEGRAM ACCOUNT*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Status   : 🟢 Connected\n"
            f"Nama     : {me['name']}\n"
            f"Username : @{me['username']}\n"
            f"Phone    : +{me['phone']}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Reconnect", callback_data="cb_reconnect")],
            [InlineKeyboardButton("🔐 Logout",    callback_data="cb_logout")],
            [InlineKeyboardButton("⬅️ Kembali",   callback_data="cb_dashboard")],
        ])
    else:
        text = (
            "👤 *TELEGRAM ACCOUNT*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Status : 🔴 Disconnected\n\n"
            "Tekan tombol di bawah untuk login."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Login Sekarang", callback_data="cb_login_start")],
            [InlineKeyboardButton("⬅️ Kembali",        callback_data="cb_dashboard")],
        ])

    if edit:
        await query_or_msg.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await query_or_msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ── Login Flow ────────────────────────────────────────────────────────────────

async def login_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    from config import API_ID, API_HASH
    if not API_ID or not API_HASH:
        await query.edit_message_text(
            "❌ API_ID dan API_HASH belum diisi di file `.env`.\n\n"
            "Dapatkan di: https://my.telegram.org/apps",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📱 *LOGIN TELEGRAM*\n\n"
        "Kirim nomor HP kamu dengan format internasional.\n\n"
        "Contoh: `+628123456789`\n\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return WAIT_PHONE


async def wait_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    phone = update.message.text.strip()
    if not phone.startswith("+"):
        await update.message.reply_text("❌ Format salah. Gunakan format: `+628123456789`", parse_mode="Markdown")
        return WAIT_PHONE

    msg = await update.message.reply_text("⏳ Mengirim kode OTP...")
    phone_code_hash = await telegram_client.send_code(phone)

    if not phone_code_hash:
        await msg.edit_text("❌ Gagal mengirim OTP. Periksa nomor HP dan API credentials.")
        return ConversationHandler.END

    context.user_data["phone"] = phone
    context.user_data["phone_code_hash"] = phone_code_hash

    await msg.edit_text(
        "✅ Kode OTP telah dikirim ke Telegram kamu.\n\n"
        "Kirim kode OTP yang kamu terima.\n\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return WAIT_OTP


async def wait_otp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    code = update.message.text.strip().replace(" ", "")
    phone = context.user_data.get("phone", "")
    phone_code_hash = context.user_data.get("phone_code_hash", "")

    logger.info(f"OTP attempt — phone: {phone}, hash: {phone_code_hash[:6]}..., code_len: {len(code)}")

    if not phone or not phone_code_hash:
        await update.message.reply_text(
            "❌ Sesi login tidak ditemukan. Mulai ulang dengan menekan tombol Login.",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    success, needs_2fa, error_msg = await telegram_client.sign_in(phone, code, phone_code_hash)

    if needs_2fa:
        await update.message.reply_text(
            "🔐 Akun kamu menggunakan *2FA*.\n\n"
            "Kirim password 2FA kamu.\n\n"
            "_Ketik /cancel untuk membatalkan._",
            parse_mode="Markdown",
        )
        return WAIT_2FA

    if success:
        me = await telegram_client.get_me()
        db.add_log("INFO", f"Login berhasil: @{me['username'] if me else 'unknown'}")
        await update.message.reply_text(
            f"✅ Login berhasil!\n\nSelamat datang, *{me['name'] if me else 'User'}*.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    # Kode expired — kirim ulang otomatis
    if "Expired" in error_msg or "expired" in error_msg:
        msg = await update.message.reply_text("⏳ Kode expired. Mengirim ulang OTP...")
        new_hash = await telegram_client.send_code(phone)
        if new_hash:
            context.user_data["phone_code_hash"] = new_hash
            await msg.edit_text(
                "✅ Kode OTP baru telah dikirim ke Telegram kamu.\n\n"
                "Segera kirim kode yang baru (berlaku ~2 menit)."
            )
        else:
            await msg.edit_text("❌ Gagal mengirim ulang OTP. Coba tekan Login lagi.", reply_markup=_BACK_BTN)
            return ConversationHandler.END
        return WAIT_OTP

    await update.message.reply_text(
        f"❌ Login gagal: `{error_msg}`\n\nCoba kirim ulang kode OTP.",
        parse_mode="Markdown",
    )
    return WAIT_OTP


async def wait_2fa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    password = update.message.text.strip()
    # Hapus pesan password agar tidak tersimpan di chat
    try:
        await update.message.delete()
    except Exception:
        pass

    success = await telegram_client.sign_in_2fa(password)
    if success:
        me = await telegram_client.get_me()
        db.add_log("INFO", f"Login 2FA berhasil: @{me['username'] if me else 'unknown'}")
        await update.effective_chat.send_message(
            f"✅ Login berhasil!\n\nSelamat datang, *{me['name'] if me else 'User'}*.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
    else:
        await update.effective_chat.send_message("❌ Password 2FA salah. Coba lagi.")
        return WAIT_2FA

    return ConversationHandler.END


async def cancel_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Login dibatalkan.", reply_markup=_BACK_BTN)
    return ConversationHandler.END


# ── Reconnect / Logout ────────────────────────────────────────────────────────

async def reconnect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text("⏳ Mencoba reconnect...")
    ok = await telegram_client.connect()
    if ok:
        await _show_account(query)
    else:
        await query.edit_message_text(
            "❌ Reconnect gagal. Session mungkin sudah tidak valid.\nSilakan login ulang.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Login Ulang", callback_data="cb_login_start")],
                [InlineKeyboardButton("⬅️ Kembali",    callback_data="cb_dashboard")],
            ]),
        )


async def logout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await telegram_client.logout()
    db.add_log("INFO", "Logout dari akun Telegram")
    await query.edit_message_text(
        "🔐 Berhasil logout dari akun Telegram.",
        reply_markup=_BACK_BTN,
    )


def build_login_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(login_start_callback, pattern="^cb_login_start$")],
        states={
            WAIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_phone_handler)],
            WAIT_OTP:   [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_otp_handler)],
            WAIT_2FA:   [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_2fa_handler)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_login)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
