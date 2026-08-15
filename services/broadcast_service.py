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

# ── State per akun ────────────────────────────────────────────────────────────
# key = phone, value = state dict
_states: dict[str, dict] = {}


def _new_state() -> dict:
    return {
        "running":      False,
        "paused":       False,
        "broadcast_id": None,
        "current":      0,
        "total":        0,
        "success":      0,
        "failed":       0,
        "resume_event": None,
    }


def get_state(phone: str = None) -> dict:
    if phone:
        return dict(_states.get(phone, _new_state()))
    # Fallback: kembalikan state akun pertama yang running
    for s in _states.values():
        if s["running"]:
            return dict(s)
    return _new_state()


def get_all_states() -> dict[str, dict]:
    return {p: dict(s) for p, s in _states.items() if s["running"]}


def is_running(phone: str = None) -> bool:
    if phone:
        return _states.get(phone, {}).get("running", False)
    return any(s["running"] for s in _states.values())


def is_paused(phone: str = None) -> bool:
    if phone:
        return _states.get(phone, {}).get("paused", False)
    return any(s["paused"] for s in _states.values())


def pause(phone: str = None) -> bool:
    targets = [phone] if phone else [p for p, s in _states.items() if s["running"]]
    ok = False
    for p in targets:
        s = _states.get(p)
        if s and s["running"]:
            s["paused"] = True
            ok = True
    return ok


def resume(phone: str = None) -> bool:
    targets = [phone] if phone else [p for p, s in _states.items() if s["paused"]]
    ok = False
    for p in targets:
        s = _states.get(p)
        if s and s["paused"]:
            s["paused"] = False
            if s["resume_event"]:
                s["resume_event"].set()
            ok = True
    return ok


def cancel(phone: str = None) -> bool:
    targets = [phone] if phone else list(_states.keys())
    ok = False
    for p in targets:
        s = _states.get(p)
        if s and s["running"]:
            s["running"] = False
            s["paused"] = False
            if s["resume_event"]:
                s["resume_event"].set()
            ok = True
    return ok


async def run_broadcast(
    message: str,
    target_ids: list[int],
    progress_callback,
    test_mode: bool = False,
    phone: str = None,
) -> None:
    from config import PHONE_NUMBER
    from services.telegram_client import get_all_clients
    # Jika `phone` diberikan, gunakan semua akun yang terkoneksi
    from services.telegram_client import get_all_clients, is_connected

    async def _run_for_phone(active_phone: str) -> None:
        key = active_phone or "default"
        state = _new_state()
        state.update({
            "running":      True,
            "total":        len(target_ids),
            "resume_event": asyncio.Event(),
        })
        _states[key] = state

        broadcast_id = db.create_broadcast(message, test_mode=test_mode or TEST_MODE)
        state["broadcast_id"] = broadcast_id
        db.start_broadcast(broadcast_id)

        for tid in target_ids:
            db.add_broadcast_target(broadcast_id, tid)

        rate = RateLimiter()

        try:
            for i, target_id in enumerate(target_ids):
                if not state["running"]:
                    db.finish_broadcast(broadcast_id, "cancelled")
                    await progress_callback("cancelled", state)
                    return

                while state["paused"]:
                    state["resume_event"].clear()
                    await progress_callback("paused", state)
                    await state["resume_event"].wait()
                    if not state["running"]:
                        db.finish_broadcast(broadcast_id, "cancelled")
                        await progress_callback("cancelled", state)
                        return

                target = db.get_target_by_id(target_id)
                if not target:
                    continue

                state["current"] = i + 1
                chat_id = target["chat_id"]
                title   = target["title"]

                if test_mode or TEST_MODE:
                    db.update_broadcast_target(broadcast_id, target_id, "success")
                    db.add_log("INFO", f"[TEST] {title} → simulasi berhasil")
                    state["success"] += 1
                    await progress_callback("progress", state)
                    await rate.wait()
                    continue

                try:
                    await send_message_to(chat_id, message, active_phone)
                    db.update_broadcast_target(broadcast_id, target_id, "success")
                    db.add_log("INFO", f"{title} → berhasil ({active_phone})")
                    state["success"] += 1

                except FloodWaitError as e:
                    db.add_log("WARNING", f"FloodWait {e.seconds}s — menunggu...")
                    await progress_callback("flood_wait", {**state, "flood_seconds": e.seconds})
                    await rate.handle_flood_wait(e.seconds)
                    try:
                        await send_message_to(chat_id, message, active_phone)
                        db.update_broadcast_target(broadcast_id, target_id, "success")
                        state["success"] += 1
                    except Exception as retry_err:
                        db.update_broadcast_target(broadcast_id, target_id, "failed", str(retry_err))
                        state["failed"] += 1

                except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError) as e:
                    err = type(e).__name__
                    db.update_broadcast_target(broadcast_id, target_id, "failed", err)
                    db.set_target_status(chat_id, 0)
                    state["failed"] += 1

                except (PeerIdInvalidError, RPCError) as e:
                    db.update_broadcast_target(broadcast_id, target_id, "failed", str(e))
                    state["failed"] += 1

                except Exception as e:
                    db.update_broadcast_target(broadcast_id, target_id, "failed", str(e))
                    state["failed"] += 1

                await progress_callback("progress", state)
                await rate.wait()

            db.finish_broadcast(broadcast_id, "completed")
            await progress_callback("completed", state)

        except Exception as e:
            logger.error(f"Broadcast fatal error [{active_phone}]: {e}")
            db.finish_broadcast(broadcast_id, "error")
            await progress_callback("error", state)

        finally:
            state["running"] = False
            state["paused"]  = False

    # Tentukan daftar akun yang akan dipakai
    phones_to_use: list[str] = []
    clients = get_all_clients()
    if phone:
        # Pakai akun yang dipilih saja
        if await is_connected(phone):
            phones_to_use = [phone]
    else:
        # Tidak ada akun dipilih, pakai akun pertama yang terkoneksi
        if PHONE_NUMBER and await is_connected(PHONE_NUMBER):
            phones_to_use = [PHONE_NUMBER]
        else:
            for ph in clients:
                if await is_connected(ph):
                    phones_to_use = [ph]
                    break

    if not phones_to_use:
        # Tidak ada akun terhubung: buat satu run yang akan mencatat kegagalan
        await _run_for_phone(None)
        return

    # Jalankan broadcast untuk tiap akun secara paralel
    tasks = [asyncio.create_task(_run_for_phone(ph)) for ph in phones_to_use]
    await asyncio.gather(*tasks)
