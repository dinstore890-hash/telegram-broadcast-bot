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

import database as db
from config import is_admin, TEST_MODE
from services import broadcast_service, telegram_client

logger = logging.getLogger(__name__)

# ConversationHandler states
SELECT_TARGETS, WAIT_MESSAGE, CONFIRM_BROADCAST = range(20, 23)

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_target_keyboard(targets, selected: set) -> InlineKeyboardMarkup:
    buttons = []
    for t in targets:
        check = "☑" if t["id"] in selected else "☐"
        buttons.append([InlineKeyboardButton(
            f"{check} {t['title']}",
            callback_data=f"bc_toggle_{t['id']}",
        )])
    buttons.append([
        InlineKeyboardButton("✅ Lanjut",    callback_data="bc_next"),
        InlineKeyboardButton("❌ Batal",     callback_data="cb_dashboard"),
    ])
    return InlineKeyboardMarkup(buttons)


# ── Entry: pilih target ───────────────────────────────────────────────────────

async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    if broadcast_service.is_running():
        await query.edit_message_text(
            "⚠️ Broadcast sedang berjalan.\nGunakan tombol *⏸️ Pause* untuk menghentikan.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    targets = db.get_active_targets()
    if not targets:
        await query.edit_message_text(
            "⚠️ Tidak ada target aktif.\nTambahkan target dulu melalui *➕ Tambah Target*.",
            parse_mode="Markdown",
            reply_markup=_BACK_BTN,
        )
        return ConversationHandler.END

    selected = {t["id"] for t in targets}
    context.user_data["bc_selected"] = selected
    context.user_data["bc_targets"]  = [dict(t) for t in targets]

    test_badge = "  🧪 TEST MODE" if TEST_MODE else ""
    await query.edit_message_text(
        f"╭─ 📢 BROADCAST{test_badge}\n"
        f"│\n"
        f"│  Total target : {len(targets)}\n"
        f"│\n"
        f"╰─ Kirim pesan yang ingin dibroadcast.\nKetik /cancel untuk batal."
    )
    return WAIT_MESSAGE


async def toggle_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return SELECT_TARGETS

    target_id = int(query.data.replace("bc_toggle_", ""))
    selected: set = context.user_data.get("bc_selected", set())
    if target_id in selected:
        selected.discard(target_id)
    else:
        selected.add(target_id)
    context.user_data["bc_selected"] = selected

    targets = context.user_data.get("bc_targets", [])
    test_badge = "  🧪 TEST MODE" if TEST_MODE else ""
    await query.edit_message_text(
        f"╭─ 📢 PILIH TARGET{test_badge}\n│\n╰─ Centang/hapus centang target broadcast:",
        reply_markup=_build_target_keyboard(targets, selected),
    )
    return SELECT_TARGETS


async def bc_next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    selected = context.user_data.get("bc_selected", set())
    if not selected:
        await query.answer("⚠️ Pilih minimal 1 target!", show_alert=True)
        return SELECT_TARGETS

    await query.edit_message_text(
        "╭─ ✏️ TULIS PESAN BROADCAST\n"
        "│\n"
        "│ Kirim pesan yang ingin dibroadcast.\n"
        "│\n"
        "╰─ Ketik /cancel untuk batal."
    )
    return WAIT_MESSAGE


async def wait_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    message = update.message.text.strip()
    if len(message) > 4096:
        await update.message.reply_text("❌ Pesan terlalu panjang (maks 4096 karakter).")
        return WAIT_MESSAGE

    context.user_data["bc_message"] = message

    selected  = context.user_data.get("bc_selected", set())
    all_tgts  = context.user_data.get("bc_targets", [])
    chosen    = [t for t in all_tgts if t["id"] in selected]
    test_badge = "🧪 TEST MODE\n│\n" if TEST_MODE else ""

    target_lines = "\n".join(f"│  • {t['title']}" for t in chosen)
    preview = (
        f"╭─ 📢 PREVIEW BROADCAST\n"
        f"│\n"
        f"│ {test_badge}"
        f"│ Pesan:\n│  {message}\n"
        f"│\n"
        f"│ Target ({len(chosen)}):\n{target_lines}\n"
        f"╰─ Kirim atau batalkan?"
    )

    if len(preview) > 4096:
        preview = preview[:4050] + "\n│ ...terpotong.\n╰─"

    await update.message.reply_text(
        preview,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 KIRIM",  callback_data="bc_confirm"),
                InlineKeyboardButton("❌ BATAL",  callback_data="cb_dashboard"),
            ]
        ]),
    )
    return CONFIRM_BROADCAST


async def confirm_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    message  = context.user_data.get("bc_message", "")
    selected = context.user_data.get("bc_selected", set())
    all_tgts = context.user_data.get("bc_targets", [])
    chosen   = [t for t in all_tgts if t["id"] in selected]

    if not chosen or not message:
        await query.edit_message_text("❌ Data tidak valid.", reply_markup=_BACK_BTN)
        return ConversationHandler.END

    target_ids = [t["id"] for t in chosen]
    test_prefix = "🧪 TEST MODE\n" if TEST_MODE else ""
    status_msg = await query.edit_message_text(
        f"{test_prefix}📢 Memulai broadcast ke *{len(chosen)}* target...",
        parse_mode="Markdown",
    )

    last_edit = [0.0]

    async def progress_callback(event: str, state: dict) -> None:
        import time
        now = time.time()

        if event == "flood_wait":
            text = (
                f"⏳ *FloodWait*\n\n"
                f"Telegram meminta menunggu *{state.get('flood_seconds', '?')} detik*.\n"
                f"Bot akan melanjutkan otomatis setelah selesai."
            )
            try:
                await status_msg.edit_text(text, parse_mode="Markdown")
            except Exception:
                pass
            return

        total   = state["total"]
        current = state["current"]
        success = state["success"]
        failed  = state["failed"]

        if event in ("completed", "cancelled", "error", "paused") or (now - last_edit[0]) >= 2:
            icons = {"completed": "🎉", "cancelled": "⏹", "error": "💥", "paused": "⏸️"}
            suffix = ""
            if event in icons:
                labels = {"completed": "Selesai!", "cancelled": "Dihentikan.", "error": "Error!", "paused": "Dijeda."}
                suffix = f"\n\n{icons[event]} *{labels[event]}*"
                if event == "paused":
                    suffix += "\n\nGunakan tombol *▶️ Resume* atau *❌ Cancel*."

            text = (
                f"{test_prefix}"
                f"📢 *Broadcast Progress*\n\n"
                f"📨 Terkirim : {current}/{total}\n"
                f"✅ Berhasil : {success}\n"
                f"❌ Gagal    : {failed}"
                f"{suffix}"
            )

            keyboard = None
            if event == "paused":
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("▶️ Resume",  callback_data="bc_resume"),
                        InlineKeyboardButton("❌ Cancel",  callback_data="bc_cancel"),
                    ]
                ])

            try:
                await status_msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
                last_edit[0] = now
            except Exception:
                pass

    context.user_data.clear()
    context.application.create_task(
        broadcast_service.run_broadcast(message, target_ids, progress_callback, test_mode=TEST_MODE)
    )
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Broadcast dibatalkan.", reply_markup=_BACK_BTN)
    return ConversationHandler.END


# ── Pause / Resume / Cancel ───────────────────────────────────────────────────

async def pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    if not broadcast_service.is_running():
        await query.answer("ℹ️ Tidak ada broadcast yang sedang berjalan.", show_alert=True)
        return

    if broadcast_service.is_paused():
        await query.answer("⏸️ Broadcast sudah dalam kondisi dijeda.", show_alert=True)
        return

    broadcast_service.pause()
    state = broadcast_service.get_state()
    try:
        await query.edit_message_text(
            f"╭─ ⏸️ BROADCAST DIJEDA\n"
            f"│\n"
            f"│  ⤷  Terkirim : {state['current']}/{state['total']}\n"
            f"│  ⤷  Berhasil : {state['success']}\n"
            f"│  ⤷  Gagal    : {state['failed']}\n"
            f"│\n"
            f"╰─ Lanjutkan atau batalkan?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("▶️ Resume",  callback_data="bc_resume"),
                    InlineKeyboardButton("❌ Cancel",  callback_data="bc_cancel"),
                ]
            ]),
        )
    except Exception:
        await query.answer("⏸️ Broadcast dijeda!", show_alert=True)


async def resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    broadcast_service.resume()
    await query.answer("▶️ Broadcast dilanjutkan.", show_alert=True)


async def cancel_running_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    broadcast_service.cancel()
    await query.edit_message_text("⏹ Broadcast dibatalkan.", reply_markup=_BACK_BTN)


def build_broadcast_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_callback, pattern="^cb_broadcast$")],
        states={
            SELECT_TARGETS: [
                CallbackQueryHandler(toggle_target_callback, pattern="^bc_toggle_"),
                CallbackQueryHandler(bc_next_callback,       pattern="^bc_next$"),
            ],
            WAIT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wait_message_handler)
            ],
            CONFIRM_BROADCAST: [
                CallbackQueryHandler(confirm_broadcast_callback, pattern="^bc_confirm$"),
            ],
        },
        fallbacks=[MessageHandler(filters.COMMAND, cancel_broadcast)],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )
