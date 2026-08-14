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
WAIT_LEAVE_DELAY  = 12

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


async def groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await _show_groups(query)


async def _show_groups(query) -> None:
    targets = db.get_all_targets()

    if not targets:
        text = (
            "╭─ 📋 DAFTAR TARGET\n"
            "│\n"
            "│ Belum ada target terdaftar.\n"
            "╰─ Tambahkan target untuk mulai broadcast."
        )
    else:
        lines = [
            f"╭─ 📋 DAFTAR TARGET\n"
            f"│ Total: {len(targets)} target\n"
            f"│"
        ]
        for i, t in enumerate(targets, 1):
            status = "🟢" if t["is_active"] else "🔴"
            uname  = f"@{t['username']}" if t["username"] else "—"
            lines.append(
                f"│ {i}. {status} {t['title']}\n"
                f"│  ⤷  {uname} | ID: {t['chat_id']}"
            )
        lines.append("╰─ Pilih aksi di bawah.")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Tambah Target",  callback_data="cb_addtarget"),
            InlineKeyboardButton("🗑️ Hapus Target",  callback_data="cb_removetarget"),
        ],
        [
            InlineKeyboardButton("✅ Aktifkan Semua", callback_data="cb_activateall"),
            InlineKeyboardButton("📥 Import dari Akun", callback_data="cb_importgroups"),
        ],
        [
            InlineKeyboardButton("🚪 Leave Grup",    callback_data="cb_leavegroups"),
            InlineKeyboardButton("📦 Arsipkan Grup", callback_data="cb_archivegroups"),
        ],
        [InlineKeyboardButton("📋 Bulk Join & Tambah",  callback_data="cb_bulkjoin")],
        [InlineKeyboardButton("📤 Export Target",        callback_data="cb_exporttargets")],
        [InlineKeyboardButton("🔄 Refresh",             callback_data="cb_groups")],
        [InlineKeyboardButton("⬅️ Kembali",             callback_data="cb_dashboard")],
    ])

    if len(text) > 4096:
        text = text[:4050] + "\n\n...dan lebih banyak."

    try:
        await query.edit_message_text(text, reply_markup=keyboard)
    except Exception:
        pass


async def importgroups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    connected = await telegram_client.is_connected()
    if not connected:
        await query.edit_message_text(
            "╭─ ❌ TIDAK TERKONEKSI\n"
            "│\n"
            "│ Akun Telegram belum terkoneksi.\n"
            "╰─ Login dulu melalui menu 👤 Account.",
            reply_markup=_BACK_BTN,
        )
        return

    await query.edit_message_text("╭─ 🔍 Mengambil daftar grup/channel...\n╰─ Mohon tunggu.")

    groups = await telegram_client.get_joined_groups()
    if not groups:
        await query.edit_message_text("╭─ ⚠️ Tidak ada grup/channel ditemukan.\n╰─", reply_markup=_BACK_BTN)
        return

    context.user_data["import_groups"] = groups

    existing = {t["chat_id"]: t for t in db.get_all_targets()}
    new_count = sum(1 for g in groups if g["chat_id"] not in existing)
    update_count = sum(
        1 for g in groups
        if g["chat_id"] in existing
        and (
            existing[g["chat_id"]]["title"] != g["title"]
            or existing[g["chat_id"]]["username"] != g["username"]
        )
    )

    await query.edit_message_text(
        f"╭─ 📥 IMPORT DARI AKUN\n"
        f"│\n"
        f"│  ⤷  Ditemukan       : {len(groups)} grup/channel\n"
        f"│  ⤷  Baru (belum ada): {new_count}\n"
        f"│  ⤷  Ada perubahan   : {update_count}\n"
        f"│\n"
        f"╰─ Lanjutkan import semua?",
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
        await query.edit_message_text("╭─ ⚠️ Data import tidak ditemukan.\n╰─ Coba lagi.", reply_markup=_BACK_BTN)
        return

    added, updated, skipped = db.bulk_upsert_targets(groups)
    db.add_log("INFO", f"Import dari akun: {added} ditambahkan, {updated} diperbarui, {skipped} dilewati")

    await query.edit_message_text(
        f"╭─ ✅ IMPORT SELESAI\n"
        f"│\n"
        f"│  ⤷  Ditambahkan  : {added}\n"
        f"│  ⤷  Diperbarui   : {updated}\n"
        f"│  ⤷  Tidak berubah: {skipped}\n"
        f"╰─ Import selesai!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Daftar", callback_data="cb_groups")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
        ]),
    )


async def activateall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    count = db.activate_all_targets()
    db.add_log("INFO", f"Aktifkan semua target: {count} target diaktifkan")

    await query.edit_message_text(
        f"╭─ ✅ SEMUA TARGET DIAKTIFKAN\n"
        f"│\n"
        f"│  ⤷  Diaktifkan : {count} target\n"
        f"│\n"
        f"╰─ Semua target siap untuk broadcast.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Daftar", callback_data="cb_groups")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
        ]),
    )


async def exporttargets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    targets = db.get_active_targets()
    usernames = [f"@{t['username']}" for t in targets if t["username"]]
    if not usernames:
        await query.edit_message_text("╭─ ❌ Tidak ada target dengan username.\n╰─", reply_markup=_BACK_BTN)
        return
    chunk = 100
    for i in range(0, len(usernames), chunk):
        await query.message.reply_text("\n".join(usernames[i:i+chunk]))


async def bulkjoin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    # Tampilkan pilihan akun
    accounts = db.get_active_accounts()
    if not accounts:
        await query.edit_message_text(
            "╭─ ❌ TIDAK TERKONEKSI\n│\n│ Belum ada akun terdaftar.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    keyboard = []
    for acc in accounts:
        name = acc["name"] or acc["phone"]
        keyboard.append([InlineKeyboardButton(
            f"📱 {name} ({acc['phone']})",
            callback_data=f"cb_bulkjoin_acc_{acc['phone']}"
        )])
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_groups")])

    await query.edit_message_text(
        "╭─ 📋 BULK JOIN & TAMBAH\n"
        "│\n"
        "│ Pilih akun yang akan join grup:\n"
        "╰─",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def bulkjoin_acc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    phone = query.data.replace("cb_bulkjoin_acc_", "")
    context.user_data["bulkjoin_phone"] = phone

    await query.edit_message_text(
        f"╭─ 📋 BULK JOIN & TAMBAH\n"
        f"│\n"
        f"│ Akun: {phone}\n"
        f"│\n"
        f"│ Kirim daftar link/username,\n"
        f"│ satu per baris. Contoh:\n"
        f"│\n"
        f"│  https://t.me/grupA\n"
        f"│  @grupB\n"
        f"│\n"
        f"╰─ Ketik /cancel untuk batal."
    )
    return WAIT_BULK_INPUT


async def wait_bulk_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    lines = [l.strip() for l in update.message.text.strip().splitlines() if l.strip()]
    if not lines:
        await update.message.reply_text("╭─ ⚠️ Tidak ada link yang dikirim.\n╰─", reply_markup=_BACK_BTN)
        return ConversationHandler.END

    msg = await update.message.reply_text(f"╭─ ⏳ Memproses 0/{len(lines)}...\n╰─")

    phone = context.user_data.pop("bulkjoin_phone", None)
    success, failed = [], []
    for i, link in enumerate(lines, 1):
        await msg.edit_text(f"╭─ ⏳ Memproses {i}/{len(lines)}...\n│ 🔗 {link}\n╰─")
        result = await telegram_client.join_and_resolve(link, phone)
        if result.get("error"):
            failed.append(f"❌ {link} → {result['error']}")
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

    report = (
        f"╭─ 📊 HASIL BULK JOIN\n"
        f"│\n"
        f"│  ⤷  Total    : {len(lines)}\n"
        f"│  ⤷  Berhasil : {len(success)}\n"
        f"│  ⤷  Gagal    : {len(failed)}\n"
        f"│\n"
    )
    if success:
        report += "│ ✅ Berhasil:\n"
        for s in success[:20]:
            report += f"│  {s}\n"
        if len(success) > 20:
            report += f"│  ...dan {len(success)-20} lainnya\n"
    if failed:
        report += "│\n│ ❌ Gagal:\n"
        for f_ in failed[:10]:
            report += f"│  {f_}\n"
    report += "╰─ Selesai."

    db.add_log("INFO", f"Bulk join: {len(success)} berhasil, {len(failed)} gagal")

    await msg.edit_text(
        report,
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
            "╭─ ❌ TIDAK TERKONEKSI\n"
            "│\n"
            "│ Akun Telegram belum terkoneksi.\n"
            "╰─ Login dulu melalui menu 👤 Account.",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ ➕ TAMBAH TARGET\n"
        "│\n"
        "│ Kirim username atau link Telegram.\n"
        "│ Contoh:\n"
        "│  @namagrup\n"
        "│  https://t.me/namagrup\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return WAIT_TARGET_INPUT


async def wait_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    raw = update.message.text.strip()
    msg = await update.message.reply_text("╭─ 🔍 Memeriksa akses ke target...\n╰─")

    raw_username = raw
    if raw_username.startswith("https://t.me/"):
        raw_username = raw_username.replace("https://t.me/", "").split("/")[0]
    raw_username = raw_username.lstrip("@")

    info = await telegram_client.resolve_target(raw)
    if not info:
        await msg.edit_text(
            "╭─ ❌ TARGET TIDAK DAPAT DIAKSES\n"
            "│\n"
            "│ Pastikan akun sudah bergabung\n"
            "│ ke grup/channel tersebut.\n"
            "╰─",
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
            f"╭─ ✅ TARGET DITAMBAHKAN\n"
            f"│\n"
            f"│  ⤷  Nama : {info['title']}\n"
            f"│  ⤷  User : @{raw_username}\n"
            f"│  ⤷  Tipe : {info['chat_type']}\n"
            f"│  ⤷  ID   : {info['chat_id']}\n"
            f"╰─ Target siap digunakan.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Tambah Lagi", callback_data="cb_addtarget")],
                [InlineKeyboardButton("📋 Daftar Grup", callback_data="cb_groups")],
                [InlineKeyboardButton("⬅️ Kembali",     callback_data="cb_dashboard")],
            ]),
        )
    else:
        await msg.edit_text(
            f"╭─ ⚠️ SUDAH TERDAFTAR\n"
            f"│\n"
            f"│ {info['title']}\n"
            f"╰─ Target ini sudah ada di daftar.",
            reply_markup=_BACK_BTN,
        )

    return ConversationHandler.END


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("╭─ ❌ Dibatalkan.\n╰─", reply_markup=_BACK_BTN)
    return ConversationHandler.END


# ── Leave Grup ────────────────────────────────────────────────────────────────

async def leavegroups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tampilkan pilihan akun untuk leave grup."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    accounts = db.get_active_accounts()
    if not accounts:
        await query.edit_message_text(
            "╭─ ❌ TIDAK ADA AKUN\n│\n│ Belum ada akun terdaftar.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    delay = db.get_setting("leave_delay", "5")
    targets = db.get_all_targets()

    keyboard = []
    for acc in accounts:
        name = acc["name"] or acc["phone"]
        keyboard.append([InlineKeyboardButton(
            f"📱 {name} ({acc['phone']})",
            callback_data=f"cb_leaveacc_{acc['phone']}"
        )])
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_groups")])

    await query.edit_message_text(
        f"╭─ 🚪 LEAVE GRUP OTOMATIS\n"
        f"│\n"
        f"│  ⤷  Total target : {len(targets)} grup\n"
        f"│  ⤷  Delay leave  : {delay} detik\n"
        f"│\n"
        f"│ Pilih akun yang akan leave:\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


async def leavedelay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Minta input delay leave."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    current = db.get_setting("leave_delay", "5")
    await query.edit_message_text(
        f"╭─ ⏱️ ATUR DELAY LEAVE\n"
        f"│\n"
        f"│  ⤷  Delay saat ini: {current} detik\n"
        f"│\n"
        f"│ Kirim angka delay baru (detik).\n"
        f"│ Contoh: 3 atau 5\n"
        f"│ (Disarankan 3-10 detik)\n"
        f"╰─ Ketik /cancel untuk batal."
    )
    return WAIT_LEAVE_DELAY


async def wait_leave_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Simpan delay baru."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()
    try:
        delay = int(text)
        if delay < 1 or delay > 60:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "╭─ ⚠️ Input tidak valid.\n│ Masukkan angka 1-60.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    db.set_setting("leave_delay", str(delay))
    db.add_log("INFO", f"Delay leave diubah: {delay} detik")

    await update.message.reply_text(
        f"╭─ ✅ DELAY DIPERBARUI\n"
        f"│\n"
        f"│  ⤷  Delay leave: {delay} detik\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚪 Leave Grup", callback_data="cb_leavegroups")],
            [InlineKeyboardButton("⬅️ Kembali",    callback_data="cb_groups")],
        ]),
    )
    return ConversationHandler.END


async def leaveacc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Konfirmasi sebelum leave."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    phone = query.data.replace("cb_leaveacc_", "")
    targets = db.get_all_targets()
    delay = db.get_setting("leave_delay", "5")

    context.user_data["leave_phone"] = phone

    await query.edit_message_text(
        f"╭─ 🚪 KONFIRMASI LEAVE\n"
        f"│\n"
        f"│  ⤷  Akun    : {phone}\n"
        f"│  ⤷  Target  : {len(targets)} grup\n"
        f"│  ⤷  Delay   : {delay} detik per grup\n"
        f"│\n"
        f"│ ⚠️ Akun akan keluar dari semua\n"
        f"│ grup dalam daftar target!\n"
        f"╰─ Yakin lanjutkan?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Leave Semua", callback_data="cb_leaveconfirm")],
            [InlineKeyboardButton("❌ Batal",           callback_data="cb_leavegroups")],
        ]),
    )


async def leaveconfirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Proses leave semua grup dengan delay."""
    import asyncio
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    phone = context.user_data.pop("leave_phone", None)
    if not phone:
        await query.edit_message_text("╭─ ⚠️ Data tidak ditemukan.\n╰─ Coba lagi.", reply_markup=_BACK_BTN)
        return

    targets = db.get_all_targets()
    delay = int(db.get_setting("leave_delay", "5"))

    if not targets:
        await query.edit_message_text("╭─ ⚠️ Tidak ada target.\n╰─", reply_markup=_BACK_BTN)
        return

    msg = await query.edit_message_text(
        f"╭─ 🚪 LEAVE SEDANG BERJALAN\n"
        f"│\n"
        f"│  ⤷  Progress: 0/{len(targets)}\n"
        f"│  ⤷  Delay   : {delay} detik\n"
        f"╰─ Mohon tunggu..."
    )

    success_list, failed_list = [], []

    for i, target in enumerate(targets, 1):
        if i % 5 == 0 or i == 1:
            try:
                await msg.edit_text(
                    f"╭─ 🚪 LEAVE SEDANG BERJALAN\n"
                    f"│\n"
                    f"│  ⤷  Progress: {i}/{len(targets)}\n"
                    f"│  ⤷  Berhasil: {len(success_list)}\n"
                    f"│  ⤷  Gagal   : {len(failed_list)}\n"
                    f"╰─ Mohon tunggu..."
                )
            except Exception:
                pass

        result = await telegram_client.leave_group(target["chat_id"], phone)
        if result["success"]:
            success_list.append(target["title"])
        else:
            failed_list.append(f"{target['title']} → {result['error']}")

        if i < len(targets):
            await asyncio.sleep(delay)

    db.add_log("INFO", f"Leave grup [{phone}]: {len(success_list)} berhasil, {len(failed_list)} gagal")

    report = (
        f"╭─ ✅ LEAVE SELESAI\n"
        f"│\n"
        f"│  ⤷  Total   : {len(targets)}\n"
        f"│  ⤷  Berhasil: {len(success_list)}\n"
        f"│  ⤷  Gagal   : {len(failed_list)}\n"
    )
    if failed_list:
        report += "│\n│ ❌ Gagal:\n"
        for f_ in failed_list[:10]:
            report += f"│  {f_}\n"
        if len(failed_list) > 10:
            report += f"│  ...dan {len(failed_list)-10} lainnya\n"
    report += "╰─ Selesai."

    await msg.edit_text(
        report,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Daftar", callback_data="cb_groups")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
        ]),
    )


async def removetarget_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    targets = db.get_all_targets()
    if not targets:
        await query.edit_message_text(
            "╭─ 📋 HAPUS TARGET\n"
            "│\n"
            "│ Tidak ada target untuk dihapus.\n"
            "╰─",
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
        "╭─ 🗑️ HAPUS TARGET\n"
        "│\n"
        "╰─ Pilih target yang ingin dihapus:",
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
            f"╭─ 🗑️ TARGET DIHAPUS\n"
            f"│\n"
            f"│ {target['title']}\n"
            f"╰─ Berhasil dihapus.",
            reply_markup=_BACK_BTN,
        )
    else:
        await query.edit_message_text("╭─ ⚠️ Target tidak ditemukan.\n╰─", reply_markup=_BACK_BTN)


def build_leave_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(leavedelay_callback, pattern="^cb_leavedelay$"),
        ],
        states={
            WAIT_LEAVE_DELAY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_leave_delay)
            ],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_add)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )


def build_addtarget_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(addtarget_callback,   pattern="^cb_addtarget$"),
            CallbackQueryHandler(bulkjoin_callback,    pattern="^cb_bulkjoin$"),
            CallbackQueryHandler(bulkjoin_acc_callback, pattern="^cb_bulkjoin_acc_"),
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


# ── Arsipkan Grup ─────────────────────────────────────────────────────────────

async def archivegroups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    accounts = db.get_active_accounts()
    if not accounts:
        await query.edit_message_text(
            "╭─ ❌ TIDAK ADA AKUN\n│\n│ Belum ada akun terdaftar.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return

    delay = db.get_setting("leave_delay", "5")
    targets = db.get_all_targets()

    keyboard = []
    for acc in accounts:
        name = acc["name"] or acc["phone"]
        keyboard.append([InlineKeyboardButton(
            f"📱 {name} ({acc['phone']})",
            callback_data=f"cb_archiveacc_{acc['phone']}"
        )])
    keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_groups")])

    await query.edit_message_text(
        f"╭─ 📦 ARSIPKAN GRUP OTOMATIS\n"
        f"│\n"
        f"│  ⤷  Total target : {len(targets)} grup\n"
        f"│  ⤷  Delay        : {delay} detik\n"
        f"│\n"
        f"│ Pilih akun yang akan arsipkan:\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def archiveacc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    phone = query.data.replace("cb_archiveacc_", "")
    targets = db.get_all_targets()
    delay = db.get_setting("leave_delay", "5")
    context.user_data["archive_phone"] = phone

    await query.edit_message_text(
        f"╭─ 📦 KONFIRMASI ARSIPKAN\n"
        f"│\n"
        f"│  ⤷  Akun    : {phone}\n"
        f"│  ⤷  Target  : {len(targets)} grup\n"
        f"│  ⤷  Delay   : {delay} detik per grup\n"
        f"│\n"
        f"│ Semua grup dalam daftar target\n"
        f"│ akan dipindah ke Arsip.\n"
        f"╰─ Yakin lanjutkan?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Arsipkan Semua", callback_data="cb_archiveconfirm")],
            [InlineKeyboardButton("❌ Batal",              callback_data="cb_archivegroups")],
        ]),
    )


async def archiveconfirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import asyncio
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    phone = context.user_data.pop("archive_phone", None)
    if not phone:
        await query.edit_message_text("╭─ ⚠️ Data tidak ditemukan.\n╰─ Coba lagi.", reply_markup=_BACK_BTN)
        return

    targets = db.get_all_targets()
    delay = int(db.get_setting("leave_delay", "5"))

    if not targets:
        await query.edit_message_text("╭─ ⚠️ Tidak ada target.\n╰─", reply_markup=_BACK_BTN)
        return

    msg = await query.edit_message_text(
        f"╭─ 📦 ARSIPKAN SEDANG BERJALAN\n"
        f"│\n"
        f"│  ⤷  Progress: 0/{len(targets)}\n"
        f"│  ⤷  Delay   : {delay} detik\n"
        f"╰─ Mohon tunggu..."
    )

    success_list, failed_list = [], []

    for i, target in enumerate(targets, 1):
        if i % 5 == 0 or i == 1:
            try:
                await msg.edit_text(
                    f"╭─ 📦 ARSIPKAN SEDANG BERJALAN\n"
                    f"│\n"
                    f"│  ⤷  Progress: {i}/{len(targets)}\n"
                    f"│  ⤷  Berhasil: {len(success_list)}\n"
                    f"│  ⤷  Gagal   : {len(failed_list)}\n"
                    f"╰─ Mohon tunggu..."
                )
            except Exception:
                pass

        result = await telegram_client.archive_group(target["chat_id"], phone, archive=True)
        if result["success"]:
            success_list.append(target["title"])
        else:
            failed_list.append(f"{target['title']} → {result['error']}")
        if i < len(targets):
            await asyncio.sleep(delay)

    db.add_log("INFO", f"Arsipkan grup [{phone}]: {len(success_list)} berhasil, {len(failed_list)} gagal")

    report = (
        f"╭─ ✅ ARSIPKAN SELESAI\n"
        f"│\n"
        f"│  ⤷  Total   : {len(targets)}\n"
        f"│  ⤷  Berhasil: {len(success_list)}\n"
        f"│  ⤷  Gagal   : {len(failed_list)}\n"
    )
    if failed_list:
        report += "│\n│ ❌ Gagal:\n"
        for f_ in failed_list[:10]:
            report += f"│  {f_}\n"
        if len(failed_list) > 10:
            report += f"│  ...dan {len(failed_list)-10} lainnya\n"
    report += "╰─ Selesai."

    await msg.edit_text(
        report,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Lihat Daftar", callback_data="cb_groups")],
            [InlineKeyboardButton("⬅️ Kembali",      callback_data="cb_dashboard")],
        ]),
    )
