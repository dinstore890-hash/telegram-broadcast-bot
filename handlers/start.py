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
            InlineKeyboardButton("👤 Account",   callback_data="cb_account"),
            InlineKeyboardButton("⚙️ Pengaturan", callback_data="cb_settings"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh",   callback_data="cb_dashboard"),
        ],
    ])


def _user_keyboard(has_license: bool = False) -> InlineKeyboardMarkup:
    if has_license:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Mulai Broadcast", callback_data="cb_user_broadcast")],
            [InlineKeyboardButton("🎫 Cek Lisensi",     callback_data="cb_lisensi")],
            [InlineKeyboardButton("🛒 Perpanjang",      callback_data="cb_order")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
        [InlineKeyboardButton("📋 Cek Lisensi",   callback_data="cb_lisensi")],
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
        f"╭─ 💎 Gmail Market JASNEB 💎\n"
        f"│\n"
        f"│ Halo, {first_name + '! ' if first_name else ''}{greeting} 👋\n"
        f"{lisensi_info}"
        f"│ ∘₊✧──────✧₊∘∘₊✧──────✧₊∘\n"
        f"│  𝐎𝐰𝐧𝐞𝐫 @GmailMarket67\n"
        f"│  👥 Grup    : https://t.me/+sVVIxK_QnhthM2E1\n"
        f"│  📢 Channel : https://t.me/GmailxMarket\n"
        f"╰─ Gunakan menu untuk mulai promosi instant 🤖"
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
        f"╭─ 💎 Gmail Market JASNEB 💎{test_badge}\n"
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
        f"│       𝐎𝐰𝐧𝐞𝐫 @GmailMarket67\n"
        f"╰─ Gunakan menu untuk mulai promosi instant 🤖"
    )


async def _build_admin_dashboard(connected: bool) -> str:
    stats = db.get_stats()
    user_stats = db.get_user_stats()
    from services.broadcast_service import get_state
    state = get_state()

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
        f"╭─ 💎 Gmail Market JASNEB 💎{test_badge}\n"
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
        f"│       𝐎𝐰𝐧𝐞𝐫 @GmailMarket67\n"
        f"╰─ Gunakan menu untuk mulai promosi instant 🤖"
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

    text = (
        f"╭─ ⚙️ PENGATURAN\n"
        f"│\n"
        f"│  ⤷  Test Mode        : {test_status}\n"
        f"│  ⤷  Broadcast Delay  : {broadcast_delay}s\n"
        f"│  ⤷  Leave Delay      : {leave_delay}s\n"
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
