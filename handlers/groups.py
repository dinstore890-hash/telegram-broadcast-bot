import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import database as db
from config import is_admin
from services import telegram_client

logger = logging.getLogger(__name__)

WAIT_TARGET_INPUT = 10
WAIT_BULK_INPUT   = 11

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


# ── Daftar Grup ───────────────────────────────────────────────────────────────

async def groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await _show_groups(query)


async def _show_groups(query) -> None:
    targets = db.get_all_targets()

    if not targets:
        text = "📋 DAFTAR TARGET\n━━━━━━━━━━━━━━━━━━━━\n\nBelum ada target terdaftar."
    else:
        lines = ["📋 DAFTAR TARGET\n━━━━━━━━━━━━━━━━━━━━\n"]
        for i, t in enumerate(targets, 1):
            status = "🟢 Aktif" if t["is_active"] else "🔴 Nonaktif"
            uname  = f"@{t['username']}" if t["username"] else "—"
            lines.append(
                f"{i}. {t['title']}\n"
                f"   Username: {uname}\n"
                f"   Status: {status}\n"
                f"   ID: {t['chat_id']}"
            )
        text = "\n\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Tambah Target",  callback_data="cb_addtarget"),
            InlineKeyboardButton("🗑️ Hapus Target",  callback_data="cb_removetarget"),
        ],
        [InlineKeyboardButton("📥 Import dari Akun", callback_data="cb_importgroups")],
        [InlineKeyboardButton("📋 Bulk Join & Tambah", callback_data="cb_bulkjoin")],
        [InlineKeyboardButton("🔄 Refresh",           callback_data="cb_groups")],
        [InlineKeyboardButton("⬅️ Kembali",           callback_data="cb_dashboard")],
    ])

    if len(text) > 4096:
        text = text[:4050] + "\n\n...dan lebih banyak."

    try:
        await query.edit_message_text(text, reply_markup=keyboard)
    except Exception:
        pass


# ── Tambah Target ─────────────────────────────────────────────────────────────

# ── Import dari Akun ──────────────────────────────────────────────────────────

async def importgroups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    connected = await telegram_client.is_connected()
    if not connected:
        await query.edit_message_text(
            "❌ Akun Telegram belum terkoneksi. Login dulu melalui menu *👤 Account*.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return

    await query.edit_message_text("🔍 Mengambil daftar grup/channel dari akun...")

    groups = await telegram_client.get_joined_groups()
    if not groups:
        await query.edit_message_text("⚠️ Tidak ada grup/channel ditemukan.", reply_markup=_BACK_BTN)
        return

    context.user_data["import_groups"] = groups

    # Hitung yang sudah ada di DB
    import database as db2
    existing = {t["chat_id"] for t in db2.get_all_targets()}
    new_count = sum(1 for g in groups if g["chat_id"] not in existing)

    await query.edit_message_text(
        f"📥 *IMPORT DARI AKUN*\n\n"
        f"Ditemukan: *{len(groups)}* grup/channel\n"
        f"Baru (belum terdaftar): *{new_count}*\n\n"
        f"Lanjutkan import semua?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Import Semua", callback_data="cb_importconfirm")],
            [InlineKeyboardButton("❌ Batal",            callback_data="cb_groups")],
        ]),
    )


async def importconfirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    groups = context.user_data.pop("import_groups", [])
    if not groups:
        await query.edit_message_text("⚠️ Data import tidak ditemukan. Coba lagi.", reply_markup=_BACK_BTN)
        return

    added, skipped = db.bulk_add_targets(groups)
    db.add_log("INFO", f"Import dari akun: {added} ditambahkan, {skipped} dilewati")

    await query.edit_message_text(
        f"✅ *Import selesai!*\n\n"
        f"Berhasil ditambahkan: *{added}*\n"
        f"Sudah ada (dilewati): *{skipped}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Daftar", callback_data="cb_groups")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
        ]),
    )


# ── Bulk Join & Tambah ─────────────────────────────────────────────────────

async def bulkjoin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    connected = await telegram_client.is_connected()
    if not connected:
        await query.edit_message_text(
            "❌ Akun Telegram belum terkoneksi. Login dulu melalui menu *👤 Account*.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📋 *BULK JOIN & TAMBAH*\n\n"
        "Kirim daftar link/username, satu per baris.\n\n"
        "Contoh:\n"
        "https://t.me/grupA\n"
        "https://t.me/grupB\n"
        "@grupC\n\n"
        "_Akun akan otomatis join ke semua grup tersebut._\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return WAIT_BULK_INPUT


async def wait_bulk_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    lines = [l.strip() for l in update.message.text.strip().splitlines() if l.strip()]
    if not lines:
        await update.message.reply_text("⚠️ Tidak ada link yang dikirim.", reply_markup=_BACK_BTN)
        return ConversationHandler.END

    msg = await update.message.reply_text(f"⏳ Memproses 0/{len(lines)}...")

    success, failed = [], []
    for i, link in enumerate(lines, 1):
        await msg.edit_text(f"⏳ Memproses {i}/{len(lines)}...\n🔗 {link}")
        result = await telegram_client.join_and_resolve(link)
        if result.get("error"):
            failed.append(f"❌ {link} \u2192 {result['error']}")
        else:
            added = db.add_target(
                chat_id=result["chat_id"],
                title=result["title"],
                username=result["username"],
                chat_type=result["chat_type"],
            )
            label = result["title"] or result["username"]
            if added:
                success.append(f"✅ {label}")
            else:
                success.append(f"⚠️ {label} (sudah ada)")

    report = f"📊 *Hasil Bulk Join*\n\n"
    report += f"Total: {len(lines)} | Berhasil: {len(success)} | Gagal: {len(failed)}\n\n"
    if success:
        report += "*Berhasil:*\n" + "\n".join(success[:20])
        if len(success) > 20:
            report += f"\n_...dan {len(success)-20} lainnya_"
    if failed:
        report += "\n\n*Gagal:*\n" + "\n".join(failed[:10])

    db.add_log("INFO", f"Bulk join: {len(success)} berhasil, {len(failed)} gagal")

    await msg.edit_text(
        report,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Daftar", callback_data="cb_groups")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
        ]),
    )
    return ConversationHandler.END


async def addtarget_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    connected = await telegram_client.is_connected()
    if not connected:
        await query.edit_message_text(
            "❌ Akun Telegram belum terkoneksi.\n\nLogin dulu melalui menu *👤 Account*.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "➕ *TAMBAH TARGET*\n\n"
        "Kirim username atau link Telegram target.\n\n"
        "Contoh:\n`@namagrup`\n`https://t.me/namagrup`\n\n"
        "_Ketik /cancel untuk membatalkan._",
        parse_mode="Markdown",
    )
    return WAIT_TARGET_INPUT


async def wait_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    raw = update.message.text.strip()
    msg = await update.message.reply_text("🔍 Memeriksa akses ke target...")

    # Ekstrak username dari berbagai format input
    raw_username = raw
    if raw_username.startswith("https://t.me/"):
        raw_username = raw_username.replace("https://t.me/", "").split("/")[0]
    raw_username = raw_username.lstrip("@")

    info = await telegram_client.resolve_target(raw)
    if not info:
        await msg.edit_text(
            "❌ Target tidak dapat diakses oleh akun Telegram kamu.\n\n"
            "Pastikan akun sudah bergabung ke grup/channel tersebut.",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    info["username"] = raw_username

    added = db.add_target(
        chat_id=info["chat_id"],
        title=info["title"],
        username=info["username"],
        chat_type=info["chat_type"],
    )

    if added:
        db.add_log("INFO", f"Target ditambahkan: {info['title']} ({info['chat_id']})")
        await msg.edit_text(
            f"✅ *Target berhasil ditambahkan!*\n\n"
            f"Nama  : {info['title']}\n"
            f"User  : @{raw_username}\n"
            f"Tipe  : {info['chat_type']}\n"
            f"ID    : `{info['chat_id']}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Tambah Lagi",  callback_data="cb_addtarget")],
                [InlineKeyboardButton("📋 Daftar Grup",  callback_data="cb_groups")],
                [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
            ]),
        )
    else:
        await msg.edit_text(
            f"⚠️ Target *{info['title']}* sudah terdaftar.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )

    return ConversationHandler.END


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Dibatalkan.", reply_markup=_BACK_BTN)
    return ConversationHandler.END


# ── Hapus Target ──────────────────────────────────────────────────────────────

async def removetarget_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    targets = db.get_all_targets()
    if not targets:
        await query.edit_message_text(
            "📋 Tidak ada target untuk dihapus.",
            reply_markup=_BACK_BTN,
        )
        return

    buttons = []
    for t in targets:
        uname = f"@{t['username']}" if t["username"] else t["title"]
        label = f"{'🟢' if t['is_active'] else '🔴'} {t['title']} ({uname})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cb_del_{t['id']}")])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_groups")])

    await query.edit_message_text(
        "🗑️ *HAPUS TARGET*\n\nPilih target yang ingin dihapus:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def delete_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    target_id = int(query.data.replace("cb_del_", ""))
    target = db.get_target_by_id(target_id)
    if target:
        db.remove_target(target_id)
        db.add_log("INFO", f"Target dihapus: {target['title']}")
        await query.edit_message_text(
            f"🗑️ Target *{target['title']}* berhasil dihapus.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
    else:
        await query.edit_message_text("⚠️ Target tidak ditemukan.", reply_markup=_BACK_BTN)


def build_addtarget_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(addtarget_callback, pattern="^cb_addtarget$"),
            CallbackQueryHandler(bulkjoin_callback,  pattern="^cb_bulkjoin$"),
        ],
        states={
            WAIT_TARGET_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_target_input)
            ],
            WAIT_BULK_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_bulk_input)
            ],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_add)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
