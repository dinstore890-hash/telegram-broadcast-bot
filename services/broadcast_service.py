import asyncio
import logging
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    PeerIdInvalidError,
    RPCError,
)

import database as db
from services.telegram_client import send_message_to, is_connected
from services.rate_limiter import RateLimiter
from config import TEST_MODE

logger = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────────────────────────
_state = {
    "running":      False,
    "paused":       False,
    "broadcast_id": None,
    "current":      0,
    "total":        0,
    "success":      0,
    "failed":       0,
    "resume_event": None,   # asyncio.Event
}


def get_state() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["running"]


def is_paused() -> bool:
    return _state["paused"]


def pause() -> bool:
    if not _state["running"]:
        return False
    _state["paused"] = True
    return True


def resume() -> bool:
    if not _state["paused"]:
        return False
    _state["paused"] = False
    event: asyncio.Event = _state["resume_event"]
    if event:
        event.set()
    return True


def cancel() -> bool:
    if not _state["running"]:
        return False
    _state["running"] = False
    _state["paused"] = False
    event: asyncio.Event = _state["resume_event"]
    if event:
        event.set()
    return True


async def run_broadcast(
    message: str,
    target_ids: list[int],
    progress_callback,
    test_mode: bool = False,
) -> None:
    _state.update({
        "running":      True,
        "paused":       False,
        "current":      0,
        "total":        len(target_ids),
        "success":      0,
        "failed":       0,
        "resume_event": asyncio.Event(),
    })

    broadcast_id = db.create_broadcast(message, test_mode=test_mode or TEST_MODE)
    _state["broadcast_id"] = broadcast_id
    db.start_broadcast(broadcast_id)

    for tid in target_ids:
        db.add_broadcast_target(broadcast_id, tid)

    rate = RateLimiter()

    try:
        for i, target_id in enumerate(target_ids):
            if not _state["running"]:
                db.finish_broadcast(broadcast_id, "cancelled")
                await progress_callback("cancelled", _state)
                return

            # Pause: tunggu resume atau cancel
            while _state["paused"]:
                _state["resume_event"].clear()
                await progress_callback("paused", _state)
                await _state["resume_event"].wait()
                if not _state["running"]:
                    db.finish_broadcast(broadcast_id, "cancelled")
                    await progress_callback("cancelled", _state)
                    return

            target = db.get_target_by_id(target_id)
            if not target:
                continue

            _state["current"] = i + 1
            chat_id   = target["chat_id"]
            title     = target["title"]

            if test_mode or TEST_MODE:
                db.update_broadcast_target(broadcast_id, target_id, "success")
                db.add_log("INFO", f"[TEST] {title} → simulasi berhasil")
                _state["success"] += 1
                await progress_callback("progress", _state)
                await rate.wait()
                continue

            if not await is_connected():
                db.update_broadcast_target(broadcast_id, target_id, "failed", "Akun tidak terkoneksi")
                _state["failed"] += 1
                await progress_callback("progress", _state)
                continue

            try:
                await send_message_to(chat_id, message)
                db.update_broadcast_target(broadcast_id, target_id, "success")
                db.add_log("INFO", f"{title} → berhasil")
                _state["success"] += 1
                logger.info(f"Broadcast ke {title} ({chat_id}): berhasil")

            except FloodWaitError as e:
                db.add_log("WARNING", f"FloodWait {e.seconds}s — menunggu...")
                await progress_callback("flood_wait", {**_state, "flood_seconds": e.seconds})
                await rate.handle_flood_wait(e.seconds)
                # Coba sekali lagi setelah flood wait
                try:
                    await send_message_to(chat_id, message)
                    db.update_broadcast_target(broadcast_id, target_id, "success")
                    db.add_log("INFO", f"{title} → berhasil (setelah FloodWait)")
                    _state["success"] += 1
                except Exception as retry_err:
                    db.update_broadcast_target(broadcast_id, target_id, "failed", str(retry_err))
                    db.add_log("ERROR", f"{title} → gagal: {retry_err}")
                    _state["failed"] += 1

            except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError) as e:
                err = type(e).__name__
                db.update_broadcast_target(broadcast_id, target_id, "failed", err)
                db.set_target_status(chat_id, 0)
                db.add_log("WARNING", f"{title} → {err} — ditandai nonaktif")
                _state["failed"] += 1
                logger.warning(f"Permission error di {title}: {err}")

            except (PeerIdInvalidError, RPCError) as e:
                err = str(e)
                db.update_broadcast_target(broadcast_id, target_id, "failed", err)
                db.add_log("ERROR", f"{title} → {err}")
                _state["failed"] += 1
                logger.error(f"RPC error di {title}: {err}")

            except Exception as e:
                err = str(e)
                db.update_broadcast_target(broadcast_id, target_id, "failed", err)
                db.add_log("ERROR", f"{title} → {err}")
                _state["failed"] += 1
                logger.error(f"Error di {title}: {err}")

            await progress_callback("progress", _state)
            await rate.wait()

        db.finish_broadcast(broadcast_id, "completed")
        await progress_callback("completed", _state)

    except Exception as e:
        logger.error(f"Broadcast fatal error: {e}")
        db.finish_broadcast(broadcast_id, "error")
        await progress_callback("error", _state)

    finally:
        _state["running"] = False
        _state["paused"]  = False
