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


# ── Kelola Lisensi (Admin) ────────────────────────────────────────────────────

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from config import is_admin


async def manage_licenses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    # Ambil semua lisensi
    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT l.id, l.user_id, l.paket, l.max_grup, l.expired_at,
                   u.username, u.first_name
            FROM licenses l
            LEFT JOIN users u ON l.user_id = u.user_id
            ORDER BY l.expired_at DESC
        """).fetchall()

    if not rows:
        await query.edit_message_text(
            "╭─ 👑 KELOLA LISENSI\n│\n│ Tidak ada lisensi.\n╰─",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
            ]),
        )
        return

    from datetime import datetime
    now = datetime.now().isoformat()

    text = "╭─ 👑 KELOLA LISENSI\n│\n"
    buttons = []
    for r in rows:
        status = "✅" if r["expired_at"] > now else "❌"
        name = r["username"] or r["first_name"] or str(r["user_id"])
        expired = r["expired_at"][:10]
        text += f"│ {status} @{name} — {r['paket'][:15]}\n│  ⤷  Exp: {expired}\n"
        buttons.append([InlineKeyboardButton(
            f"🗑️ Hapus @{name}",
            callback_data=f"adm_del_lic_{r['user_id']}"
        )])

    text += "╰─"
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def delete_license_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.replace("adm_del_lic_", ""))
    db.revoke_license(user_id)

    await query.edit_message_text(
        f"╭─ ✅ LISENSI DIHAPUS\n│\n│ User ID: {user_id}\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Kelola Lisensi", callback_data="cb_manage_licenses")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
        ]),
    )
