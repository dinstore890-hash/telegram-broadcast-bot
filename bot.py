import asyncio
import logging

from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

from config import BOT_TOKEN
from database import init_db
from handlers.start import start_handler, menu_callback, menu_back_callback
from handlers.groups import addgroup_handler, groups_handler, removegroup_handler
from handlers.broadcast import broadcast_handler, pause_handler
from handlers.stats import stats_handler, logs_handler


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def main() -> None:
    init_db()
    logger.info("Database diinisialisasi.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("addgroup", addgroup_handler))
    app.add_handler(CommandHandler("groups", groups_handler))
    app.add_handler(CommandHandler("removegroup", removegroup_handler))
    app.add_handler(CommandHandler("broadcast", broadcast_handler))
    app.add_handler(CommandHandler("pause", pause_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CommandHandler("logs", logs_handler))

    app.add_handler(
        CallbackQueryHandler(menu_back_callback, pattern="^menu_back$")
    )
    app.add_handler(
        CallbackQueryHandler(menu_callback, pattern="^menu_")
    )

    logger.info("Bot berjalan...")

    # Python 3.14 compatibility
    asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()