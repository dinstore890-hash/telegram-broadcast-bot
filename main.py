import asyncio
import logging
import os
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

from config import BOT_TOKEN, LOG_DIR
from database import init_db
from services import telegram_client

from handlers.start import (
    start_handler, dashboard_callback, settings_callback,
    lisensi_callback, set_broadcast_delay_callback,
    build_settings_conversation,
)
from handlers.user_broadcast import build_user_broadcast_conversation
from handlers.account import (
    account_callback, reconnect_callback, logout_callback,
    build_login_conversation, delacc_callback,
)
from handlers.groups import (
    groups_callback, removetarget_callback, delete_target_callback,
    importgroups_callback, importconfirm_callback,
    bulkjoin_callback, exporttargets_callback, activateall_callback,
    leavegroups_callback, leavedelay_callback, leaveacc_callback, leaveconfirm_callback,
    build_addtarget_conversation, build_leave_conversation,
)
from handlers.broadcast import (
    pause_callback, resume_callback, cancel_running_callback,
    build_broadcast_conversation,
)
from handlers.stats import stats_callback
from config import is_admin
import database as db
from handlers.logs import logs_callback
from handlers.order import (
    order_callback, pilih_paket_callback,
    admin_confirm_callback, admin_reject_callback,
    build_order_conversation, setqris_handler,
)

# ── Logging setup ─────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


async def post_init(app) -> None:
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("start", "🚀 Buka Dashboard"),
        BotCommand("refresh", "🔄 Refresh Dashboard"),
    ])
    await telegram_client.load_accounts_from_db()
    connected = await telegram_client.connect_all()
    if connected:
        logger.info(f"Telethon connected: {len(connected)} akun — {connected}")
    else:
        logger.warning("Telethon: belum ada akun login. Gunakan menu 👤 Account untuk tambah akun.")


async def post_shutdown(app) -> None:
    await telegram_client.disconnect()
    logger.info("Telethon disconnected.")


def build_app():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    async def exporttargets_handler(update, context):
        if not is_admin(update.effective_user.id):
            return
        targets = db.get_active_targets()
        usernames = [f"@{t['username']}" for t in targets if t["username"]]
        if not usernames:
            await update.message.reply_text("Tidak ada target dengan username.")
            return
        # Kirim per 100 baris biar tidak kena limit pesan
        chunk = 100
        for i in range(0, len(usernames), chunk):
            await update.message.reply_text("\n".join(usernames[i:i+chunk]))

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("refresh", start_handler))
    app.add_handler(CommandHandler("setqris", setqris_handler))
    app.add_handler(CommandHandler("exporttargets", exporttargets_handler))

    app.add_handler(build_login_conversation())
    app.add_handler(build_settings_conversation())
    app.add_handler(build_leave_conversation())
    app.add_handler(build_addtarget_conversation())
    app.add_handler(build_broadcast_conversation())
    app.add_handler(build_order_conversation())
    app.add_handler(build_user_broadcast_conversation())

    app.add_handler(CallbackQueryHandler(dashboard_callback,      pattern="^cb_dashboard$"))
    app.add_handler(CallbackQueryHandler(account_callback,        pattern="^cb_account$"))
    app.add_handler(CallbackQueryHandler(reconnect_callback,      pattern="^cb_reconnect$"))
    app.add_handler(CallbackQueryHandler(logout_callback,         pattern="^cb_logout$"))
    app.add_handler(CallbackQueryHandler(delacc_callback,         pattern="^cb_delacc_"))
    app.add_handler(CallbackQueryHandler(groups_callback,         pattern="^cb_groups$"))
    app.add_handler(CallbackQueryHandler(removetarget_callback,   pattern="^cb_removetarget$"))
    app.add_handler(CallbackQueryHandler(delete_target_callback,  pattern="^cb_del_\\d+$"))
    app.add_handler(CallbackQueryHandler(importgroups_callback,   pattern="^cb_importgroups$"))
    app.add_handler(CallbackQueryHandler(importconfirm_callback,  pattern="^cb_importconfirm$"))
    app.add_handler(CallbackQueryHandler(activateall_callback,    pattern="^cb_activateall$"))
    app.add_handler(CallbackQueryHandler(exporttargets_callback,  pattern="^cb_exporttargets$"))
    app.add_handler(CallbackQueryHandler(leavegroups_callback,    pattern="^cb_leavegroups$"))
    app.add_handler(CallbackQueryHandler(leaveacc_callback,       pattern="^cb_leaveacc_"))
    app.add_handler(CallbackQueryHandler(leaveconfirm_callback,   pattern="^cb_leaveconfirm$"))
    app.add_handler(CallbackQueryHandler(pause_callback,          pattern="^cb_pause$"))
    app.add_handler(CallbackQueryHandler(resume_callback,         pattern="^bc_resume$"))
    app.add_handler(CallbackQueryHandler(cancel_running_callback, pattern="^bc_cancel$"))
    app.add_handler(CallbackQueryHandler(stats_callback,          pattern="^cb_stats$"))
    app.add_handler(CallbackQueryHandler(logs_callback,           pattern="^cb_logs$"))
    app.add_handler(CallbackQueryHandler(settings_callback,       pattern="^cb_settings$"))
    app.add_handler(CallbackQueryHandler(order_callback,          pattern="^cb_order$"))
    app.add_handler(CallbackQueryHandler(pilih_paket_callback,    pattern="^ord_paket_"))
    app.add_handler(CallbackQueryHandler(lisensi_callback,        pattern="^cb_lisensi$"))
    app.add_handler(CallbackQueryHandler(admin_confirm_callback,  pattern="^adm_confirm_"))
    app.add_handler(CallbackQueryHandler(admin_reject_callback,   pattern="^adm_reject_"))

    return app


def main() -> None:
    init_db()
    logger.info("Database diinisialisasi.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = build_app()
    logger.info("Bot berjalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
