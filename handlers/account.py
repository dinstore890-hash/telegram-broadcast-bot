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

WAIT_PHONE, WAIT_OTP, WAIT_2FA, WAIT_STRING_SESSION = range(4)

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_account")]
])
_BACK_DASHBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


# ── Tampilan utama akun ───────────────────────────────────────────────────────

async def account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await _show_accounts(query)


async def _show_accounts(query_or_msg, edit: bool = True) -> None:
    accounts = db.get_all_accounts()
    all_me = await telegram_client.get_all_me()
    me_by_phone = {m["phone"]: m for m in all_me}

    if accounts:
        lines = ["╭─ 👥 DAFTAR AKUN TELEGRAM\n│"]
        for i, acc in enumerate(accounts, 1):
            phone = acc["phone"]
            info = me_by_phone.get(phone)
            if info and info.get("connected"):
                status = "🟢"
                name = info.get("name") or acc["name"] or "-"
                uname = f"@{info['username']}" if info.get("username") else "-"
            else:
                status = "🔴"
                name = acc["name"] or "-"
                uname = f"@{acc['username']}" if acc["username"] else "-"
            lines.append(f"│  {i}. {status} {name} ({uname})")
            lines.append(f"│      📱 {phone}")
        lines.append("╰─")
        text = "\n".join(lines)
    else:
        text = (
            "╭─ 👥 DAFTAR AKUN TELEGRAM\n"
            "│\n"
            "│  Belum ada akun terdaftar.\n"
            "╰─"
        )

    # Tombol hapus per akun
    keyboard = []
    for acc in accounts:
        phone = acc["phone"]
        name = acc["name"] or phone
        keyboard.append([InlineKeyboardButton(f"🗑 Hapus {name}", callback_data=f"cb_delacc_{phone}")])

    keyboard.append([InlineKeyboardButton("🔄 Sync Grup ke Semua Akun", callback_data="cb_syncgroups")])
    keyboard.append([InlineKeyboardButton("➕ Tambah Akun", callback_data="cb_addacc_start")])
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")])

    markup = InlineKeyboardMarkup(keyboard)

    if edit:
        await query_or_msg.edit_message_text(text, reply_markup=markup)
    else:
        await query_or_msg.reply_text(text, reply_markup=markup)


# ── Hapus akun ────────────────────────────────────────────────────────────────

async def delacc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    phone = query.data.replace("cb_delacc_", "")
    await telegram_client.remove_client(phone)
    db.delete_account(phone)

    # Hapus file session
    import os
    from config import SESSION_DIR
    session_file = os.path.join(SESSION_DIR, f"{phone.replace('+', '')}.session")
    if os.path.exists(session_file):
        os.remove(session_file)

    db.add_log("INFO", f"Akun {phone} dihapus")
    await query.answer(f"Akun {phone} dihapus.", show_alert=True)
    await _show_accounts(query)


# ── Tambah akun: mulai ────────────────────────────────────────────────────────

async def addacc_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ ➕ TAMBAH AKUN BARU\n"
        "│\n"
        "│ Pilih metode login:\n"
        "╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 OTP", callback_data="cb_addacc_otp")],
            [InlineKeyboardButton("📋 String Session", callback_data="cb_addacc_string")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_account")],
        ])
    )
    return ConversationHandler.END


async def addacc_otp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ 🔑 LOGIN VIA OTP\n"
        "│\n"
        "│ Kirim nomor HP format internasional.\n"
        "│ Contoh: +628123456789\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return WAIT_PHONE


async def addacc_string_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ 📋 LOGIN VIA STRING SESSION\n"
        "│\n"
        "│ Paste string session kamu di sini.\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return WAIT_STRING_SESSION


async def wait_string_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    string_session = update.message.text.strip()

    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await update.effective_chat.send_message("╭─ ⏳ Mencoba connect...\n╰─")

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from config import API_ID, API_HASH
        from services.telegram_client import _clients

        client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            await msg.edit_text(
                "╭─ ❌ STRING SESSION TIDAK VALID\n"
                "│\n"
                "│ Session sudah expired atau salah.\n"
                "╰─",
                reply_markup=_BACK_BTN,
            )
            await client.disconnect()
            return ConversationHandler.END

        me = await client.get_me()
        phone = f"+{me.phone}"
        name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        username = me.username or ""
        session_name = phone.replace("+", "")

        _clients[phone] = client

        db.add_account(phone, session_name, name, username, string_session)
        db.add_log("INFO", f"Akun ditambahkan via String Session: {phone} (@{username})")

        await msg.edit_text(
            f"╭─ ✅ AKUN BERHASIL DITAMBAHKAN\n"
            f"│\n"
            f"│  Nama     : {name}\n"
            f"│  Username : @{username}\n"
            f"│  Phone    : {phone}\n"
            f"╰─",
            reply_markup=_BACK_BTN,
        )

    except Exception as e:
        logger.error(f"String session error: {e}")
        await msg.edit_text(
            f"╭─ ❌ GAGAL\n"
            f"│\n"
            f"│ {e}\n"
            f"╰─",
            reply_markup=_BACK_BTN,
        )

    return ConversationHandler.END


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

    context.user_data["acc_phone"] = phone
    context.user_data["acc_phone_code_hash"] = phone_code_hash

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
    phone = context.user_data.get("acc_phone", "")
    phone_code_hash = context.user_data.get("acc_phone_code_hash", "")

    if not phone or not phone_code_hash:
        await update.message.reply_text(
            "╭─ ❌ SESI TIDAK DITEMUKAN\n"
            "│\n"
            "│ Mulai ulang dengan menekan tombol Tambah Akun.\n"
            "╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    logger.info(f"OTP attempt — phone: {phone}, code: {code}, hash: {phone_code_hash[:6]}...")
    success, needs_2fa, error_msg = await telegram_client.sign_in(phone, code, phone_code_hash)
    logger.info(f"sign_in result — success: {success}, needs_2fa: {needs_2fa}, error: {error_msg}")

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
        await _save_new_account(phone, update)
        return ConversationHandler.END

    # Hanya kirim ulang OTP kalau memang expired, bukan salah kode
    is_expired = "PhoneCodeExpired" in error_msg or "Expired" in error_msg
    is_invalid = "PhoneCodeInvalid" in error_msg or "Invalid" in error_msg

    if is_expired:
        msg = await update.message.reply_text("╭─ ⏳ Kode expired. Mengirim ulang OTP...\n╰─")
        new_hash = await telegram_client.send_code(phone)
        if new_hash:
            context.user_data["acc_phone_code_hash"] = new_hash
            await msg.edit_text(
                "╭─ ✅ OTP BARU TERKIRIM\n"
                "│\n"
                "│ Segera kirim kode yang baru.\n"
                "╰─"
            )
        else:
            await msg.edit_text("╭─ ❌ Gagal kirim ulang OTP.\n╰─", reply_markup=_BACK_BTN)
            return ConversationHandler.END
        return WAIT_OTP

    if is_invalid:
        await update.message.reply_text(
            "╭─ ❌ KODE OTP SALAH\n"
            "│\n"
            "│ Kode yang kamu masukkan salah.\n"
            "│ Coba kirim ulang kode OTP yang benar.\n"
            "╰─"
        )
        return WAIT_OTP

    await update.message.reply_text(
        f"╭─ ❌ LOGIN GAGAL\n"
        f"│\n"
        f"│ {error_msg}\n"
        f"╰─",
        reply_markup=_BACK_BTN,
    )
    return ConversationHandler.END


async def wait_2fa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    password = update.message.text.strip()
    phone = context.user_data.get("acc_phone", "")

    try:
        await update.message.delete()
    except Exception:
        pass

    success = await telegram_client.sign_in_2fa(phone, password)
    if success:
        await _save_new_account(phone, update)
    else:
        await update.effective_chat.send_message(
            "╭─ ❌ PASSWORD 2FA SALAH\n"
            "│\n"
            "╰─ Coba lagi."
        )
        return WAIT_2FA

    return ConversationHandler.END


async def _save_new_account(phone: str, update) -> None:
    """Simpan akun baru ke DB setelah login berhasil."""
    me = await telegram_client.get_me(phone)
    name = me["name"] if me else ""
    username = me["username"] if me else ""
    session_name = phone.replace("+", "")

    db.add_account(phone, session_name, name, username)
    db.add_log("INFO", f"Akun baru ditambahkan: {phone} (@{username})")

    await update.effective_chat.send_message(
        f"╭─ ✅ AKUN BERHASIL DITAMBAHKAN\n"
        f"│\n"
        f"│  Nama     : {name}\n"
        f"│  Username : @{username}\n"
        f"│  Phone    : {phone}\n"
        f"╰─",
        reply_markup=_BACK_BTN,
    )


async def cancel_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = context.user_data.pop("acc_phone", None)
    if phone:
        await telegram_client.remove_client(phone)
    context.user_data.clear()
    await update.message.reply_text("╭─ ❌ Dibatalkan.\n╰─", reply_markup=_BACK_BTN)
    return ConversationHandler.END


# ── Sync Grup ────────────────────────────────────────────────────────────────

async def syncgroups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    targets = db.get_active_targets()
    if not targets:
        await query.edit_message_text("╭─ ❌ Belum ada target grup.\n╰─", reply_markup=_BACK_BTN)
        return

    accounts = db.get_active_accounts()
    if len(accounts) < 2:
        await query.edit_message_text("╭─ ❌ Hanya ada 1 akun, tidak perlu sync.\n╰─", reply_markup=_BACK_BTN)
        return

    await query.edit_message_text(
        f"╭─ 🔄 SYNC GRUP\n"
        f"│\n"
        f"│ Memulai join {len(targets)} grup ke semua akun...\n"
        f"│ Ini mungkin butuh beberapa menit.\n"
        f"╰─"
    )

    from services.telegram_client import get_client, is_connected
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.errors import UserAlreadyParticipantError, FloodWaitError
    import asyncio

    total_joined = 0
    total_failed = 0

    for acc in accounts:
        phone = acc["phone"]
        if not await is_connected(phone):
            continue
        client = get_client(phone)
        joined = 0
        failed = 0
        for target in targets:
            username = target["username"]
            if not username:
                continue
            try:
                entity = await client.get_entity(username)
                await client(JoinChannelRequest(entity))
                joined += 1
                await asyncio.sleep(4)
            except UserAlreadyParticipantError:
                joined += 1
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
            except Exception:
                failed += 1
        total_joined += joined
        total_failed += failed
        db.add_log("INFO", f"Sync grup akun {phone}: {joined} joined, {failed} gagal")

    await query.edit_message_text(
        f"╭─ ✅ SYNC SELESAI\n"
        f"│\n"
        f"│  Berhasil join : {total_joined}\n"
        f"│  Gagal         : {total_failed}\n"
        f"╰─",
        reply_markup=_BACK_BTN,
    )


# ── Reconnect & Logout ────────────────────────────────────────────────────────

async def reconnect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text("╭─ ⏳ Mencoba reconnect semua akun...\n╰─")
    connected = await telegram_client.connect_all()
    await query.edit_message_text(
        f"╭─ 🔄 RECONNECT\n"
        f"│\n"
        f"│  Berhasil: {len(connected)} akun\n"
        f"╰─",
        reply_markup=_BACK_BTN,
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
        "╰─ Berhasil logout.",
        reply_markup=_BACK_BTN,
    )


def build_login_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(addacc_start_callback,  pattern="^cb_addacc_start$"),
            CallbackQueryHandler(addacc_otp_callback,    pattern="^cb_addacc_otp$"),
            CallbackQueryHandler(addacc_string_callback, pattern="^cb_addacc_string$"),
        ],
        states={
            WAIT_PHONE:          [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_phone_handler)],
            WAIT_OTP:            [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_otp_handler)],
            WAIT_2FA:            [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_2fa_handler)],
            WAIT_STRING_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_string_session_handler)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_login)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
