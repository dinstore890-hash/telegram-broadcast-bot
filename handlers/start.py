from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from config import is_admin, TEST_MODE
from services import telegram_client


def _main_keyboard(is_broadcasting: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Daftar Grup",    callback_data="cb_groups"),
            InlineKeyboardButton("➕ Tambah Target", callback_data="cb_addtarget"),
        ],
        [
            InlineKeyboardButton("⏸️ Pause Broadcast", callback_data="cb_pause")
            if is_broadcasting else
            InlineKeyboardButton("📢 Broadcast", callback_data="cb_broadcast"),
        ],
        [
            InlineKeyboardButton("📊 Statistik", callback_data="cb_stats"),
            InlineKeyboardButton("📜 Logs",      callback_data="cb_logs"),
        ],
        [
            InlineKeyboardButton("👤 Account",    callback_data="cb_account"),
            InlineKeyboardButton("⚙️ Pengaturan", callback_data="cb_settings"),
        ],
        [InlineKeyboardButton("👑 Kelola Lisensi", callback_data="cb_manage_licenses")],
        [InlineKeyboardButton("🔄 Refresh",        callback_data="cb_dashboard")],
    ])


def _user_keyboard(has_license: bool = False) -> InlineKeyboardMarkup:
    if has_license:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Mulai Broadcast", callback_data="cb_user_broadcast")],
            [InlineKeyboardButton("🎫 Cek Lisensi",     callback_data="cb_lisensi")],
            [InlineKeyboardButton("🛒 Perpanjang",      callback_data="cb_order")],
            [InlineKeyboardButton("⚠️ Bantuan",         callback_data="ub_bantuan")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
        [InlineKeyboardButton("📋 Cek Lisensi",   callback_data="cb_lisensi")],
        [InlineKeyboardButton("⚠️ Bantuan",        callback_data="ub_bantuan")],
    ])


async def _build_user_dashboard(user_id: int, first_name: str = "") -> str:
    from datetime import datetime
    hour = datetime.now().hour
    if hour < 11:
        greeting = "Selamat Pagi"
    elif hour < 15:
        greeting = "Selamat Siang"
    elif hour < 18:
        greeting = "Selamat Sore"
    else:
        greeting = "Selamat Malam"

    # Ambil info bot dari DB settings (bisa diubah admin)
    bot_title   = db.get_setting("bot_title",   "💎 Gmail Market JASNEB 💎")
    bot_owner   = db.get_setting("bot_owner",   "@GmailMarket67")
    bot_grup    = db.get_setting("bot_grup",    "https://t.me/+sVVIxK_QnhthM2E1")
    bot_channel = db.get_setting("bot_channel", "https://t.me/GmailxMarket")
    bot_tagline = db.get_setting("bot_tagline", "Gunakan menu untuk mulai promosi instant 🤖")

    lic = db.get_license(user_id)
    active = lic and db.is_license_active(user_id)
    if active:
        expired = lic["expired_at"][:10]
        lisensi_info = (
            f"│\n"
            f"│ 🎫 LISENSI AKTIF\n"
            f"│  ⤷  Paket   : {lic['paket']}\n"
            f"│  ⤷  Max Grup: {lic['max_grup']}\n"
            f"│  ⤷  Expired : {expired}\n"
        )
    else:
        active = False
        lisensi_info = (
            f"│\n"
            f"│ 🔒 Belum punya lisensi\n"
            f"│  ⤷  Order sekarang untuk mulai!\n"
        )

    return (
        f"╭─ {bot_title}\n"
        f"│\n"
        f"│ Halo, {first_name + '! ' if first_name else ''}{greeting} 👋\n"
        f"{lisensi_info}"
        f"│ ∘₊✧──────✧₊∘∘₊✧──────✧₊∘\n"
        f"│  𝐎𝐰𝐧𝐞𝐫 {bot_owner}\n"
        f"│  👥 Grup    : {bot_grup}\n"
        f"│  📢 Channel : {bot_channel}\n"
        f"╰─ {bot_tagline}"
    ), active


async def _build_dashboard(connected: bool) -> str:
    stats = db.get_stats()
    user_stats = db.get_user_stats()
    from services.broadcast_service import get_state
    state = get_state()

    from datetime import datetime
    hour = datetime.now().hour
    if hour < 11:
        greeting = "Selamat Pagi"
    elif hour < 15:
        greeting = "Selamat Siang"
    elif hour < 18:
        greeting = "Selamat Sore"
    else:
        greeting = "Selamat Malam"

    bot_title   = db.get_setting("bot_title",   "💎 Gmail Market JASNEB 💎")
    bot_owner   = db.get_setting("bot_owner",   "@GmailMarket67")
    bot_tagline = db.get_setting("bot_tagline", "Gunakan menu untuk mulai promosi instant 🤖")

    account_status = "🟢 Connected" if connected else "🔴 Disconnected"
    test_badge = "  🧪 TEST MODE AKTIF" if TEST_MODE else ""

    broadcast_info = ""
    if state["running"]:
        status_bc = "⏸️ Dijeda" if state["paused"] else "⚡ Berjalan"
        broadcast_info = (
            f"│\n"
            f"│ ⚡ 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓 𝐀𝐊𝐓𝐈𝐅\n"
            f"│  ⤷  Status   : {status_bc}\n"
            f"│  ⤷  Progress : {state['current']}/{state['total']}\n"
            f"│  ⤷  Berhasil : {state['success']}\n"
            f"│  ⤷  Gagal    : {state['failed']}\n"
        )

    return (
        f"╭─ {bot_title}{test_badge}\n"
        f"│\n"
        f"│ Halo, {greeting} 👋\n"
        f"│\n"
        f"│ ⭐ 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐊 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓\n"
        f"│  ⤷  Total Target   : {stats['total_targets']}\n"
        f"│  ⤷  Target Aktif   : {stats['active_targets']}\n"
        f"│  ⤷  Total Terkirim : {stats['total_success']}\n"
        f"│  ⤷  Total Gagal    : {stats['total_failed']}\n"
        f"{broadcast_info}"
        f"│ ∘₊✧──────✧₊∘∘₊✧──────✧₊∘\n"
        f"│  📡 Akun : {account_status}\n"
        f"│       𝐎𝐰𝐧𝐞𝐫 {bot_owner}\n"
        f"╰─ {bot_tagline}"
    )


async def _build_admin_dashboard(connected: bool) -> str:
    stats = db.get_stats()
    user_stats = db.get_user_stats()
    from services.broadcast_service import get_state
    state = get_state()

    bot_title   = db.get_setting("bot_title",   "💎 Gmail Market JASNEB 💎")
    bot_owner   = db.get_setting("bot_owner",   "@GmailMarket67")
    bot_tagline = db.get_setting("bot_tagline", "Gunakan menu untuk mulai promosi instant 🤖")

    account_status = "🟢 Connected" if connected else "🔴 Disconnected"
    test_badge = "  🧪 TEST MODE AKTIF" if TEST_MODE else ""

    broadcast_info = ""
    if state["running"]:
        status_bc = "⏸️ Dijeda" if state["paused"] else "⚡ Berjalan"
        broadcast_info = (
            f"│\n"
            f"│ ⚡ 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓 𝐀𝐊𝐓𝐈𝐅\n"
            f"│  ⤷  Status   : {status_bc}\n"
            f"│  ⤷  Progress : {state['current']}/{state['total']}\n"
            f"│  ⤷  Berhasil : {state['success']}\n"
            f"│  ⤷  Gagal    : {state['failed']}\n"
        )

    return (
        f"╭─ {bot_title}{test_badge}\n"
        f"│\n"
        f"│ 👑 ADMIN DASHBOARD\n"
        f"│\n"
        f"│ ⭐ 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐊 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓\n"
        f"│  ⤷  Total Target   : {stats['total_targets']}\n"
        f"│  ⤷  Target Aktif   : {stats['active_targets']}\n"
        f"│  ⤷  Total Terkirim : {stats['total_success']}\n"
        f"│  ⤷  Total Gagal    : {stats['total_failed']}\n"
        f"{broadcast_info}"
        f"│ ⭐ 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐊 𝐔𝐒𝐄𝐑\n"
        f"│  ⤷  Pengguna Baru   : {user_stats['new_users']}\n"
        f"│  ⤷  Total Pengguna  : {user_stats['total_users']}\n"
        f"│  ⤷  Kunjungan Baru  : {user_stats['new_visits']}\n"
        f"│  ⤷  Total Kunjungan : {user_stats['total_visits']}\n"
        f"│ ∘₊✧──────✧₊∘∘₊✧──────✧₊∘\n"
        f"│  📡 Akun : {account_status}\n"
        f"│       𝐎𝐰𝐧𝐞𝐫 {bot_owner}\n"
        f"╰─ {bot_tagline}"
    )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db.track_user(user.id, user.username, user.first_name)

    connected = await telegram_client.is_connected()
    from services.broadcast_service import is_running

    if is_admin(user.id):
        text = await _build_admin_dashboard(connected)
        await update.message.reply_text(text, reply_markup=_main_keyboard(is_running()))
    else:
        text, active = await _build_user_dashboard(user.id, user.first_name or "")
        await update.message.reply_text(text, reply_markup=_user_keyboard(active))


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if is_admin(query.from_user.id):
        from services.broadcast_service import is_running
        connected = await telegram_client.is_connected()
        text = await _build_admin_dashboard(connected)
        try:
            await query.edit_message_text(text, reply_markup=_main_keyboard(is_running()))
        except Exception:
            pass
    else:
        text, active = await _build_user_dashboard(query.from_user.id, query.from_user.first_name or "")
        try:
            await query.edit_message_text(text, reply_markup=_user_keyboard(active))
        except Exception:
            pass


async def lisensi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lic = db.get_license(user_id)

    if lic and db.is_license_active(user_id):
        from datetime import datetime
        expired = lic["expired_at"][:16].replace("T", " ")
        activated = lic["activated_at"][:10]
        text = (
            f"╭─ 🎫 LISENSI KAMU\n"
            f"│\n"
            f"│  ⤷  Paket    : {lic['paket']}\n"
            f"│  ⤷  Max Grup : {lic['max_grup']}\n"
            f"│  ⤷  Durasi   : {lic['durasi_hari']} Hari\n"
            f"│  ⤷  Aktif    : {activated}\n"
            f"│  ⤷  Expired  : {expired}\n"
            f"│\n"
            f"╰─ Lisensi kamu masih aktif ✅"
        )
    else:
        text = (
            "╭─ 🔒 LISENSI TIDAK AKTIF\n"
            "│\n"
            "│ Kamu belum punya lisensi aktif.\n"
            "│ Order sekarang untuk mulai!\n"
            "╰─"
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
            [InlineKeyboardButton("⬅️ Kembali",        callback_data="cb_dashboard")],
        ]),
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    test_status = "🟢 AKTIF" if TEST_MODE else "🔴 NONAKTIF"
    from config import BROADCAST_DELAY
    broadcast_delay = db.get_setting("broadcast_delay", str(BROADCAST_DELAY))
    leave_delay     = db.get_setting("leave_delay", "5")
    bot_title       = db.get_setting("bot_title",   "💎 Gmail Market JASNEB 💎")
    bot_owner       = db.get_setting("bot_owner",   "@GmailMarket67")
    bot_grup        = db.get_setting("bot_grup",    "https://t.me/+sVVIxK_QnhthM2E1")
    bot_channel     = db.get_setting("bot_channel", "https://t.me/GmailxMarket")

    text = (
        f"╭─ ⚙️ PENGATURAN\n"
        f"│\n"
        f"│  ⤷  Test Mode        : {test_status}\n"
        f"│  ⤷  Broadcast Delay  : {broadcast_delay}s\n"
        f"│  ⤷  Leave Delay      : {leave_delay}s\n"
        f"│\n"
        f"│ 📝 INFO BOT (tampil ke user):\n"
        f"│  ⤷  Judul    : {bot_title}\n"
        f"│  ⤷  Owner    : {bot_owner}\n"
        f"│  ⤷  Link Grup: {bot_grup[:30]}...\n"
        f"│  ⤷  Channel  : {bot_channel[:30]}...\n"
        f"│\n"
        f"╰─ Pilih yang ingin diubah:"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⏱️ Broadcast Delay", callback_data="cb_set_broadcast_delay"),
                InlineKeyboardButton("⏱️ Leave Delay",     callback_data="cb_leavedelay"),
            ],
            [InlineKeyboardButton("📝 Ubah Info Bot", callback_data="cb_set_botinfo")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
        ]),
    )


# ── Ubah Broadcast Delay ──────────────────────────────────────────────────────

WAIT_BROADCAST_DELAY = 50

_SETTINGS_BACK = InlineKeyboardMarkup([
    [InlineKeyboardButton("⚙️ Pengaturan", callback_data="cb_settings")]
])


async def set_broadcast_delay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram.ext import ConversationHandler
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    from config import BROADCAST_DELAY
    current = db.get_setting("broadcast_delay", str(BROADCAST_DELAY))
    await query.edit_message_text(
        f"╭─ ⏱️ ATUR BROADCAST DELAY\n"
        f"│\n"
        f"│  ⤷  Delay saat ini: {current} detik\n"
        f"│\n"
        f"│ Kirim angka delay baru (detik).\n"
        f"│ Contoh: 3 atau 5\n"
        f"│ (Disarankan 3-10 detik)\n"
        f"╰─ Ketik /cancel untuk batal."
    )
    return WAIT_BROADCAST_DELAY


async def wait_broadcast_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram.ext import ConversationHandler
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    try:
        delay = float(text)
        if delay < 0.5 or delay > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "╭─ ⚠️ Input tidak valid.\n│ Masukkan angka 0.5-300.\n╰─",
            reply_markup=_SETTINGS_BACK,
        )
        return ConversationHandler.END

    db.set_setting("broadcast_delay", str(delay))
    db.add_log("INFO", f"Broadcast delay diubah: {delay} detik")

    await update.message.reply_text(
        f"╭─ ✅ DELAY DIPERBARUI\n"
        f"│\n"
        f"│  ⤷  Broadcast delay: {delay} detik\n"
        f"╰─",
        reply_markup=_SETTINGS_BACK,
    )
    return ConversationHandler.END


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram.ext import ConversationHandler
    await update.message.reply_text("╭─ ❌ Dibatalkan.\n╰─", reply_markup=_SETTINGS_BACK)
    return ConversationHandler.END



# ── Ubah Info Bot (Admin) ─────────────────────────────────────────────────────

WAIT_BOTINFO = 60  # conversation state

_BOTINFO_FIELDS = {
    "bot_title":   ("Judul Bot",   "💎 Gmail Market JASNEB 💎"),
    "bot_owner":   ("Owner",       "@GmailMarket67"),
    "bot_grup":    ("Link Grup",   "https://t.me/+sVVIxK_QnhthM2E1"),
    "bot_channel": ("Link Channel","https://t.me/GmailxMarket"),
    "bot_tagline": ("Tagline",     "Gunakan menu untuk mulai promosi instant 🤖"),
}

_BOTINFO_BACK = InlineKeyboardMarkup([
    [InlineKeyboardButton("📝 Info Bot", callback_data="cb_set_botinfo")],
    [InlineKeyboardButton("⚙️ Pengaturan", callback_data="cb_settings")],
])


async def set_botinfo_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan menu pilih field yang mau diubah."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    title   = db.get_setting("bot_title",   "💎 Gmail Market JASNEB 💎")
    owner   = db.get_setting("bot_owner",   "@GmailMarket67")
    grup    = db.get_setting("bot_grup",    "https://t.me/+sVVIxK_QnhthM2E1")
    channel = db.get_setting("bot_channel", "https://t.me/GmailxMarket")
    tagline = db.get_setting("bot_tagline", "Gunakan menu untuk mulai promosi instant 🤖")

    text = (
        f"╭─ 📝 UBAH INFO BOT\n"
        f"│\n"
        f"│  ⤷  Judul    : {title}\n"
        f"│  ⤷  Owner    : {owner}\n"
        f"│  ⤷  Link Grup: {grup}\n"
        f"│  ⤷  Channel  : {channel}\n"
        f"│  ⤷  Tagline  : {tagline[:40]}{'...' if len(tagline)>40 else ''}\n"
        f"│\n"
        f"╰─ Pilih field yang ingin diubah:"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Judul Bot",   callback_data="cb_editbotinfo_bot_title")],
            [InlineKeyboardButton("✏️ Owner",       callback_data="cb_editbotinfo_bot_owner")],
            [InlineKeyboardButton("✏️ Link Grup",   callback_data="cb_editbotinfo_bot_grup")],
            [InlineKeyboardButton("✏️ Link Channel",callback_data="cb_editbotinfo_bot_channel")],
            [InlineKeyboardButton("✏️ Tagline",     callback_data="cb_editbotinfo_bot_tagline")],
            [InlineKeyboardButton("🔄 Reset Default", callback_data="cb_resetbotinfo")],
            [InlineKeyboardButton("⬅️ Kembali",    callback_data="cb_settings")],
        ]),
    )


async def edit_botinfo_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mulai konversasi edit 1 field info bot."""
    from telegram.ext import ConversationHandler
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    field_key = query.data.replace("cb_editbotinfo_", "")
    if field_key not in _BOTINFO_FIELDS:
        return ConversationHandler.END

    label, default = _BOTINFO_FIELDS[field_key]
    current = db.get_setting(field_key, default)
    context.user_data["editing_botinfo_key"] = field_key

    await query.edit_message_text(
        f"╭─ ✏️ UBAH {label.upper()}\n"
        f"│\n"
        f"│  Nilai sekarang:\n"
        f"│  {current}\n"
        f"│\n"
        f"│ Kirim teks baru untuk {label}.\n"
        f"╰─ /cancel untuk batal."
    )
    return WAIT_BOTINFO


async def wait_botinfo_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Terima input teks baru dan simpan ke DB."""
    from telegram.ext import ConversationHandler
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    field_key = context.user_data.pop("editing_botinfo_key", None)
    if not field_key or field_key not in _BOTINFO_FIELDS:
        return ConversationHandler.END

    new_value = update.message.text.strip()
    if not new_value:
        await update.message.reply_text("╭─ ⚠️ Input kosong, tidak disimpan.\n╰─", reply_markup=_BOTINFO_BACK)
        return ConversationHandler.END

    label, _ = _BOTINFO_FIELDS[field_key]
    db.set_setting(field_key, new_value)
    db.add_log("INFO", f"Info bot '{field_key}' diubah: {new_value[:50]}")

    await update.message.reply_text(
        f"╭─ ✅ {label.upper()} DIPERBARUI\n"
        f"│\n"
        f"│  {new_value}\n"
        f"╰─ Dashboard user akan langsung pakai nilai baru ini.",
        reply_markup=_BOTINFO_BACK,
    )
    return ConversationHandler.END


async def reset_botinfo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset semua info bot ke nilai default."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    for key, (_, default) in _BOTINFO_FIELDS.items():
        db.set_setting(key, default)
    db.add_log("INFO", "Info bot direset ke default.")

    await query.edit_message_text(
        "╭─ 🔄 INFO BOT DIRESET\n│\n│ Semua nilai dikembalikan ke default.\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Lihat Info Bot", callback_data="cb_set_botinfo")],
            [InlineKeyboardButton("⬅️ Kembali",        callback_data="cb_settings")],
        ]),
    )


def build_botinfo_conversation():
    from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_botinfo_field_callback, pattern="^cb_editbotinfo_"),
        ],
        states={
            WAIT_BOTINFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_botinfo_input),
            ],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_settings)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )


def build_settings_conversation():
    from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_broadcast_delay_callback, pattern="^cb_set_broadcast_delay$"),
        ],
        states={
            WAIT_BROADCAST_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_broadcast_delay)
            ],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_settings)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
