import asyncio
import logging
from telegram import Bot
from telegram.error import Forbidden, ChatMigrated, RetryAfter, TelegramError

import database as db
from config import BROADCAST_DELAY

logger = logging.getLogger(__name__)

# State broadcast aktif: broadcast_id -> asyncio.Task
_active_tasks: dict[int, asyncio.Task] = {}
_pause_flags: dict[int, bool] = {}


def is_running() -> bool:
    return any(not t.done() for t in _active_tasks.values())


def pause_broadcast() -> bool:
    if not _active_tasks:
        return False
    for bid in list(_active_tasks.keys()):
        _pause_flags[bid] = True
    return True


async def run_broadcast(bot: Bot, message: str, progress_callback) -> None:
    groups = db.get_active_groups()
    if not groups:
        await progress_callback(None, 0, 0, 0, done=True, empty=True)
        return

    broadcast_id = db.create_broadcast(message, len(groups))
    _pause_flags[broadcast_id] = False

    task = asyncio.current_task()
    _active_tasks[broadcast_id] = task

    success = 0
    failed = 0

    try:
        for i, group in enumerate(groups):
            if _pause_flags.get(broadcast_id):
                db.update_broadcast(broadcast_id, success, failed, "paused")
                await progress_callback(broadcast_id, i, success, failed, done=True, paused=True)
                return

            chat_id = group["chat_id"]
            group_name = group["name"]

            try:
                await bot.send_message(chat_id=chat_id, text=message)
                db.add_broadcast_log(broadcast_id, chat_id, group_name, "success")
                success += 1
                logger.info(f"Broadcast ke {group_name} ({chat_id}): berhasil")

            except RetryAfter as e:
                wait = e.retry_after + 1
                logger.warning(f"Flood limit, menunggu {wait}s")
                await asyncio.sleep(wait)
                try:
                    await bot.send_message(chat_id=chat_id, text=message)
                    db.add_broadcast_log(broadcast_id, chat_id, group_name, "success")
                    success += 1
                except TelegramError as retry_err:
                    db.add_broadcast_log(broadcast_id, chat_id, group_name, "failed", str(retry_err))
                    failed += 1

            except (Forbidden, ChatMigrated) as e:
                error_msg = str(e)
                db.add_broadcast_log(broadcast_id, chat_id, group_name, "permission_error", error_msg)
                db.set_group_status(chat_id, 0)
                failed += 1
                logger.warning(f"Permission error di {group_name}: {error_msg}")

            except TelegramError as e:
                db.add_broadcast_log(broadcast_id, chat_id, group_name, "failed", str(e))
                failed += 1
                logger.error(f"Error di {group_name}: {e}")

            await progress_callback(broadcast_id, i + 1, success, failed, done=False)
            await asyncio.sleep(BROADCAST_DELAY)

        db.update_broadcast(broadcast_id, success, failed, "completed")
        await progress_callback(broadcast_id, len(groups), success, failed, done=True)

    finally:
        _active_tasks.pop(broadcast_id, None)
        _pause_flags.pop(broadcast_id, None)
