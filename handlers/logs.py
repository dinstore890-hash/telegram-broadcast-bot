from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from config import is_admin

_BACK_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")]
])

_LEVEL_ICON = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌"}


async def logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    logs = db.get_logs(limit=30)
    if not logs:
        await query.edit_message_text(
            "📜 Belum ada log.",
            reply_markup=_BACK_BTN,
        )
        return

    lines = ["📜 *LOGS (30 terakhir)*\n━━━━━━━━━━━━━━━━━━━━\n"]
    for log in logs:
        icon = _LEVEL_ICON.get(log["level"], "•")
        time = log["created_at"][11:19]
        lines.append(f"`[{time}]` {icon} {log['message']}")

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4050] + "\n\n_...terpotong._"

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="cb_logs")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="cb_dashboard")],
        ]),
    )
