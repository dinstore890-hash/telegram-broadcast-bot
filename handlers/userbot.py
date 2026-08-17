import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError

import database as db
from config import API_ID, API_HASH, is_admin

logger = logging.getLogger(__name__)

# ── Conversation States ───────────────────────────────────────────────────────
(
    UB_WAIT_PHONE, UB_WAIT_OTP, UB_WAIT_2FA,
    UB_WAIT_ADD_GROUP, UB_WAIT_MSG_TITLE, UB_WAIT_MSG_CONTENT,
    UB_WAIT_DELAY,
) = range(60, 67)

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")]
])

# In-memory client store per user
_user_clients: dict[int, TelegramClient] = {}
# Temp phone_code_hash
_phone_hashes: dict[int, str] = {}


def _stop_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop", callback_data="ub_stop_broadcast")]])


# ── Helper: get/create Telethon client per user ───────────────────────────────

async def _get_user_client(user_id: int) -> TelegramClient | None:
    if user_id in _user_clients:
        client = _user_clients[user_id]
        if not client.is_connected():
            await client.connect()
        if await client.is_user_authorized():
            return client

    acc = db.get_user_account(user_id)
    if not acc or not acc["string_session"]:
        return None

    client = TelegramClient(StringSession(acc["string_session"]), API_ID, API_HASH)
    await client.connect()
    if await client.is_user_authorized():
        _user_clients[user_id] = client
        return client
    return None


# ── Dashboard User ────────────────────────────────────────────────────────────

async def ub_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        first_name = query.from_user.first_name or ""
        edit = query.edit_message_text
    else:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or ""
        edit = update.message.reply_text

    lic = db.get_license(user_id)
    if not lic or not db.is_license_active(user_id):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
        ])
        text = (
            "╭─ ⚠️ LISENSI TIDAK AKTIF\n"
            "│\n"
            "│ Lisensi kamu sudah habis atau belum aktif.\n"
            "╰─ Silakan order untuk melanjutkan."
        )
        await edit(text, reply_markup=kb)
        return ConversationHandler.END

    acc = db.get_user_account(user_id)
    targets = db.get_user_targets(user_id)
    messages = db.get_user_messages(user_id)
    delay = db.get_user_setting(user_id, "delay", "5")

    acc_status = f"🟢 {acc['name'] or acc['phone']}" if acc else "🔴 Belum login"
    expired = lic["expired_at"][:10]

    text = (
        f"╭─ 🤖 USERBOT DASHBOARD\n"
        f"│\n"
        f"│ Halo, {first_name}! 👋\n"
        f"│\n"
        f"│ 🎫 Paket    : {lic['paket']}\n"
        f"│ ⏳ Expired  : {expired}\n"
        f"│ 📱 Akun     : {acc_status}\n"
        f"│ 👥 Grup     : {len(targets)}/{lic['max_grup']}\n"
        f"│ 📝 List     : {len(messages)} pesan\n"
        f"│ ⏱️ Delay    : {delay} detik\n"
        f"╰─"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 Akun", callback_data="ub_account"),
            InlineKeyboardButton("👥 Grup & List", callback_data="ub_groups"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="ub_broadcast_menu"),
            InlineKeyboardButton("⚙️ Pengaturan", callback_data="ub_settings"),
        ],
        [InlineKeyboardButton("⚠️ Bantuan", callback_data="ub_bantuan")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
    ])

    await edit(text, reply_markup=keyboard)
    return ConversationHandler.END


# ── Akun ──────────────────────────────────────────────────────────────────────

async def ub_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    acc = db.get_user_account(user_id)
    if acc:
        text = (
            f"╭─ 📱 AKUN KAMU\n"
            f"│\n"
            f"│  ⤷  Nama  : {acc['name'] or '-'}\n"
            f"│  ⤷  HP    : {acc['phone']}\n"
            f"│  ⤷  User  : @{acc['username'] or '-'}\n"
            f"╰─"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Ganti Akun", callback_data="ub_login")],
            [InlineKeyboardButton("🗑️ Hapus Akun", callback_data="ub_logout")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")],
        ])
    else:
        text = (
            "╭─ 📱 AKUN\n"
            "│\n"
            "│ Belum ada akun terdaftar.\n"
            "│ Login dulu untuk mulai broadcast.\n"
            "╰─"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Login Akun", callback_data="ub_login")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")],
        ])

    await query.edit_message_text(text, reply_markup=kb)
    return ConversationHandler.END


async def ub_login_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

    await query.edit_message_text(
        "╭─ 🔑 LOGIN AKUN\n"
        "│\n"
        "│ Tap tombol di bawah untuk\n"
        "│ mengirim nomor HP kamu.\n"
        "│\n"
        "╰─ Atau ketik /cancel untuk batal."
    )
    await query.message.reply_text(
        "📞 Kontak Saya",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📞 Kontak Saya", request_contact=True)]],
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
    )
    return UB_WAIT_PHONE


async def ub_wait_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from telegram import ReplyKeyboardRemove

    user_id = update.effective_user.id

    # Terima dari contact share atau teks manual
    if update.message.contact:
        phone = update.message.contact.phone_number
        if not phone.startswith("+"):
            phone = f"+{phone}"
    elif update.message.text:
        phone = update.message.text.strip()
        if not phone.startswith("+"):
            await update.message.reply_text(
                "╭─ ⚠️ Format salah.\n│ Contoh: +628123456789\n╰─",
                reply_markup=ReplyKeyboardRemove(),
            )
            return UB_WAIT_PHONE
    else:
        await update.message.reply_text("╭─ ⚠️ Kirim nomor HP dulu.\n╰─")
        return UB_WAIT_PHONE

    await update.message.reply_text(
        "╭─ ⏳ Mengirim OTP...\n╰─",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        _user_clients[user_id] = client
        _phone_hashes[user_id] = result.phone_code_hash
        context.user_data["ub_phone"] = phone

        await update.message.reply_text(
            f"╭─ 📲 OTP TERKIRIM\n"
            f"│\n"
            f"│ Kode OTP dikirim ke {phone}\n"
            f"│\n"
            f"╰─ Kirim kode OTP kamu\n"
            f"Pisah dengan spasi. Contoh: 1 2 3 4 5"
        )
        return UB_WAIT_OTP
    except Exception as e:
        await update.message.reply_text(
            f"╭─ ❌ Gagal kirim OTP\n│ {e}\n╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END


async def ub_wait_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip().replace(" ", "")
    user_id = update.effective_user.id
    phone = context.user_data.get("ub_phone")

    try:
        client = _user_clients[user_id]
        phone_code_hash = _phone_hashes.get(user_id)
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return await _save_user_session(update, context, client, phone, user_id)
    except SessionPasswordNeededError:
        await update.message.reply_text(
            "╭─ 🔐 2FA AKTIF\n"
            "│\n"
            "│ Akun kamu punya password 2FA.\n"
            "╰─ Kirim password 2FA kamu:"
        )
        return UB_WAIT_2FA
    except Exception as e:
        await update.message.reply_text(f"╭─ ❌ OTP salah\n│ {e}\n╰─", reply_markup=_BACK_BTN)
        return ConversationHandler.END


async def ub_wait_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text.strip()
    user_id = update.effective_user.id
    phone = context.user_data.get("ub_phone")

    try:
        client = _user_clients[user_id]
        await client.sign_in(password=password)
        return await _save_user_session(update, context, client, phone, user_id)
    except Exception as e:
        await update.message.reply_text(f"╭─ ❌ Password salah\n│ {e}\n╰─", reply_markup=_BACK_BTN)
        return ConversationHandler.END


async def _save_user_session(update, context, client, phone, user_id) -> int:
    session_str = client.session.save()
    me = await client.get_me()
    name = f"{me.first_name or ''} {me.last_name or ''}".strip()
    username = me.username or ""

    db.add_user_account(user_id, phone, session_str, name, username)

    await update.message.reply_text(
        f"╭─ ✅ LOGIN BERHASIL\n"
        f"│\n"
        f"│  ⤷  Nama : {name}\n"
        f"│  ⤷  HP   : {phone}\n"
        f"╰─ Akun siap digunakan!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )
    return ConversationHandler.END


async def ub_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    db.delete_user_account(user_id)
    if user_id in _user_clients:
        client = _user_clients.pop(user_id)
        if client.is_connected():
            await client.disconnect()

    await query.edit_message_text(
        "╭─ ✅ AKUN DIHAPUS\n│\n│ Akun berhasil dihapus.\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )


# ── Grup & List ───────────────────────────────────────────────────────────────

async def ub_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    lic = db.get_license(user_id)
    targets = db.get_user_targets(user_id)
    messages = db.get_user_messages(user_id)

    text = (
        f"╭─ 👥 GRUP & LIST\n"
        f"│\n"
        f"│  ⤷  Grup    : {len(targets)}/{lic['max_grup'] if lic else '?'}\n"
        f"│  ⤷  Pesan   : {len(messages)}\n"
        f"╰─"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Tambah Grup", callback_data="ub_add_group"),
            InlineKeyboardButton("📋 Lihat Grup", callback_data="ub_list_groups"),
        ],
        [
            InlineKeyboardButton("📥 Import Grup", callback_data="ub_import_groups"),
            InlineKeyboardButton("🗑️ Reset Grup", callback_data="ub_reset_groups"),
        ],
        [
            InlineKeyboardButton("📝 Tambah Pesan", callback_data="ub_add_message"),
            InlineKeyboardButton("📋 Lihat Pesan", callback_data="ub_list_messages"),
        ],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")],
    ])

    await query.edit_message_text(text, reply_markup=kb)


async def ub_list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    targets = db.get_user_targets(user_id)
    if not targets:
        await query.edit_message_text(
            "╭─ 👥 DAFTAR GRUP\n│\n│ Belum ada grup.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return

    text = f"╭─ 👥 DAFTAR GRUP ({len(targets)})\n│\n"
    for i, t in enumerate(targets[:30], 1):
        icon = "🟢" if t["is_active"] else "🔴"
        uname = f"@{t['username']}" if t["username"] else "—"
        text += f"│ {i}. {icon} {t['title']}\n│  ⤷  {uname}\n"
    if len(targets) > 30:
        text += f"│ ...dan {len(targets)-30} lainnya\n"
    text += "╰─"

    # Tombol hapus per grup (maks 30)
    buttons = []
    for t in targets[:30]:
        buttons.append([
            InlineKeyboardButton(
                f"🗑️ {t['title'][:30]}",
                callback_data=f"ub_delgrp_{t['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton("✅ Aktifkan Semua", callback_data="ub_activate_all")])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="ub_groups")])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def ub_activate_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    count = db.activate_all_user_targets(user_id)
    await query.edit_message_text(
        f"╭─ ✅ SEMUA GRUP DIAKTIFKAN\n│\n│  ⤷  {count} grup diaktifkan\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_groups")]
        ]),
    )


async def ub_delete_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # callback_data format: ub_delgrp_{target_id}
    try:
        target_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer("❌ ID grup tidak valid.", show_alert=True)
        return

    success = db.delete_user_target(user_id, target_id)
    if success:
        await query.answer("✅ Grup berhasil dihapus.", show_alert=True)
    else:
        await query.answer("❌ Gagal menghapus grup.", show_alert=True)

    # Refresh daftar grup
    targets = db.get_user_targets(user_id)
    if not targets:
        await query.edit_message_text(
            "╭─ 👥 DAFTAR GRUP\n│\n│ Belum ada grup.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return

    text = f"╭─ 👥 DAFTAR GRUP ({len(targets)})\n│\n"
    for i, t in enumerate(targets[:30], 1):
        icon = "🟢" if t["is_active"] else "🔴"
        uname = f"@{t['username']}" if t["username"] else "—"
        text += f"│ {i}. {icon} {t['title']}\n│  ⤷  {uname}\n"
    if len(targets) > 30:
        text += f"│ ...dan {len(targets)-30} lainnya\n"
    text += "╰─"

    buttons = []
    for t in targets[:30]:
        buttons.append([
            InlineKeyboardButton(
                f"🗑️ {t['title'][:30]}",
                callback_data=f"ub_delgrp_{t['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton("✅ Aktifkan Semua", callback_data="ub_activate_all")])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="ub_groups")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def ub_add_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    lic = db.get_license(user_id)
    targets = db.get_user_targets(user_id)
    if lic and len(targets) >= lic["max_grup"]:
        await query.edit_message_text(
            f"╭─ ⚠️ BATAS GRUP\n│\n│ Kamu sudah mencapai batas {lic['max_grup']} grup.\n╰─",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "╭─ ➕ TAMBAH GRUP\n"
        "│\n"
        "│ Kirim username atau link grup.\n"
        "│ Satu per baris untuk bulk tambah.\n"
        "│\n"
        "│ Contoh:\n"
        "│  @namagrup\n"
        "│  https://t.me/namagrup\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return UB_WAIT_ADD_GROUP


async def ub_wait_add_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lines = [l.strip() for l in update.message.text.strip().splitlines() if l.strip()]

    client = await _get_user_client(user_id)
    if not client:
        await update.message.reply_text(
            "╭─ ❌ Akun belum login.\n╰─ Login dulu via menu Akun.",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    lic = db.get_license(user_id)
    targets = db.get_user_targets(user_id)
    remaining = (lic["max_grup"] - len(targets)) if lic else 0

    if remaining <= 0:
        await update.message.reply_text("╭─ ⚠️ Batas grup tercapai.\n╰─", reply_markup=_BACK_BTN)
        return ConversationHandler.END

    lines = lines[:remaining]
    msg = await update.message.reply_text(f"╭─ ⏳ Memproses 0/{len(lines)}...\n╰─")

    success, failed = [], []
    for i, link in enumerate(lines, 1):
        try:
            await msg.edit_text(f"╭─ ⏳ Memproses {i}/{len(lines)}...\n│ {link}\n╰─")
        except Exception:
            pass

        try:
            username = link.lstrip("@")
            if "t.me/" in username:
                username = username.split("t.me/")[-1].split("/")[0]

            entity = await client.get_entity(username)
            from telethon.tl.types import Channel, Chat
            if isinstance(entity, Channel):
                chat_id = int(f"-100{entity.id}")
                chat_type = "channel" if entity.broadcast else "supergroup"
                title = entity.title
                uname = entity.username or username
            elif isinstance(entity, Chat):
                chat_id = -entity.id
                chat_type = "group"
                title = entity.title
                uname = ""
            else:
                failed.append(f"❌ {link} → Tipe tidak didukung")
                continue

            added = db.add_user_target(user_id, chat_id, title, uname, chat_type)
            if added:
                success.append(f"✅ {title}")
            else:
                success.append(f"⚠️ {title} (sudah ada)")
        except Exception as e:
            failed.append(f"❌ {link} → {e}")

        await asyncio.sleep(2)

    report = (
        f"╭─ 📊 HASIL TAMBAH GRUP\n"
        f"│  ⤷  Berhasil: {len(success)}\n"
        f"│  ⤷  Gagal   : {len(failed)}\n"
    )
    if failed:
        report += "│\n│ ❌ Gagal:\n"
        for f_ in failed[:10]:
            report += f"│  {f_}\n"
    report += "╰─"

    await msg.edit_text(
        report,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )
    return ConversationHandler.END


async def ub_import_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    client = await _get_user_client(user_id)
    if not client:
        await query.edit_message_text("╭─ ❌ Login dulu.\n╰─", reply_markup=_BACK_BTN)
        return

    msg = await query.edit_message_text("╭─ ⏳ Mengambil daftar grup...\n╰─")

    from telethon.tl.types import Channel, Chat
    groups = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel) and not entity.broadcast:
            groups.append({
                "chat_id": int(f"-100{entity.id}"),
                "title": entity.title,
                "username": entity.username or "",
                "chat_type": "supergroup",
            })
        elif isinstance(entity, Chat):
            groups.append({
                "chat_id": -entity.id,
                "title": entity.title,
                "username": "",
                "chat_type": "group",
            })

    lic = db.get_license(user_id)
    max_grup = lic["max_grup"] if lic else 0
    current = db.get_user_targets(user_id)
    remaining = max_grup - len(current)
    groups = groups[:remaining]

    added, skipped = db.bulk_add_user_targets(user_id, groups)

    await msg.edit_text(
        f"╭─ ✅ IMPORT SELESAI\n"
        f"│  ⤷  Ditambahkan: {added}\n"
        f"│  ⤷  Sudah ada  : {skipped}\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )


async def ub_reset_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    count = db.clear_user_targets(user_id)
    await query.edit_message_text(
        f"╭─ 🗑️ GRUP DIRESET\n│\n│  ⤷  {count} grup dihapus\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )


# ── List Pesan ────────────────────────────────────────────────────────────────

async def ub_list_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    messages = db.get_user_messages(user_id)
    if not messages:
        await query.edit_message_text(
            "╭─ 📝 DAFTAR PESAN\n│\n│ Belum ada pesan.\n╰─",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Tambah Pesan", callback_data="ub_add_message")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_groups")],
            ]),
        )
        return

    buttons = []
    for m in messages:
        buttons.append([InlineKeyboardButton(
            f"📝 {m['title']}",
            callback_data=f"ub_del_msg_{m['id']}"
        )])
    buttons.append([InlineKeyboardButton("🗑️ Reset Semua", callback_data="ub_reset_messages")])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="ub_groups")])

    await query.edit_message_text(
        f"╭─ 📝 DAFTAR PESAN ({len(messages)})\n│\n│ Tap untuk hapus.\n╰─",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def ub_del_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    msg_id = int(query.data.replace("ub_del_msg_", ""))
    db.delete_user_message(msg_id, user_id)
    await ub_list_messages(update, context)


async def ub_reset_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    count = db.clear_user_messages(user_id)
    await query.edit_message_text(
        f"╭─ 🗑️ PESAN DIRESET\n│\n│  ⤷  {count} pesan dihapus\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )


async def ub_add_message_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "╭─ 📝 TAMBAH PESAN\n"
        "│\n"
        "│ Kirim judul pesan.\n"
        "│ Contoh: Promo Hari Ini\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return UB_WAIT_MSG_TITLE


async def ub_wait_msg_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["ub_msg_title"] = update.message.text.strip()
    await update.message.reply_text(
        "╭─ 📝 ISI PESAN\n"
        "│\n"
        "│ Sekarang kirim isi pesan.\n"
        "│ Bisa pakai format HTML/Markdown.\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return UB_WAIT_MSG_CONTENT


async def ub_wait_msg_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    title = context.user_data.get("ub_msg_title", "Pesan")
    content = update.message.text

    db.add_user_message(user_id, title, content)

    await update.message.reply_text(
        f"╭─ ✅ PESAN DISIMPAN\n"
        f"│\n"
        f"│  ⤷  Judul: {title}\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )
    return ConversationHandler.END


# ── Broadcast ─────────────────────────────────────────────────────────────────

# Cancel flags per user
_ub_cancel: dict[int, bool] = {}
_ub_paused: dict[int, bool] = {}


def _stop_pause_btn(paused: bool = False):
    if paused:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Lanjut", callback_data="ub_resume_broadcast"),
             InlineKeyboardButton("🛑 Stop", callback_data="ub_stop_broadcast")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ Pause", callback_data="ub_pause_broadcast"),
             InlineKeyboardButton("🛑 Stop", callback_data="ub_stop_broadcast")],
        ])


async def ub_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    messages = db.get_user_messages(user_id)
    targets = db.get_active_user_targets(user_id)

    if not targets:
        await query.edit_message_text(
            "╭─ ⚠️ BELUM ADA GRUP\n│\n│ Tambah grup dulu.\n╰─",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Grup & List", callback_data="ub_groups")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")],
            ]),
        )
        return

    if not messages:
        await query.edit_message_text(
            "╭─ ⚠️ BELUM ADA PESAN\n│\n│ Tambah pesan dulu.\n╰─",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Tambah Pesan", callback_data="ub_add_message")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")],
            ]),
        )
        return

    buttons = []
    for m in messages:
        title = m['title'] if m['title'] else f"Pesan #{m['id']}"
        buttons.append([InlineKeyboardButton(
            f"📨 {title}",
            callback_data=f"ub_start_bc_{m['id']}"
        )])
    buttons.append([InlineKeyboardButton("⬅️ Kembali", callback_data="ub_home")])

    await query.edit_message_text(
        f"╭─ 📢 PILIH PESAN\n"
        f"│\n"
        f"│  ⤷  Grup aktif: {len(targets)}\n"
        f"│\n"
        f"│ Pilih pesan yang akan dikirim:\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def ub_start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    msg_id = int(query.data.replace("ub_start_bc_", ""))
    msg_obj = db.get_user_message_by_id(msg_id, user_id)
    if not msg_obj:
        await query.edit_message_text("╭─ ⚠️ Pesan tidak ditemukan.\n╰─", reply_markup=_BACK_BTN)
        return

    client = await _get_user_client(user_id)
    if not client:
        await query.edit_message_text(
            "╭─ ❌ Akun belum login.\n╰─ Login dulu via menu Akun.",
            reply_markup=_BACK_BTN,
        )
        return

    targets = db.get_active_user_targets(user_id)
    delay = int(db.get_user_setting(user_id, "delay", "5"))
    _ub_cancel[user_id] = False
    _ub_paused[user_id] = False

    # Tentukan watermark berdasarkan paket
    lic = db.get_license(user_id)
    paket = (lic["paket"] or "").lower() if lic else ""
    is_plus = "++" in paket
    if is_plus:
        watermark = ""  # Spesial++ bebas watermark
    else:
        # Watermark bisa diubah admin lewat settings
        wm = db.get_setting("watermark_text", "")
        if wm:
            watermark = "\n\n" + wm
        else:
            watermark = "\n\n• *Promote Auto by* @jasnebbot\n• Development by @GmailMarket67"

    msg = await query.edit_message_text(
        f"╭─ 📢 BROADCAST BERJALAN\n"
        f"│  ⤷  Progress: 0/{len(targets)}\n"
        f"│  ⤷  Delay   : {delay} detik\n"
        f"╰─ Mohon tunggu...",
        reply_markup=_stop_pause_btn(),
    )

    broadcast_id = db.create_user_broadcast(user_id, msg_obj["content"], len(targets))

    async def _run():
        success = failed = 0
        for i, target in enumerate(targets, 1):
            if _ub_cancel.get(user_id):
                break

            # Cek pause — tunggu sampai di-resume
            if _ub_paused.get(user_id):
                while _ub_paused.get(user_id):
                    await asyncio.sleep(0.5)
                    if _ub_cancel.get(user_id):
                        break

            if _ub_cancel.get(user_id):
                break

            if i % 5 == 0 or i == 1:
                try:
                    await msg.edit_text(
                        f"╭─ 📢 BROADCAST BERJALAN\n"
                        f"│  ⤷  Progress: {i}/{len(targets)}\n"
                        f"│  ⤷  Berhasil: {success}\n"
                        f"│  ⤷  Gagal   : {failed}\n"
                        f"╰─ Mohon tunggu...",
                        reply_markup=_stop_pause_btn(),
                    )
                except Exception:
                    pass

            # Skip channel
            if target["chat_type"] == "channel":
                continue

            # Gabungkan konten + watermark
            content_with_wm = msg_obj["content"] + watermark if watermark else msg_obj["content"]

            try:
                await client.send_message(
                    target["chat_id"],
                    content_with_wm,
                    parse_mode="md",
                )
                success += 1
            except FloodWaitError as e:
                logger.warning(f"FloodWait {e.seconds}s user {user_id}")
                await asyncio.sleep(e.seconds + 3)
                try:
                    await client.send_message(
                        target["chat_id"],
                        content_with_wm,
                        parse_mode="md",
                    )
                    success += 1
                except Exception:
                    failed += 1
            except Exception as e:
                logger.error(f"Broadcast error user {user_id}: {e}")
                failed += 1

            if i < len(targets):
                # Sleep terpotong agar pause/stop lebih responsif
                elapsed = 0
                while elapsed < delay:
                    if _ub_cancel.get(user_id) or _ub_paused.get(user_id):
                        break
                    await asyncio.sleep(0.5)
                    elapsed += 0.5

        cancelled = _ub_cancel.get(user_id, False)
        _ub_cancel.pop(user_id, None)
        _ub_paused.pop(user_id, None)
        db.finish_user_broadcast(broadcast_id, success, failed)

        try:
            await msg.edit_text(
                f"╭─ {'⚠️ BROADCAST DIBATALKAN' if cancelled else '✅ BROADCAST SELESAI'}\n"
                f"│\n"
                f"│  ⤷  Total   : {len(targets)}\n"
                f"│  ⤷  Berhasil: {success}\n"
                f"│  ⤷  Gagal   : {failed}\n"
                f"╰─",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
                ]),
            )
        except Exception:
            pass

    asyncio.create_task(_run())


async def ub_stop_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("🛑 Menghentikan...")
    user_id = query.from_user.id
    _ub_cancel[user_id] = True
    _ub_paused.pop(user_id, None)
    try:
        await query.edit_message_text(
            "╭─ 🛑 BROADCAST DIHENTIKAN\n│\n│ Proses akan berhenti segera.\n╰─",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
            ]),
        )
    except Exception:
        pass


async def ub_pause_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("⏸️ Broadcast dijeda.")
    user_id = query.from_user.id
    _ub_paused[user_id] = True
    try:
        await query.edit_message_reply_markup(
            reply_markup=_stop_pause_btn(paused=True),
        )
    except Exception:
        pass


async def ub_resume_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("▶️ Broadcast dilanjutkan.")
    user_id = query.from_user.id
    _ub_paused[user_id] = False
    try:
        await query.edit_message_reply_markup(
            reply_markup=_stop_pause_btn(paused=False),
        )
    except Exception:
        pass


# ── Pengaturan ────────────────────────────────────────────────────────────────

async def ub_bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    bot_owner   = db.get_setting("bot_owner",   "@GmailMarket67")
    bot_grup    = db.get_setting("bot_grup",    "https://t.me/+sVVIxK_QnhthM2E1")
    bot_channel = db.get_setting("bot_channel", "https://t.me/GmailxMarket")
    cs_url      = f"https://t.me/{bot_owner.lstrip('@')}"

    await query.edit_message_text(
        f"⚠️ BANTUAN — JASNEB USERBOT\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"Pilih menu bantuan di bawah:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Cara Pasang",    callback_data="ub_cara_pasang")],
            [InlineKeyboardButton("💡 Fitur Unggulan", callback_data="ub_fitur_unggulan")],
            [InlineKeyboardButton("💬 Chat CS",        url=cs_url)],
            [InlineKeyboardButton("📢 Channel",        url=bot_channel if bot_channel.startswith("http") else f"https://t.me/{bot_channel.lstrip('@')}")],
            [InlineKeyboardButton("👥 Grup",           url=bot_grup)],
            [InlineKeyboardButton("⬅️ Kembali",        callback_data="ub_home")],
        ]),
    )


async def ub_cara_pasang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📚 CARA PASANG USERBOT\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🎁 Lakukan Pembelian\n"
        "⚪️ Tekan tombol 🛒 Order Sekarang\n"
        "⚪️ Pilih paket yang Anda inginkan\n"
        "⚪️ Selesaikan pembayaran sesuai instruksi\n"
        "\n"
        "👤 Login Akun Telegram\n"
        "⚪️ Tekan menu 📢 Mulai Broadcast\n"
        "⚪️ Pilih 👤 Akun → 🔑 Login\n"
        "⚪️ Kirim nomor HP (format: +628xxx)\n"
        "⚪️ Masukkan kode OTP yang diterima\n"
        "⚪️ Wajib spasi kode, contoh: 1 2 3 4 5\n"
        "⚪️ Jika ada 2FA, masukkan password\n"
        "\n"
        "👥 Tambah Grup Target\n"
        "⚪️ Menu 👥 Grup & List\n"
        "⚪️ Import dari akun atau tambah manual\n"
        "\n"
        "📝 Tambah Pesan\n"
        "⚪️ Menu ✉️ Pesan → Tambah Pesan\n"
        "⚪️ Isi judul dan isi pesan\n"
        "\n"
        "📢 Mulai Broadcast\n"
        "⚪️ Menu 📢 Broadcast\n"
        "⚪️ Pilih pesan → langsung kirim\n"
        "\n"
        "✅ Userbot siap digunakan!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali ke Bantuan", callback_data="ub_bantuan")],
        ]),
    )


async def ub_fitur_unggulan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💡 FITUR UNGGULAN USERBOT\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "🚀 AUTO PROMOSI\n"
        "⚪️ Broadcast ke ratusan grup\n"
        "⚪️ Pakai akun Telegram sendiri\n"
        "⚪️ Support semua format pesan\n"
        "⚪️ Notifikasi terkirim/gagal\n"
        "⚪️ Jeda custom & stop kapan saja\n"
        "\n"
        "💎 PAKET SPESIAL\n"
        "⚪️ Max 50 grup target\n"
        "⚪️ Multi list pesan\n"
        "⚪️ Watermark otomatis\n"
        "\n"
        "⚡ PAKET SPESIAL++\n"
        "⚪️ Semua fitur Spesial\n"
        "⚪️ Max 100 grup target\n"
        "⚪️ Tanpa watermark\n"
        "\n"
        "🛡️ KEAMANAN\n"
        "⚪️ Sesi login aman & terenkripsi\n"
        "⚪️ Data privat 100% terjaga\n"
        "⚪️ Bisa logout kapan saja\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 Solusi Lengkap untuk Promosi Digital!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali ke Bantuan", callback_data="ub_bantuan")],
        ]),
    )


async def ub_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    delay = db.get_user_setting(user_id, "delay", "5")

    if int(delay) <= 5:
        status = "⚡ Cepat (risiko limit tinggi)"
    elif int(delay) <= 15:
        status = "✅ Aman"
    else:
        status = "🛡️ Sangat Aman"

    await query.edit_message_text(
        f"⚙️ PENGATURAN JEDA\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"⏱️ Jeda saat ini : {delay} detik\n"
        f"📊 Status        : {status}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Pilih jeda per grup:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ 3 detik",  callback_data="ub_setdelay_3"),
                InlineKeyboardButton("🔥 5 detik",  callback_data="ub_setdelay_5"),
            ],
            [
                InlineKeyboardButton("✅ 10 detik", callback_data="ub_setdelay_10"),
                InlineKeyboardButton("✅ 15 detik", callback_data="ub_setdelay_15"),
            ],
            [
                InlineKeyboardButton("🛡️ 30 detik", callback_data="ub_setdelay_30"),
                InlineKeyboardButton("🛡️ 60 detik", callback_data="ub_setdelay_60"),
            ],
            [InlineKeyboardButton("✏️ Custom", callback_data="ub_set_delay")],
            [InlineKeyboardButton("⬅️ Kembali",    callback_data="ub_home")],
        ]),
    )
    return ConversationHandler.END


async def ub_setdelay_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    delay = int(query.data.replace("ub_setdelay_", ""))
    db.set_user_setting(user_id, "delay", str(delay))

    if delay <= 5:
        status = "⚡ Cepat (risiko limit tinggi)"
    elif delay <= 15:
        status = "✅ Aman"
    else:
        status = "🛡️ Sangat Aman"

    await query.edit_message_text(
        f"✅ JEDA DIPERBARUI\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"⏱️ Jeda : {delay} detik per grup\n"
        f"📊 Status: {status}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Pengaturan", callback_data="ub_settings")],
            [InlineKeyboardButton("🏠 Dashboard",  callback_data="ub_home")],
        ]),
    )


async def ub_set_delay_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current = db.get_user_setting(user_id, "delay", "5")
    await query.edit_message_text(
        f"╭─ ⏱️ ATUR DELAY CUSTOM\n"
        f"│\n"
        f"│  ⤷  Delay saat ini: {current} detik\n"
        f"│\n"
        f"╰─ Kirim angka delay (1-300 detik):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Kembali", callback_data="ub_settings")]
        ]),
    )
    return UB_WAIT_DELAY


async def ub_wait_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        delay = int(update.message.text.strip())
        if delay < 1 or delay > 300:
            raise ValueError
    except ValueError:
        await update.message.reply_text("╭─ ⚠️ Masukkan angka 1-300.\n╰─")
        return UB_WAIT_DELAY

    db.set_user_setting(user_id, "delay", str(delay))
    await update.message.reply_text(
        f"╭─ ✅ DELAY DIPERBARUI\n│\n│  ⤷  {delay} detik\n╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="ub_home")]
        ]),
    )
    return ConversationHandler.END


async def ub_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("╭─ ❌ Dibatalkan.\n╰─", reply_markup=_BACK_BTN)
    return ConversationHandler.END


# ── ConversationHandler ───────────────────────────────────────────────────────

async def ub_trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan info trial gratis."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Cek sudah pernah trial
    if db.has_used_trial(user_id):
        lic = db.get_license(user_id)
        active = lic and db.is_license_active(user_id)
        if active and lic["paket"] == "TRIAL":
            # Trial masih aktif
            expired = lic["expired_at"][11:16]
            await query.edit_message_text(
                f"╭─ 🎁 TRIAL AKTIF\n"
                f"│\n"
                f"│ Trial kamu masih aktif!\n"
                f"│ Berakhir pukul: {expired}\n"
                f"│\n"
                f"╰─ Gunakan fitur bot sekarang!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Mulai Broadcast", callback_data="cb_user_broadcast")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
                ]),
            )
        else:
            # Trial sudah habis
            await query.edit_message_text(
                f"╭─ ⏰ TRIAL BERAKHIR\n"
                f"│\n"
                f"│ Trial gratis kamu sudah berakhir.\n"
                f"│ Setiap akun hanya bisa trial 1 kali.\n"
                f"│\n"
                f"│ Order sekarang untuk lanjut\n"
                f"│ menikmati fitur lengkap!\n"
                f"╰─",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
                ]),
            )
        return

    # Belum pernah trial — tampilkan kebijakan
    bot_owner = db.get_setting("bot_owner", "@GmailMarket67")
    await query.edit_message_text(
        f"🎁 COBA GRATIS — TRIAL 1 JAM\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"🔔 Kebijakan Trial Userbot\n"
        f"\n"
        f"💎 Akses Trial Selama 1 Jam.\n"
        f"🥳 Mendapatkan Plan Basic (maks 10 grup).\n"
        f"💎 Setelah 1 Jam, akses akan berakhir.\n"
        f"⚠️ Setiap akun hanya bisa trial 1 kali.\n"
        f"\n"
        f"🥳 Risiko & Syarat:\n"
        f"• Gunakan dengan bijak\n"
        f"• Jangan spam berlebihan\n"
        f"• Admin berhak membatalkan trial\n"
        f"\n"
        f"✍️ Tekan ✅ Setuju Trial untuk memulai\n"
        f"\n"
        f"🚨 Promo paket lengkap — hubungi {bot_owner}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Setuju Trial", callback_data="ub_setuju_trial")],
            [InlineKeyboardButton("❌ Batalkan",     callback_data="cb_dashboard")],
        ]),
    )


async def ub_setuju_trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Aktifkan trial setelah user setuju."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Double check belum trial
    if db.has_used_trial(user_id):
        await query.edit_message_text(
            "╭─ ⚠️ Kamu sudah pernah trial.\n╰─",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛒 Order Sekarang", callback_data="cb_order")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
            ]),
        )
        return

    db.activate_trial(user_id)
    db.add_log("INFO", f"User {user_id} aktivasi trial 1 jam.")

    await query.edit_message_text(
        f"╭─ 🎉 TRIAL AKTIF!\n"
        f"│\n"
        f"│ ✅ Trial 1 jam berhasil diaktifkan!\n"
        f"│\n"
        f"│ 📦 Paket  : TRIAL\n"
        f"│ 👥 Max Grup: 10 grup\n"
        f"│ ⏱️ Durasi  : 1 Jam\n"
        f"│\n"
        f"│ Mulai broadcast sekarang!\n"
        f"│ Setelah 1 jam akses berakhir.\n"
        f"╰─",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Mulai Broadcast", callback_data="cb_user_broadcast")],
            [InlineKeyboardButton("🏠 Dashboard",       callback_data="cb_dashboard")],
        ]),
    )


def build_userbot_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(ub_login_start,       pattern="^ub_login$"),
            CallbackQueryHandler(ub_add_group_start,   pattern="^ub_add_group$"),
            CallbackQueryHandler(ub_add_message_start, pattern="^ub_add_message$"),
            CallbackQueryHandler(ub_set_delay_start,   pattern="^ub_set_delay$"),
        ],
        states={
            UB_WAIT_PHONE:       [
                MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), ub_wait_phone)
            ],
            UB_WAIT_OTP:         [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_wait_otp)],
            UB_WAIT_2FA:         [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_wait_2fa)],
            UB_WAIT_ADD_GROUP:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_wait_add_group)],
            UB_WAIT_MSG_TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_wait_msg_title)],
            UB_WAIT_MSG_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_wait_msg_content)],
            UB_WAIT_DELAY:       [MessageHandler(filters.TEXT & ~filters.COMMAND, ub_wait_delay)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, ub_cancel)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
