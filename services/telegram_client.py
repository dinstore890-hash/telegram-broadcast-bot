import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel, Chat, User

from config import API_ID, API_HASH, PHONE_NUMBER, SESSION_DIR

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        os.makedirs(SESSION_DIR, exist_ok=True)
        # Pakai string session jika tersedia, fallback ke file session
        string_session = os.getenv("STRING_SESSION", "").strip()
        if string_session:
            _client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
        else:
            session_path = os.path.join(SESSION_DIR, "account")
            _client = TelegramClient(session_path, API_ID, API_HASH)
    return _client


async def is_connected() -> bool:
    client = get_client()
    if not client.is_connected():
        return False
    return await client.is_user_authorized()


async def get_me() -> dict | None:
    try:
        client = get_client()
        if not await is_connected():
            return None
        me = await client.get_me()
        return {
            "id":       me.id,
            "username": me.username or "",
            "phone":    me.phone or "",
            "name":     f"{me.first_name or ''} {me.last_name or ''}".strip(),
        }
    except Exception as e:
        logger.error(f"get_me error: {e}")
        return None


async def connect() -> bool:
    try:
        client = get_client()
        if not client.is_connected():
            await client.connect()
        return await client.is_user_authorized()
    except Exception as e:
        logger.error(f"connect error: {e}")
        return False


async def send_code(phone: str) -> str | None:
    """Kirim OTP ke nomor HP. Return phone_code_hash."""
    try:
        client = get_client()
        if not client.is_connected():
            await client.connect()
        result = await client.send_code_request(phone)
        return result.phone_code_hash
    except Exception as e:
        logger.error(f"send_code error: {e}")
        return None


async def sign_in(phone: str, code: str, phone_code_hash: str) -> tuple[bool, bool, str]:
    """
    Login dengan OTP.
    Return (success, needs_2fa, error_message).
    """
    try:
        client = get_client()
        if not client.is_connected():
            await client.connect()
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return True, False, ""
    except SessionPasswordNeededError:
        return False, True, ""
    except Exception as e:
        logger.error(f"sign_in error: {type(e).__name__}: {e}")
        return False, False, f"{type(e).__name__}: {e}"


async def sign_in_2fa(password: str) -> bool:
    try:
        client = get_client()
        await client.sign_in(password=password)
        return True
    except Exception as e:
        logger.error(f"sign_in_2fa error: {e}")
        return False


async def logout() -> bool:
    try:
        client = get_client()
        await client.log_out()
        return True
    except Exception as e:
        logger.error(f"logout error: {e}")
        return False


async def resolve_target(identifier: str) -> dict | None:
    try:
        client = get_client()
        if not await is_connected():
            logger.error("resolve_target: client tidak connected")
            return None

        identifier = identifier.strip()
        if identifier.startswith("https://t.me/"):
            identifier = identifier.replace("https://t.me/", "")
        if "/" in identifier:
            identifier = identifier.split("/")[0]
        if identifier.startswith("@"):
            identifier = identifier[1:]

        # Simpan username asli persis seperti input user (dengan underscore)
        display_username = identifier

        logger.info(f"resolve_target: mencoba akses '{identifier}'")

        # Coba username dulu, kalau gagal coba pakai InputPeerUsername
        entity = None
        try:
            entity = await client.get_entity(identifier)
        except Exception:
            from telethon.tl.functions.contacts import ResolveUsernameRequest
            try:
                result = await client(ResolveUsernameRequest(identifier))
                entity = result.chats[0] if result.chats else (result.users[0] if result.users else None)
            except Exception as e2:
                logger.error(f"resolve_target fallback error: {type(e2).__name__}: {e2}")
                return None

        if entity is None:
            return None

        logger.info(f"resolve_target: entity type = {type(entity).__name__}, id = {entity.id}")

        if isinstance(entity, Channel):
            chat_type = "channel" if entity.broadcast else "supergroup"
            return {
                "chat_id":   int(f"-100{entity.id}"),
                "title":     entity.title,
                "username":  display_username,
                "chat_type": chat_type,
            }
        elif isinstance(entity, Chat):
            return {
                "chat_id":   -entity.id,
                "title":     entity.title,
                "username":  "",
                "chat_type": "group",
            }
        elif isinstance(entity, User):
            return {
                "chat_id":   entity.id,
                "title":     f"{entity.first_name or ''} {entity.last_name or ''}".strip(),
                "username":  display_username,
                "chat_type": "user",
            }
        logger.warning(f"resolve_target: tipe entity tidak dikenal: {type(entity)}")
        return None
    except Exception as e:
        logger.error(f"resolve_target '{identifier}' error: {type(e).__name__}: {e}")
        return None


async def send_message_to(chat_id: int, message: str) -> None:
    """Kirim pesan via akun Telethon. Raise exception jika gagal."""
    client = get_client()
    # Supergroup/channel perlu prefix -100
    if chat_id > 0:
        full_id = int(f"-100{chat_id}")
    else:
        full_id = chat_id
    await client.send_message(full_id, message)


async def join_and_resolve(identifier: str) -> dict:
    """
    Resolve target. Jika belum join, auto-join dulu.
    Return dict dengan key: chat_id, title, username, chat_type, joined (bool), error (str)
    """
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.functions.messages import ImportChatInviteRequest
    from telethon.errors import UserAlreadyParticipantError

    client = get_client()
    raw = identifier.strip()

    # Ekstrak username/invite hash
    invite_hash = None
    if "t.me/+" in raw or "t.me/joinchat/" in raw:
        invite_hash = raw.split("/+")[-1] if "/+" in raw else raw.split("/joinchat/")[-1]
    
    username = raw
    if username.startswith("https://t.me/"):
        username = username.replace("https://t.me/", "").split("/")[0]
    username = username.lstrip("@")

    try:
        # Coba resolve dulu
        entity = None
        try:
            entity = await client.get_entity(username if not invite_hash else raw)
        except Exception:
            pass

        # Kalau gagal resolve → coba join dulu
        if entity is None:
            try:
                if invite_hash:
                    await client(ImportChatInviteRequest(invite_hash))
                else:
                    from telethon.tl.functions.contacts import ResolveUsernameRequest
                    result = await client(ResolveUsernameRequest(username))
                    entity = result.chats[0] if result.chats else (result.users[0] if result.users else None)
                    if entity:
                        await client(JoinChannelRequest(entity))
            except UserAlreadyParticipantError:
                pass
            except Exception as e:
                return {"error": str(e), "username": username}
            # Re-resolve setelah join
            try:
                entity = await client.get_entity(username if not invite_hash else raw)
            except Exception as e:
                return {"error": str(e), "username": username}
        else:
            # Sudah bisa resolve, coba join kalau belum
            try:
                if invite_hash:
                    await client(ImportChatInviteRequest(invite_hash))
                elif isinstance(entity, Channel):
                    await client(JoinChannelRequest(entity))
            except UserAlreadyParticipantError:
                pass
            except Exception:
                pass  # Sudah join, lanjut saja

        if entity is None:
            return {"error": "Tidak dapat resolve", "username": username}

        if isinstance(entity, Channel):
            chat_type = "channel" if entity.broadcast else "supergroup"
            return {
                "chat_id":   int(f"-100{entity.id}"),
                "title":     entity.title,
                "username":  username,
                "chat_type": chat_type,
                "error":     None,
            }
        elif isinstance(entity, Chat):
            return {
                "chat_id":   -entity.id,
                "title":     entity.title,
                "username":  "",
                "chat_type": "group",
                "error":     None,
            }
        return {"error": "Tipe tidak didukung", "username": username}

    except Exception as e:
        logger.error(f"join_and_resolve '{identifier}' error: {type(e).__name__}: {e}")
        return {"error": f"{type(e).__name__}: {e}", "username": username}


async def get_joined_groups() -> list[dict]:
    """Fetch semua grup/channel yang sudah di-join akun Telethon."""
    client = get_client()
    if not await is_connected():
        return []
    results = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            chat_type = "channel" if entity.broadcast else "supergroup"
            results.append({
                "chat_id":   int(f"-100{entity.id}"),
                "title":     entity.title,
                "username":  entity.username or "",
                "chat_type": chat_type,
            })
        elif isinstance(entity, Chat):
            results.append({
                "chat_id":   -entity.id,
                "title":     entity.title,
                "username":  "",
                "chat_type": "group",
            })
    return results


async def disconnect() -> None:
    global _client
    if _client and _client.is_connected():
        await _client.disconnect()
    _client = None
