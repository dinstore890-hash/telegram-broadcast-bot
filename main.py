import asyncio
import logging
import os
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

from config import BOT_TOKEN, LOG_DIR
from database import init_db
from services import telegram_client

from handlers.start import (
    start_handler, dashboard_callback, settings_callback,
    lisensi_callback, set_broadcast_delay_callback,
    build_settings_conversation,
    set_botinfo_menu, edit_botinfo_field_callback,
    reset_botinfo_callback, build_botinfo_conversation,
    coba_lagi_callback, set_channel_callback, build_channel_conversation,
)
from handlers.user_broadcast import build_user_broadcast_conversation
from handlers.userbot import (
    ub_home, ub_account, ub_login_start, ub_logout,
    ub_groups, ub_list_groups, ub_activate_all,
    ub_import_groups, ub_reset_groups,
    ub_list_messages, ub_del_message, ub_reset_messages,
    ub_broadcast_menu, ub_start_broadcast, ub_stop_broadcast,
    ub_settings, ub_setdelay_preset, ub_bantuan,
    ub_cara_pasang, ub_fitur_unggulan,
    ub_trial, ub_setuju_trial, ub_delete_group,
    ub_pause_broadcast, ub_resume_broadcast,
    ub_loop_broadcast, ub_history,
    build_userbot_conversation,
)
from handlers.account import (
    account_callback, reconnect_callback, logout_callback,
    build_login_conversation, delacc_callback,
)
from handlers.groups import (
    groups_callback, removetarget_callback, delete_target_callback,
    importgroups_callback, importconfirm_callback,
    bulkjoin_callback, exporttargets_callback, activateall_callback,
    leavegroups_callback, leavedelay_callback, leaveacc_callback, leaveconfirm_callback,
    cancelprocess_callback, retryjoin_callback,
    build_addtarget_conversation, build_leave_conversation,
)
from handlers.broadcast import (
    pause_callback, resume_callback, cancel_running_callback,
    build_broadcast_conversation,
)
from handlers.stats import stats_callback, manage_licenses_callback, delete_license_callback, \
    manage_users_callback, unban_callback, announce_callback, \
    show_userlist_ban_callback, show_userlist_unban_callback, ban_direct_callback, \
    show_userlist_reset_callback, reset_user_menu_callback, reset_user_data_callback, \
    lihat_broadcast_user_callback, \
    build_ban_conversation, build_announce_conversation
from config import is_admin
import database as db
from handlers.logs import logs_callback
from handlers.order import (
    order_callback, pilih_paket_callback,
    admin_confirm_callback, admin_reject_callback,
    build_order_conversation, setqris_handler,
    manage_harga_callback, build_harga_conversation,
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

    # Start background task notifikasi expired
    asyncio.create_task(_expired_notif_loop(app.bot))


async def _expired_notif_loop(bot) -> None:
    """Cek setiap hari jam 09.00 WIB — kirim notifikasi H-3 dan H-1 expired."""
    from datetime import datetime, timezone, timedelta
    WIB = timezone(timedelta(hours=7))
    while True:
        try:
            now = datetime.now(WIB)
            # Hitung detik sampai jam 09.00 WIB berikutnya
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"Notifikasi expired: menunggu {int(wait_seconds//3600)} jam {int((wait_seconds%3600)//60)} menit")
            await asyncio.sleep(wait_seconds)

            # Kirim notifikasi H-3
            for lic in db.get_expiring_licenses(3):
                try:
                    await bot.send_message(
                        chat_id=lic["user_id"],
                        text=(
                            "⚠️ *LISENSI HAMPIR HABIS*\n\n"
                            f"Lisensi kamu tinggal *3 hari lagi*!\n"
                            f"Paket: {lic['paket']}\n"
                            f"Expired: {lic['expired_at'][:10]}\n\n"
                            "Perpanjang sekarang biar tidak terputus 👇"
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🛒 Perpanjang Sekarang", callback_data="cb_order")
                        ]])
                    )
                    logger.info(f"Notif H-3 terkirim ke user {lic['user_id']}")
                except Exception as e:
                    logger.warning(f"Notif H-3 gagal user {lic['user_id']}: {e}")

            # Kirim notifikasi H-1
            for lic in db.get_expiring_licenses(1):
                try:
                    await bot.send_message(
                        chat_id=lic["user_id"],
                        text=(
                            "🚨 *LISENSI HABIS BESOK!*\n\n"
                            f"Lisensi kamu habis *besok*!\n"
                            f"Paket: {lic['paket']}\n"
                            f"Expired: {lic['expired_at'][:10]}\n\n"
                            "Segera perpanjang sebelum akses terputus! 👇"
                        ),
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🛒 Perpanjang Sekarang", callback_data="cb_order")
                        ]])
                    )
                    logger.info(f"Notif H-1 terkirim ke user {lic['user_id']}")
                except Exception as e:
                    logger.warning(f"Notif H-1 gagal user {lic['user_id']}: {e}")

        except Exception as e:
            logger.error(f"_expired_notif_loop error: {e}")
            await asyncio.sleep(3600)  # retry 1 jam kemudian


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
    app.add_handler(build_botinfo_conversation())
    app.add_handler(build_channel_conversation())
    app.add_handler(build_leave_conversation())
    app.add_handler(build_addtarget_conversation())
    app.add_handler(build_broadcast_conversation())
    app.add_handler(build_order_conversation())
    app.add_handler(build_harga_conversation())
    app.add_handler(build_user_broadcast_conversation())
    app.add_handler(build_userbot_conversation())
    app.add_handler(build_ban_conversation())
    app.add_handler(build_announce_conversation())

    app.add_handler(CallbackQueryHandler(dashboard_callback,      pattern="^cb_dashboard$"))
    app.add_handler(CallbackQueryHandler(coba_lagi_callback,      pattern="^cb_coba_lagi$"))
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
    app.add_handler(CallbackQueryHandler(cancelprocess_callback,  pattern="^cb_cancelprocess$"))
    app.add_handler(CallbackQueryHandler(retryjoin_callback,      pattern="^cb_retryjoin_"))
    app.add_handler(CallbackQueryHandler(pause_callback,          pattern="^cb_pause$"))
    app.add_handler(CallbackQueryHandler(resume_callback,         pattern="^bc_resume$"))
    app.add_handler(CallbackQueryHandler(cancel_running_callback, pattern="^bc_cancel$"))
    app.add_handler(CallbackQueryHandler(stats_callback,          pattern="^cb_stats$"))
    app.add_handler(CallbackQueryHandler(manage_licenses_callback, pattern="^cb_manage_licenses$"))
    app.add_handler(CallbackQueryHandler(delete_license_callback,  pattern="^adm_del_lic_"))
    app.add_handler(CallbackQueryHandler(manage_users_callback,       pattern="^cb_manage_users$"))
    app.add_handler(CallbackQueryHandler(show_userlist_ban_callback,  pattern="^adm_show_userlist_ban$"))
    app.add_handler(CallbackQueryHandler(show_userlist_unban_callback,pattern="^adm_show_userlist_unban$"))
    app.add_handler(CallbackQueryHandler(ban_direct_callback,         pattern="^adm_ban_\\d+$"))
    app.add_handler(CallbackQueryHandler(unban_callback,              pattern="^adm_unban_"))
    app.add_handler(CallbackQueryHandler(show_userlist_reset_callback, pattern="^adm_show_userlist_reset$"))
    app.add_handler(CallbackQueryHandler(reset_user_menu_callback,    pattern="^adm_reset_menu_\\d+$"))
    app.add_handler(CallbackQueryHandler(reset_user_data_callback,    pattern="^adm_reset_(grup|pesan|akun|all)_\\d+$"))
    app.add_handler(CallbackQueryHandler(lihat_broadcast_user_callback, pattern="^adm_lihat_bc_\\d+$"))
    app.add_handler(CallbackQueryHandler(announce_callback,           pattern="^cb_announce$"))
    app.add_handler(CallbackQueryHandler(manage_harga_callback,       pattern="^cb_manage_harga$"))
    app.add_handler(CallbackQueryHandler(logs_callback,           pattern="^cb_logs$"))
    app.add_handler(CallbackQueryHandler(settings_callback,       pattern="^cb_settings$"))
    app.add_handler(CallbackQueryHandler(set_botinfo_menu,        pattern="^cb_set_botinfo$"))
    app.add_handler(CallbackQueryHandler(reset_botinfo_callback,  pattern="^cb_resetbotinfo$"))
    app.add_handler(CallbackQueryHandler(order_callback,          pattern="^cb_order$"))
    app.add_handler(CallbackQueryHandler(pilih_paket_callback,    pattern="^ord_paket_"))
    app.add_handler(CallbackQueryHandler(lisensi_callback,        pattern="^cb_lisensi$"))
    app.add_handler(CallbackQueryHandler(admin_confirm_callback,  pattern="^adm_confirm_"))
    app.add_handler(CallbackQueryHandler(admin_reject_callback,   pattern="^adm_reject_"))

    # ── Userbot handlers ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(ub_home,             pattern="^ub_home$"))
    app.add_handler(CallbackQueryHandler(ub_account,          pattern="^ub_account$"))
    app.add_handler(CallbackQueryHandler(ub_logout,           pattern="^ub_logout$"))
    app.add_handler(CallbackQueryHandler(ub_groups,           pattern="^ub_groups$"))
    app.add_handler(CallbackQueryHandler(ub_list_groups,      pattern="^ub_list_groups$"))
    app.add_handler(CallbackQueryHandler(ub_activate_all,     pattern="^ub_activate_all$"))
    app.add_handler(CallbackQueryHandler(ub_import_groups,    pattern="^ub_import_groups$"))
    app.add_handler(CallbackQueryHandler(ub_reset_groups,     pattern="^ub_reset_groups$"))
    app.add_handler(CallbackQueryHandler(ub_list_messages,    pattern="^ub_list_messages$"))
    app.add_handler(CallbackQueryHandler(ub_del_message,      pattern="^ub_del_msg_"))
    app.add_handler(CallbackQueryHandler(ub_reset_messages,   pattern="^ub_reset_messages$"))
    app.add_handler(CallbackQueryHandler(ub_broadcast_menu,   pattern="^ub_broadcast_menu$"))
    app.add_handler(CallbackQueryHandler(ub_start_broadcast,  pattern="^ub_start_bc_"))
    app.add_handler(CallbackQueryHandler(ub_stop_broadcast,   pattern="^ub_stop_broadcast$"))
    app.add_handler(CallbackQueryHandler(ub_settings,         pattern="^ub_settings$"))
    app.add_handler(CallbackQueryHandler(ub_setdelay_preset,  pattern="^ub_setdelay_"))
    app.add_handler(CallbackQueryHandler(ub_bantuan,          pattern="^ub_bantuan$"))
    app.add_handler(CallbackQueryHandler(ub_cara_pasang,      pattern="^ub_cara_pasang$"))
    app.add_handler(CallbackQueryHandler(ub_fitur_unggulan,   pattern="^ub_fitur_unggulan$"))
    app.add_handler(CallbackQueryHandler(ub_trial,            pattern="^ub_trial$"))
    app.add_handler(CallbackQueryHandler(ub_setuju_trial,     pattern="^ub_setuju_trial$"))
    app.add_handler(CallbackQueryHandler(ub_delete_group,     pattern="^ub_delgrp_\\d+$"))
    app.add_handler(CallbackQueryHandler(ub_pause_broadcast,  pattern="^ub_pause_broadcast$"))
    app.add_handler(CallbackQueryHandler(ub_resume_broadcast, pattern="^ub_resume_broadcast$"))
    app.add_handler(CallbackQueryHandler(ub_loop_broadcast,   pattern="^ub_loop_bc_\\d+$"))
    app.add_handler(CallbackQueryHandler(ub_history,          pattern="^ub_history$"))

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
