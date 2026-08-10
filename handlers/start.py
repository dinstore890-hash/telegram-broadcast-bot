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
    from services.broadcast_service import get_state
    state = get_state()

    account_status = "🟢 Connected" if connected else "🔴 Disconnected"
    test_badge     = "  🧪 TEST MODE AKTIF" if TEST_MODE else ""
    broadcast_info = ""
    if state["running"]:
        broadcast_info = (
            f"\n⚡ Broadcast berjalan: {state['current']}/{state['total']}"
            f"  ✅{state['success']} ❌{state['failed']}"
        )

    return (
        f"🤖 *TELEGRAM BROADCAST*{test_badge}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Account : {account_status}\n"
        f"📋 Total Target  : {stats['total_targets']}\n"
        f"🟢 Active Target : {stats['active_targets']}\n"
        f"📨 Sent    : {stats['total_success']}\n"
        f"❌ Failed  : {stats['total_failed']}"
        f"{broadcast_info}"
    )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    from services.broadcast_service import is_running
    connected = await telegram_client.is_connected()
    text = await _build_dashboard(connected)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_main_keyboard(is_running()))


async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Akses ditolak.", show_alert=True)
        return

    from services.broadcast_service import is_running
    connected = await telegram_client.is_connected()
    text = await _build_dashboard(connected)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_main_keyboard(is_running()))
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
        "⚙️ *PENGATURAN*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🧪 Test Mode    : {test_status}\n"
        f"⏱️ Broadcast Delay : {BROADCAST_DELAY}s\n\n"
        "_Ubah pengaturan melalui file `.env` lalu restart bot._"
    )
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
        ]),
    )
