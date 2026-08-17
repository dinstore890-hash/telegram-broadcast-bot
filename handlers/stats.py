import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, filters,
)

import database as db
from config import is_admin
from services.broadcast_service import get_state

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])

# Conversation states
WAIT_ANNOUNCE = 80
WAIT_BAN_ID   = 81


# ── Statistik ─────────────────────────────────────────────────────────────────

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    s          = db.get_stats()
    user_stats = db.get_user_stats()
    state      = get_state()
    banned     = len(db.get_banned_users())

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
        f"│  ⤷  Total Target   : {s['total_targets']}\n"
        f"│  ⤷  Aktif          : {s['active_targets']}\n"
        f"│  ⤷  Total Broadcast: {s['total_broadcasts']}\n"
        f"│  ⤷  Terkirim       : {s['total_success']}\n"
        f"│  ⤷  Gagal          : {s['total_failed']}\n"
        f"│\n"
        f"│ ⭐ PENGGUNA\n"
        f"│  ⤷  Pengguna Baru  : {user_stats['new_users']}\n"
        f"│  ⤷  Total Pengguna : {user_stats['total_users']}\n"
        f"│  ⤷  Kunjungan Baru : {user_stats['new_visits']}\n"
        f"│  ⤷  Total Kunjungan: {user_stats['total_visits']}\n"
        f"│  ⤷  User Dibanned  : {banned}\n"
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


# ── Kelola Lisensi ────────────────────────────────────────────────────────────

async def manage_licenses_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

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
            [InlineKeyboardButton("⬅️ Kembali",        callback_data="cb_dashboard")],
        ]),
    )


# ── Kelola User (Ban/Unban) ───────────────────────────────────────────────────

async def manage_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    banned = db.get_banned_users()
    all_users = db.get_all_users()
    active_users = [u for u in all_users if not u["is_banned"]]

    text = (
        f"╭─ 👥 KELOLA USER\n"
        f"│\n"
        f"│  ⤷  Total User  : {len(all_users)}\n"
        f"│  ⤷  Aktif       : {len(active_users)}\n"
        f"│  ⤷  Dibanned    : {len(banned)}\n"
        f"│\n"
    )
    for u in all_users[:20]:
        name   = u["username"] or u["first_name"] or "NoName"
        uid    = u["user_id"]
        joined = u["joined_at"][:16].replace("T", " ") if u["joined_at"] else "—"
        ban    = " 🚫" if u["is_banned"] else ""
        text  += f"│ • {name}{ban}\n│   ⤷ ID: {uid} | {joined}\n"
    if len(all_users) > 20:
        text += f"│ ...dan {len(all_users)-20} lainnya\n"
    text += "╰─ Pilih aksi:"

    buttons = [
        [InlineKeyboardButton("🚫 Ban User",       callback_data="adm_show_userlist_ban")],
        [InlineKeyboardButton("✅ Unban User",     callback_data="adm_show_userlist_unban")],
        [InlineKeyboardButton("🗑️ Reset Data User", callback_data="adm_show_userlist_reset")],
        [InlineKeyboardButton("⬅️ Kembali",        callback_data="cb_dashboard")],
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_userlist_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan semua user aktif dengan tombol Ban per user."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    all_users = db.get_all_users()
    active_users = [u for u in all_users if not u["is_banned"]]

    if not active_users:
        await query.edit_message_text(
            "╭─ 👥 DAFTAR USER\n│\n│ Tidak ada user aktif.\n╰─",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="cb_manage_users")]]),
        )
        return

    text = "╭─ 🚫 PILIH USER UNTUK DIBAN\n│\n"
    buttons = []
    for u in active_users[:30]:  # max 30 biar tidak overflow
        name = u["username"] or u["first_name"] or "NoName"
        uid  = u["user_id"]
        joined = u["joined_at"][:16].replace("T", " ") if u["joined_at"] else "—"
        text += f"│ • {name} | {uid}\n│   ⤷ Masuk: {joined}\n"
        buttons.append([InlineKeyboardButton(
            f"🚫 Ban {name} ({uid})",
            callback_data=f"adm_ban_{uid}",
        )])

    text += "╰─"
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_manage_users")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_userlist_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan semua user banned dengan tombol Unban per user."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    banned = db.get_banned_users()

    if not banned:
        await query.edit_message_text(
            "╭─ ✅ UNBAN USER\n│\n│ Tidak ada user yang dibanned.\n╰─",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="cb_manage_users")]]),
        )
        return

    text = "╭─ ✅ PILIH USER UNTUK DIUNBAN\n│\n"
    buttons = []
    for u in banned:
        name = u["username"] or u["first_name"] or "NoName"
        uid  = u["user_id"]
        text += f"│ • {name} | {uid}\n"
        buttons.append([InlineKeyboardButton(
            f"✅ Unban {name} ({uid})",
            callback_data=f"adm_unban_{uid}",
        )])

    text += "╰─"
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_manage_users")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def ban_direct_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban user langsung dari tombol list."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.replace("adm_ban_", ""))
    db.ban_user(user_id)
    db.add_log("INFO", f"User {user_id} dibanned oleh admin.")

    await query.edit_message_text(
        f"╭─ ✅ USER DIBANNED\n│\n│ User ID: {user_id}\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Kelola User", callback_data="cb_manage_users")],
            [InlineKeyboardButton("⬅️ Kembali",     callback_data="cb_dashboard")],
        ]),
    )


async def ban_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ 🚫 BAN USER\n"
        "│\n"
        "│ Kirim user_id yang mau dibanned.\n"
        "│ Contoh: 123456789\n"
        "╰─ /cancel untuk batal."
    )
    return WAIT_BAN_ID


async def wait_ban_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "╭─ ⚠️ Masukkan angka user_id yang valid.\n╰─",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kelola User", callback_data="cb_manage_users")]]),
        )
        return ConversationHandler.END

    db.ban_user(target_id)
    db.add_log("INFO", f"User {target_id} dibanned oleh admin.")

    await update.message.reply_text(
        f"╭─ ✅ USER DIBANNED\n│\n│ User ID: {target_id}\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Kelola User", callback_data="cb_manage_users")],
            [InlineKeyboardButton("⬅️ Kembali",     callback_data="cb_dashboard")],
        ]),
    )
    return ConversationHandler.END


async def unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.replace("adm_unban_", ""))
    db.unban_user(user_id)
    db.add_log("INFO", f"User {user_id} di-unban oleh admin.")

    await query.edit_message_text(
        f"╭─ ✅ USER DI-UNBAN\n│\n│ User ID: {user_id}\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Kelola User", callback_data="cb_manage_users")],
            [InlineKeyboardButton("⬅️ Kembali",     callback_data="cb_dashboard")],
        ]),
    )


    await query.edit_message_text(
        f"╭─ ✅ USER DI-UNBAN\n│\n│ User ID: {user_id}\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Kelola User", callback_data="cb_manage_users")],
            [InlineKeyboardButton("⬅️ Kembali",     callback_data="cb_dashboard")],
        ]),
    )


async def show_userlist_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan daftar user untuk pilih yang mau direset datanya."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    all_users = db.get_all_users()
    if not all_users:
        await query.edit_message_text(
            "╭─ 👥 RESET DATA\n│\n│ Tidak ada user.\n╰─",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="cb_manage_users")]]),
        )
        return

    text = "╭─ 🗑️ PILIH USER UNTUK RESET DATA\n│\n"
    buttons = []
    for u in all_users[:30]:
        name = u["username"] or u["first_name"] or "NoName"
        uid  = u["user_id"]
        text += f"│ • {name} | {uid}\n"
        buttons.append([InlineKeyboardButton(
            f"🗑️ Reset {name}",
            callback_data=f"adm_reset_menu_{uid}",
        )])
    text += "╰─"
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_manage_users")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def reset_user_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan pilihan reset untuk user tertentu."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    user_id = int(query.data.replace("adm_reset_menu_", ""))
    u = next((x for x in db.get_all_users() if x["user_id"] == user_id), None)
    name = u["username"] or u["first_name"] if u else str(user_id)

    await query.edit_message_text(
        f"╭─ 🗑️ RESET DATA USER\n│\n│ User: {name} ({user_id})\n│\n│ Pilih data yang mau direset:\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Reset Grup",   callback_data=f"adm_reset_grup_{user_id}")],
            [InlineKeyboardButton("📝 Reset Pesan",  callback_data=f"adm_reset_pesan_{user_id}")],
            [InlineKeyboardButton("📱 Reset Akun",   callback_data=f"adm_reset_akun_{user_id}")],
            [InlineKeyboardButton("💣 Reset Semua",  callback_data=f"adm_reset_all_{user_id}")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="adm_show_userlist_reset")],
        ]),
    )


async def reset_user_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Eksekusi reset data user."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    data = query.data  # adm_reset_{tipe}_{user_id}
    parts = data.split("_")
    tipe    = parts[2]  # grup / pesan / akun / all
    user_id = int(parts[3])

    if tipe == "grup":
        count = db.clear_user_targets(user_id)
        msg = f"✅ {count} grup berhasil dihapus."
    elif tipe == "pesan":
        count = db.clear_user_messages(user_id)
        msg = f"✅ {count} pesan berhasil dihapus."
    elif tipe == "akun":
        db.delete_user_account(user_id)
        msg = "✅ Akun userbot berhasil direset."
    elif tipe == "all":
        g = db.clear_user_targets(user_id)
        p = db.clear_user_messages(user_id)
        db.delete_user_account(user_id)
        msg = f"✅ Semua data direset. ({g} grup, {p} pesan, akun)"
    else:
        msg = "❌ Tipe reset tidak dikenal."

    db.add_log("INFO", f"Admin reset data user {user_id}: {tipe}")
    await query.edit_message_text(
        f"╭─ 🗑️ RESET SELESAI\n│\n│ {msg}\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Kelola User", callback_data="cb_manage_users")],
        ]),
    )
    """Handler /cancel untuk semua conversation admin."""
    context.user_data.clear()
    await update.message.reply_text(
        "╭─ ❌ Dibatalkan.\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Dashboard", callback_data="cb_dashboard")]
        ]),
    )
    return ConversationHandler.END


def build_ban_conversation():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(ban_new_callback, pattern="^adm_ban_new$")],
        states={
            WAIT_BAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_ban_id)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, _cancel_admin)],
        per_chat=True, per_user=True, per_message=False, allow_reentry=True,
    )


# ── Broadcast Pengumuman ke Semua User ───────────────────────────────────────

async def announce_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    user_ids = db.get_all_user_ids()
    await query.edit_message_text(
        f"╭─ 📢 BROADCAST PENGUMUMAN\n"
        f"│\n"
        f"│  ⤷  Total penerima: {len(user_ids)} user\n"
        f"│\n"
        f"│ Kirim teks pengumuman.\n"
        f"│ Mendukung format bold, italic, dll.\n"
        f"╰─ /cancel untuk batal."
    )
    return WAIT_ANNOUNCE


async def wait_announce_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    if not text:
        return ConversationHandler.END

    user_ids = db.get_all_user_ids()
    bot = update.get_bot()

    progress_msg = await update.message.reply_text(
        f"╭─ 📢 MENGIRIM PENGUMUMAN\n│\n│  ⤷  0/{len(user_ids)} terkirim\n╰─"
    )

    async def _send():
        sent = failed = 0
        for uid in user_ids:
            try:
                await bot.send_message(
                    uid,
                    f"📢 *PENGUMUMAN*\n\n{text}",
                    parse_mode="Markdown",
                )
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)

        try:
            await progress_msg.edit_text(
                f"╭─ ✅ PENGUMUMAN TERKIRIM\n"
                f"│\n"
                f"│  ⤷  Berhasil : {sent}\n"
                f"│  ⤷  Gagal    : {failed}\n"
                f"╰─",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
                ]),
            )
        except Exception:
            pass

    asyncio.create_task(_send())
    db.add_log("INFO", f"Broadcast pengumuman dikirim ke {len(user_ids)} user.")
    return ConversationHandler.END


def build_announce_conversation():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(announce_callback, pattern="^cb_announce$")],
        states={
            WAIT_ANNOUNCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_announce_text)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, _cancel_admin)],
        per_chat=True, per_user=True, per_message=False, allow_reentry=True,
    )
