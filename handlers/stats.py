
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from config import is_admin
from services.broadcast_service import get_state

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    s     = db.get_stats()
    state = get_state()

    running_info = ""
    if state["running"]:
        status = "⏸️ Dijeda" if state["paused"] else "⚡ Berjalan"
        running_info = (
            f"\n\n*Broadcast Aktif:*\n"
            f"Status  : {status}\n"
            f"Progress: {state['current']}/{state['total']}\n"
            f"✅ {state['success']}  ❌ {state['failed']}"
        )

    text = (
        "📊 *STATISTIK BROADCAST*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 Total Target : {s['total_targets']}\n"
        f"🟢 Aktif        : {s['active_targets']}\n"
        f"🔴 Nonaktif     : {s['inactive_targets']}\n"
        f"📢 Broadcast    : {s['total_broadcasts']}\n"
        f"📨 Berhasil     : {s['total_success']}\n"
        f"❌ Gagal        : {s['total_failed']}"
        f"{running_info}"
    )

    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="cb_stats")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
        ]),
    )
