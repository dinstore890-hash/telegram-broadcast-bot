import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

import database as db
from config import is_admin, ADMIN_IDS, QRIS_FILE_ID

logger = logging.getLogger(__name__)

WAIT_BUKTI = 30

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])

# ── Paket & Harga ─────────────────────────────────────────────────────────────

PAKET = {
    "spesial":    {"label": "JASNEB SPESIAL",    "max_grup": 50},
    "spesialpp":  {"label": "JASNEB SPESIAL++",  "max_grup": 100},
}

# Harga default — bisa diubah admin dari dashboard
_HARGA_DEFAULT = {
    "spesial":   {7: 5000, 15: 8000, 30: 15000},
    "spesialpp": {7: 10000, 15: 15000, 30: 25000},
}


def _get_harga(paket_key: str, hari: int) -> int:
    """Ambil harga dari DB settings, fallback ke default."""
    key = f"paket_harga_{paket_key}_{hari}"
    default = _HARGA_DEFAULT.get(paket_key, {}).get(hari, 0)
    return int(db.get_setting(key, str(default)))


def _fmt_harga(harga: int) -> str:
    return f"Rp. {harga:,}".replace(",", ".")


def _paket_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 SPESIAL",    callback_data="ord_paket_spesial")],
        [InlineKeyboardButton("⚡ SPESIAL++",  callback_data="ord_paket_spesialpp")],
        [InlineKeyboardButton("⬅️ Kembali",    callback_data="cb_dashboard")],
    ])


def _durasi_keyboard(paket_key: str) -> InlineKeyboardMarkup:
    durasi_list = list(_HARGA_DEFAULT[paket_key].keys())
    buttons = []
    for hari in durasi_list:
        harga = _get_harga(paket_key, hari)
        buttons.append([InlineKeyboardButton(
            f"{hari} Hari • {_fmt_harga(harga)}",
            callback_data=f"ord_durasi_{paket_key}_{hari}",
        )])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_order")])
    return InlineKeyboardMarkup(buttons)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # Ambil harga dari DB (bisa diubah admin)
    sp7  = _fmt_harga(_get_harga("spesial",   7))
    sp15 = _fmt_harga(_get_harga("spesial",   15))
    sp30 = _fmt_harga(_get_harga("spesial",   30))
    pp7  = _fmt_harga(_get_harga("spesialpp", 7))
    pp15 = _fmt_harga(_get_harga("spesialpp", 15))
    pp30 = _fmt_harga(_get_harga("spesialpp", 30))

    bot_owner = db.get_setting("bot_owner", "@GmailMarket67")

    await query.edit_message_text(
        f"💎 JASNEB USERBOT BY {bot_owner}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"🔥 SPESIAL — 50 Grup\n"
        f"• 7 Hari  → {sp7}\n"
        f"• 15 Hari → {sp15}\n"
        f"• 30 Hari → {sp30}\n"
        "\n"
        f"⚡ SPESIAL++ — 100 Grup\n"
        f"• 7 Hari  → {pp7}\n"
        f"• 15 Hari → {pp15}\n"
        f"• 30 Hari → {pp30}\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Fitur Semua Paket:\n"
        "• Pakai akun Telegram sendiri\n"
        "• Broadcast 24 jam nonstop\n"
        "• Multi list pesan\n"
        "• Delay custom\n"
        "• Stop & lanjut kapan saja\n"
        "\n"
        "⚡ Bonus Spesial++:\n"
        "• 100 grup (2x lebih banyak)\n"
        "• Tanpa watermark\n"
        "\n"
        "👇 Pilih paket:",
        reply_markup=_paket_keyboard(),
    )


async def pilih_paket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    paket_key = query.data.replace("ord_paket_", "")
    paket = PAKET[paket_key]
    context.user_data["ord_paket"] = paket_key

    lines = "\n".join(
        f"│  ✦ {hari} Hari ➜ {_fmt_harga(_get_harga(paket_key, hari))}"
        for hari in _HARGA_DEFAULT[paket_key].keys()
    )

    await query.edit_message_text(
        f"💎 {paket['label']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"{lines}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Pilih durasi:",
        reply_markup=_durasi_keyboard(paket_key),
    )


async def pilih_durasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    parts = query.data.replace("ord_durasi_", "").rsplit("_", 1)
    paket_key = parts[0]
    hari = int(parts[1])
    harga = _get_harga(paket_key, hari)
    paket = PAKET[paket_key]

    context.user_data["ord_paket"]  = paket_key
    context.user_data["ord_hari"]   = hari
    context.user_data["ord_harga"]  = harga

    caption = (
        f"╭─ 💳 INFORMASI PEMBAYARAN\n"
        f"│\n"
        f"│ 📦 Paket  : {paket['label']}\n"
        f"│ ⏱ Durasi  : {hari} Hari\n"
        f"│ 💰 Total  : {_fmt_harga(harga)}\n"
        f"│\n"
        f"│ Scan QRIS di atas untuk bayar.\n"
        f"│\n"
        f"│ Setelah bayar, kirim:\n"
        f"│  1️⃣ Screenshot bukti transfer\n"
        f"│  2️⃣ Username Telegram kamu\n"
        f"│\n"
        f"╰─ Kirim bukti bayar sekarang 👇"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Batal", callback_data="cb_dashboard")]
    ])

    # Ambil file_id dari DB
    qris_id = db.get_setting("qris_file_id") or QRIS_FILE_ID

    await query.message.delete()
    if qris_id:
        await update.effective_chat.send_photo(
            photo=qris_id,
            caption=caption,
            reply_markup=keyboard,
        )
    else:
        await update.effective_chat.send_message(
            caption,
            reply_markup=keyboard,
        )

    return WAIT_BUKTI


async def wait_bukti_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    paket_key = context.user_data.get("ord_paket")
    hari      = context.user_data.get("ord_hari")
    harga     = context.user_data.get("ord_harga")

    if not paket_key or not hari:
        await update.message.reply_text("⚠️ Sesi order tidak ditemukan. Mulai ulang.", reply_markup=_BACK_BTN)
        return ConversationHandler.END

    paket = PAKET[paket_key]

    # Simpan order ke DB
    order_id = db.create_order(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        paket=paket["label"],
        max_grup=paket["max_grup"],
        durasi_hari=hari,
        harga=harga,
    )

    # Konfirmasi ke user
    await update.message.reply_text(
        f"╭─ ✅ BUKTI DITERIMA\n"
        f"│\n"
        f"│ Order ID : #{order_id}\n"
        f"│ Paket    : {paket['label']}\n"
        f"│ Durasi   : {hari} Hari\n"
        f"│ Total    : {_fmt_harga(harga)}\n"
        f"│\n"
        f"│ Bukti kamu sedang diverifikasi admin.\n"
        f"│ Tunggu konfirmasi dalam 1x24 jam.\n"
        f"╰─ Terima kasih! 🙏",
        reply_markup=_BACK_BTN,
    )

    # Cek apakah user sudah punya lisensi aktif
    existing_lic = db.get_license(user.id)
    from datetime import datetime
    if existing_lic and db.is_license_active(user.id):
        expired = existing_lic["expired_at"][:10]
        lic_info = (
            f"\n⚠️ PERPANJANGAN\n"
            f"📦 Paket lama  : {existing_lic['paket']}\n"
            f"👥 Grup lama   : {existing_lic['max_grup']}\n"
            f"📅 Expired lama: {expired}\n"
            f"\n➕ Setelah konfirmasi:\n"
            f"👥 Total Grup  : {existing_lic['max_grup'] + paket['max_grup']}\n"
        )
    else:
        lic_info = ""

    # Forward bukti ke semua admin
    caption_admin = (
        f"🔔 ORDER BARU #{order_id}\n\n"
        f"👤 User     : {user.first_name} (@{user.username or '-'})\n"
        f"🆔 ID       : {user.id}\n"
        f"📦 Paket    : {paket['label']}\n"
        f"⏱ Durasi   : {hari} Hari\n"
        f"💰 Total    : {_fmt_harga(harga)}\n"
        f"{lic_info}"
    )

    keyboard_admin = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Konfirmasi", callback_data=f"adm_confirm_{order_id}"),
            InlineKeyboardButton("❌ Tolak",      callback_data=f"adm_reject_{order_id}"),
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=update.message.photo[-1].file_id,
                    caption=caption_admin,
                    reply_markup=keyboard_admin,
                )
            elif update.message.document:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=update.message.document.file_id,
                    caption=caption_admin,
                    reply_markup=keyboard_admin,
                )
            else:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=caption_admin + f"\n📝 Pesan: {update.message.text or '-'}",
                    reply_markup=keyboard_admin,
                )
        except Exception as e:
            logger.error(f"Gagal forward ke admin {admin_id}: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Order dibatalkan.", reply_markup=_BACK_BTN)
    return ConversationHandler.END


async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    from handlers.start import _build_user_dashboard, _user_keyboard
    text, active = await _build_user_dashboard(query.from_user.id, query.from_user.first_name or "")
    await query.message.delete()
    await update.effective_chat.send_message(text, reply_markup=_user_keyboard(active))
    return ConversationHandler.END


# ── Admin: Konfirmasi / Tolak ─────────────────────────────────────────────────

async def admin_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    order_id = int(query.data.replace("adm_confirm_", ""))
    order = db.get_order(order_id)
    if not order:
        await query.answer("⚠️ Order tidak ditemukan.", show_alert=True)
        return

    db.confirm_order(order_id)
    db.activate_license(
        user_id=order["user_id"],
        paket=order["paket"],
        max_grup=order["max_grup"],
        durasi_hari=order["durasi_hari"],
    )
    db.add_log("INFO", f"Order #{order_id} dikonfirmasi untuk user {order['user_id']}")

    # Edit pesan admin
    await query.edit_message_caption(
        caption=query.message.caption + "\n\n✅ DIKONFIRMASI",
    ) if query.message.caption else await query.edit_message_text(
        query.message.text + "\n\n✅ DIKONFIRMASI"
    )

    # Notif ke user
    lic = db.get_license(order["user_id"])
    expired = lic["expired_at"][:16].replace("T", " ") if lic else "-"
    total_grup = lic["max_grup"] if lic else order["max_grup"]
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=(
                f"╭─ 🎉 PEMBAYARAN DIKONFIRMASI\n"
                f"│\n"
                f"│ Order ID   : #{order_id}\n"
                f"│ Paket      : {order['paket']}\n"
                f"│ Total Grup : {total_grup}\n"
                f"│ Expired    : {expired}\n"
                f"│\n"
                f"│ Akses kamu sudah aktif!\n"
                f"╰─ Ketik /start untuk mulai 🚀"
            ),
        )
    except Exception as e:
        logger.error(f"Gagal notif user {order['user_id']}: {e}")

    # Kirim invoice ke grup JASNEB AND GMAIL MARKET (topik Invoice)
    INVOICE_GROUP_ID = -1003936397248
    INVOICE_TOPIC_ID = 274
    # Sensor nama pembeli: huruf pertama + bintang
    if order['username']:
        raw = order['username']
        buyer = "@" + raw[0] + "*" * (len(raw) - 1)
    else:
        uid_str = str(order['user_id'])
        buyer = uid_str[0] + "*" * (len(uid_str) - 1)
    harga_fmt = f"Rp {order['harga']:,}".replace(",", ".")
    try:
        await context.bot.send_message(
            chat_id=INVOICE_GROUP_ID,
            message_thread_id=INVOICE_TOPIC_ID,
            text=(
                f"🧾 INVOICE TRANSAKSI\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⭐ Order ID   : #{order_id}\n"
                f"⭐ Pembeli    : {buyer}\n"
                f"⭐ Paket      : {order['paket']}\n"
                f"⭐ Durasi     : {order['durasi_hari']} Hari\n"
                f"⭐ Max Grup   : {order['max_grup']}\n"
                f"⭐ Total      : {harga_fmt}\n"
                f"⭐ Expired    : {expired}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Pembayaran Dikonfirmasi"
            ),
        )
    except Exception as e:
        logger.error(f"Gagal kirim invoice ke grup: {e}")


async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    order_id = int(query.data.replace("adm_reject_", ""))
    order = db.get_order(order_id)
    if not order:
        await query.answer("⚠️ Order tidak ditemukan.", show_alert=True)
        return

    db.reject_order(order_id)
    db.add_log("INFO", f"Order #{order_id} ditolak untuk user {order['user_id']}")

    await query.edit_message_caption(
        caption=query.message.caption + "\n\n❌ DITOLAK",
    ) if query.message.caption else await query.edit_message_text(
        query.message.text + "\n\n❌ DITOLAK"
    )

    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=(
                f"╭─ ❌ PEMBAYARAN DITOLAK\n"
                f"│\n"
                f"│ Order ID : #{order_id}\n"
                f"│\n"
                f"│ Bukti bayar kamu tidak valid.\n"
                f"│ Silakan order ulang atau hubungi\n"
                f"│ owner @GmailMarket67\n"
                f"╰─"
            ),
        )
    except Exception as e:
        logger.error(f"Gagal notif user {order['user_id']}: {e}")


async def setqris_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return

    # Cek apakah ada foto di pesan ini atau pesan yang di-reply
    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]

    if not photo:
        await update.message.reply_text(
            "╭─ ⚠️ CARA PAKAI\n"
            "│\n"
            "│ 1. Kirim/forward foto QRIS ke bot\n"
            "│ 2. Reply foto itu dengan /setqris\n"
            "╰─"
        )
        return

    file_id = photo.file_id
    db.set_setting("qris_file_id", file_id)
    await update.message.reply_text(
        "╭─ ✅ QRIS BERHASIL DISIMPAN\n"
        "│\n"
        "│ QRIS sudah aktif dan siap digunakan.\n"
        "╰─"
    )


# ── Admin: Ubah Harga Paket ───────────────────────────────────────────────────

WAIT_HARGA = 35

_HARGA_BACK = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 Harga Paket", callback_data="cb_manage_harga")],
    [InlineKeyboardButton("⬅️ Kembali",     callback_data="cb_dashboard")],
])


async def manage_harga_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    lines = "╭─ 💰 UBAH HARGA PAKET\n│\n"
    buttons = []
    for paket_key, durasi_dict in _HARGA_DEFAULT.items():
        label = PAKET[paket_key]["label"]
        lines += f"│ 📦 {label}:\n"
        for hari in durasi_dict:
            harga = _get_harga(paket_key, hari)
            lines += f"│  ⤷  {hari} Hari : {_fmt_harga(harga)}\n"
            buttons.append([InlineKeyboardButton(
                f"✏️ {label} {hari} Hari",
                callback_data=f"adm_setharga_{paket_key}_{hari}",
            )])
        lines += "│\n"

    lines += "╰─ Pilih yang ingin diubah:"
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")])

    await query.edit_message_text(lines, reply_markup=InlineKeyboardMarkup(buttons))


async def set_harga_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    parts = query.data.replace("adm_setharga_", "").rsplit("_", 1)
    paket_key = parts[0]
    hari = int(parts[1])
    current = _get_harga(paket_key, hari)

    context.user_data["harga_paket_key"] = paket_key
    context.user_data["harga_hari"]      = hari

    label = PAKET[paket_key]["label"]
    await query.edit_message_text(
        f"╭─ ✏️ UBAH HARGA\n"
        f"│\n"
        f"│  Paket  : {label}\n"
        f"│  Durasi : {hari} Hari\n"
        f"│  Saat ini: {_fmt_harga(current)}\n"
        f"│\n"
        f"│ Kirim harga baru (angka saja).\n"
        f"│ Contoh: 7500\n"
        f"╰─ /cancel untuk batal."
    )
    return WAIT_HARGA


async def wait_harga_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    paket_key = context.user_data.pop("harga_paket_key", None)
    hari      = context.user_data.pop("harga_hari", None)

    try:
        harga = int(update.message.text.strip())
        if harga <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "╭─ ⚠️ Input tidak valid. Masukkan angka positif.\n╰─",
            reply_markup=_HARGA_BACK,
        )
        return ConversationHandler.END

    db.set_setting(f"paket_harga_{paket_key}_{hari}", str(harga))
    db.add_log("INFO", f"Harga {paket_key} {hari} hari diubah ke {harga}")

    label = PAKET[paket_key]["label"]
    await update.message.reply_text(
        f"╭─ ✅ HARGA DIPERBARUI\n"
        f"│\n"
        f"│  {label} {hari} Hari\n"
        f"│  ➜ {_fmt_harga(harga)}\n"
        f"╰─ Harga baru langsung berlaku.",
        reply_markup=_HARGA_BACK,
    )
    return ConversationHandler.END


def build_harga_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(set_harga_callback, pattern="^adm_setharga_")],
        states={
            WAIT_HARGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_harga_input)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_order)],
        per_chat=True, per_user=True, per_message=False, allow_reentry=True,
    )


def build_order_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(pilih_durasi_callback, pattern="^ord_durasi_"),
        ],
        states={
            WAIT_BUKTI: [
                CallbackQueryHandler(cancel_order_callback, pattern="^cb_dashboard$"),
                MessageHandler(
                    (filters.PHOTO | filters.Document.ALL | filters.TEXT) & ~filters.COMMAND,
                    wait_bukti_handler,
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_order_callback, pattern="^cb_dashboard$"),
            CallbackQueryHandler(cancel_order_callback, pattern="^cb_order$"),
            MessageHandler(filters.COMMAND, cancel_order),
        ],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
