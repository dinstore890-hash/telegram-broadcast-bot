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
            f"╭─ 👤 TELEGRAM ACCOUNT\n"
            f"│\n"
            f"│  ⤷  Status   : 🟢 Connected\n"
            f"│  ⤷  Nama     : {me['name']}\n"
            f"│  ⤷  Username : @{me['username']}\n"
            f"│  ⤷  Phone    : +{me['phone']}\n"
            f"╰─"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Reconnect", callback_data="cb_reconnect")],
            [InlineKeyboardButton("🔐 Logout",    callback_data="cb_logout")],
            [InlineKeyboardButton("⬅️ Kembali",   callback_data="cb_dashboard")],
        ])
    else:
        text = (
            "╭─ 👤 TELEGRAM ACCOUNT\n"
            "│\n"
            "│  ⤷  Status : 🔴 Disconnected\n"
            "│\n"
            "╰─ Tekan tombol di bawah untuk login."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Login Sekarang", callback_data="cb_login_start")],
            [InlineKeyboardButton("⬅️ Kembali",        callback_data="cb_dashboard")],
        ])

    if edit:
        await query_or_msg.edit_message_text(text, reply_markup=keyboard)
    else:
        await query_or_msg.reply_text(text, reply_markup=keyboard)


async def login_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    from config import API_ID, API_HASH
    if not API_ID or not API_HASH:
        await query.edit_message_text(
            "╭─ ❌ API BELUM DIISI\n"
            "│\n"
            "│ API_ID dan API_HASH belum diisi.\n"
            "│ Dapatkan di: https://my.telegram.org/apps\n"
            "╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ 📱 LOGIN TELEGRAM\n"
        "│\n"
        "│ Kirim nomor HP format internasional.\n"
        "│ Contoh: +628123456789\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return WAIT_PHONE


async def wait_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    phone = update.message.text.strip()
    if not phone.startswith("+"):
        await update.message.reply_text(
            "╭─ ❌ FORMAT SALAH\n"
            "│\n"
            "│ Gunakan format: +628123456789\n"
            "╰─"
        )
        return WAIT_PHONE

    msg = await update.message.reply_text("╭─ ⏳ Mengirim kode OTP...\n╰─")
    phone_code_hash = await telegram_client.send_code(phone)

    if not phone_code_hash:
        await msg.edit_text(
            "╭─ ❌ GAGAL KIRIM OTP\n"
            "│\n"
            "│ Periksa nomor HP dan API credentials.\n"
            "╰─"
        )
        return ConversationHandler.END

    context.user_data["phone"] = phone
    context.user_data["phone_code_hash"] = phone_code_hash

    await msg.edit_text(
        "╭─ ✅ KODE OTP TERKIRIM\n"
        "│\n"
        "│ Kirim kode OTP yang kamu terima.\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
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
            "╭─ ❌ SESI TIDAK DITEMUKAN\n"
            "│\n"
            "│ Mulai ulang dengan menekan tombol Login.\n"
            "╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    success, needs_2fa, error_msg = await telegram_client.sign_in(phone, code, phone_code_hash)

    if needs_2fa:
        await update.message.reply_text(
            "╭─ 🔐 2FA DIPERLUKAN\n"
            "│\n"
            "│ Kirim password 2FA kamu.\n"
            "│\n"
            "╰─ Ketik /cancel untuk batal."
        )
        return WAIT_2FA

    if success:
        me = await telegram_client.get_me()
        db.add_log("INFO", f"Login berhasil: @{me['username'] if me else 'unknown'}")
        await update.message.reply_text(
            f"╭─ ✅ LOGIN BERHASIL\n"
            f"│\n"
            f"│ Selamat datang, {me['name'] if me else 'User'}!\n"
            f"╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    if "Expired" in error_msg or "expired" in error_msg:
        msg = await update.message.reply_text("╭─ ⏳ Kode expired. Mengirim ulang OTP...\n╰─")
        new_hash = await telegram_client.send_code(phone)
        if new_hash:
            context.user_data["phone_code_hash"] = new_hash
            await msg.edit_text(
                "╭─ ✅ OTP BARU TERKIRIM\n"
                "│\n"
                "│ Segera kirim kode yang baru.\n"
                "╰─"
            )
        else:
            await msg.edit_text("╭─ ❌ Gagal kirim ulang OTP.\n╰─ Coba tekan Login lagi.", reply_markup=_BACK_BTN)
            return ConversationHandler.END
        return WAIT_OTP

    await update.message.reply_text(
        f"╭─ ❌ LOGIN GAGAL\n"
        f"│\n"
        f"│ {error_msg}\n"
        f"╰─ Coba kirim ulang kode OTP."
    )
    return WAIT_OTP


async def wait_2fa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    password = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    success = await telegram_client.sign_in_2fa(password)
    if success:
        me = await telegram_client.get_me()
        db.add_log("INFO", f"Login 2FA berhasil: @{me['username'] if me else 'unknown'}")
        await update.effective_chat.send_message(
            f"╭─ ✅ LOGIN BERHASIL\n"
            f"│\n"
            f"│ Selamat datang, {me['name'] if me else 'User'}!\n"
            f"╰─",
            reply_markup=_BACK_BTN,
        )
    else:
        await update.effective_chat.send_message(
            "╭─ ❌ PASSWORD 2FA SALAH\n"
            "│\n"
            "╰─ Coba lagi."
        )
        return WAIT_2FA

    return ConversationHandler.END


async def cancel_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("╭─ ❌ Login dibatalkan.\n╰─", reply_markup=_BACK_BTN)
    return ConversationHandler.END


async def reconnect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text("╭─ ⏳ Mencoba reconnect...\n╰─")
    ok = await telegram_client.connect()
    if ok:
        await _show_account(query)
    else:
        await query.edit_message_text(
            "╭─ ❌ RECONNECT GAGAL\n"
            "│\n"
            "│ Session mungkin sudah tidak valid.\n"
            "╰─ Silakan login ulang.",
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
        "╭─ 🔐 LOGOUT BERHASIL\n"
        "│\n"
        "╰─ Berhasil logout dari akun Telegram.",
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
