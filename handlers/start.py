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
        broadcast_info = (
            f"│\n"
            f"│ ⚡ Broadcast berjalan\n"
            f"│  ⤷  Progress : {state['current']}/{state['total']}\n"
            f"│  ⤷  Berhasil : {state['success']}\n"
            f"│  ⤷  Gagal    : {state['failed']}\n"
        )

    return (
        f"╭─ 💎 Gmail Market JASNEB 💎{test_badge}\n"
        f"│\n"
        f"│ Halo, {greeting} 👋\n"
        f"│\n"
        f"│ ⭐ 𝐀𝐊𝐓𝐈𝐕𝐈𝐓𝐀𝐒 𝐁𝐎𝐓\n"
        f"│  ⤷  Pengguna Baru   : {user_stats['new_users']}\n"
        f"│  ⤷  Total Pengguna  : {user_stats['total_users']}\n"
        f"│  ⤷  Kunjungan Baru  : {user_stats['new_visits']}\n"
        f"│  ⤷  Total Kunjungan : {user_stats['total_visits']}\n"
        f"│ ∘₊✧──────✧₊∘∘₊✧──────✧₊∘∘₊✧──────✧₊∘\n"
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
        broadcast_info = (
            f"│\n"
            f"│ ⚡ Broadcast berjalan\n"
            f"│  ⤷  Progress : {state['current']}/{state['total']}\n"
            f"│  ⤷  Berhasil : {state['success']}\n"
            f"│  ⤷  Gagal    : {state['failed']}\n"
        )

    return (
        f"╭─ 💎 Gmail Market JASNEB 💎{test_badge}\n"
        f"│\n"
        f"│ 👑 ADMIN DASHBOARD\n"
        f"│\n"
        f"│ 📡 Akun Telethon : {account_status}\n"
        f"│\n"
        f"│ ⭐ 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐊 𝐁𝐑𝐎𝐀𝐃𝐂𝐀𝐒𝐓\n"
        f"│  ⤷  Total Target  : {stats['total_targets']}\n"
        f"│  ⤷  Target Aktif  : {stats['active_targets']}\n"
        f"│  ⤷  Total Terkirim: {stats['total_success']}\n"
        f"│  ⤷  Total Gagal   : {stats['total_failed']}\n"
        f"{broadcast_info}"
        f"│ ⭐ 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐊 𝐔𝐒𝐄𝐑\n"
        f"│  ⤷  Pengguna Baru   : {user_stats['new_users']}\n"
        f"│  ⤷  Total Pengguna  : {user_stats['total_users']}\n"
        f"│  ⤷  Kunjungan Baru  : {user_stats['new_visits']}\n"
        f"│  ⤷  Total Kunjungan : {user_stats['total_visits']}\n"
        f"│ ∘₊✧──────✧₊∘∘₊✧──────✧₊∘∘₊✧──────✧₊∘\n"
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
        text = await _build_dashboard(connected)
        await update.message.reply_text(text)


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Akses ditolak.", show_alert=True)
        return

    from services.broadcast_service import is_running
    connected = await telegram_client.is_connected()
    text = await _build_admin_dashboard(connected)
    try:
        await query.edit_message_text(text, reply_markup=_main_keyboard(is_running()))
    except Exception:
        pass


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    test_status = "🟢 AKTIF" if TEST_MODE else "🔴 NONAKTIF"
    from config import BROADCAST_DELAY
    text = (
        f"╭─ ⚙️ PENGATURAN\n"
        f"│\n"
        f"│  ⤷  Test Mode       : {test_status}\n"
        f"│  ⤷  Broadcast Delay : {BROADCAST_DELAY}s\n"
        f"│\n"
        f"╰─ Ubah via file .env lalu restart bot."
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
        ]),
    )
