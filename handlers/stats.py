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

    s          = db.get_stats()
    user_stats = db.get_user_stats()
    state      = get_state()

    broadcast_info = ""
    if state["running"]:
        status = "⏸️ Dijeda" if state["paused"] else "⚡ Berjalan"
        broadcast_info = (
            f"│\n"
            f"│ ⚡ BROADCAST AKTIF\n"
            f"│  ⤷  Status   : {status}\n"
            f"│  ⤷  Progress : {state['current']}/{state['total']}\n"
            f"│  ⤷  Berhasil : {state['success']}\n"
            f"│  ⤷  Gagal    : {state['failed']}\n"
        )

    text = (
        f"╭─ 📊 STATISTIK\n"
        f"│\n"
        f"│ ⭐ BROADCAST\n"
        f"│  ⤷  Total Target  : {s['total_targets']}\n"
        f"│  ⤷  Aktif         : {s['active_targets']}\n"
        f"│  ⤷  Nonaktif      : {s['inactive_targets']}\n"
        f"│  ⤷  Total Broadcast: {s['total_broadcasts']}\n"
        f"│  ⤷  Terkirim      : {s['total_success']}\n"
        f"│  ⤷  Gagal         : {s['total_failed']}\n"
        f"│\n"
        f"│ ⭐ PENGGUNA\n"
        f"│  ⤷  Pengguna Baru   : {user_stats['new_users']}\n"
        f"│  ⤷  Total Pengguna  : {user_stats['total_users']}\n"
        f"│  ⤷  Kunjungan Baru  : {user_stats['new_visits']}\n"
        f"│  ⤷  Total Kunjungan : {user_stats['total_visits']}\n"
        f"{broadcast_info}"
        f"╰─ Data diperbarui setiap refresh."
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="cb_stats")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
        ]),
    )
