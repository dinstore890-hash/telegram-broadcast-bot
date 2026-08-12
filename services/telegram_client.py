import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel, Chat, User

from config import API_ID, API_HASH, PHONE_NUMBER, SESSION_DIR

logger = logging.getLogger(__name__)

# Multi-client: phone -> TelegramClient
_clients: dict[str, TelegramClient] = {}

# Untuk backward-compat: akun utama dari .env
_PRIMARY_PHONE = PHONE_NUMBER


def _make_client(session_name: str) -> TelegramClient:
    os.makedirs(SESSION_DIR, exist_ok=True)
    session_path = os.path.join(SESSION_DIR, session_name)
    return TelegramClient(session_path, API_ID, API_HASH)


def get_client(phone: str | None = None) -> TelegramClient:
    """Ambil client berdasarkan nomor HP. Jika None, ambil client pertama yang aktif."""
    if phone:
        if phone not in _clients:
            import database as db
            acc = db.get_account_by_phone(phone)
            session_name = acc["session_name"] if acc else phone.replace("+", "")
            _clients[phone] = _make_client(session_name)
        return _clients[phone]

    # Ambil client pertama yang tersedia
    if _clients:
        return next(iter(_clients.values()))

    # Fallback: akun utama dari .env
    if _PRIMARY_PHONE not in _clients:
        string_session = os.getenv("STRING_SESSION", "").strip()
        if string_session:
            _clients[_PRIMARY_PHONE] = TelegramClient(StringSession(string_session), API_ID, API_HASH)
        else:
            _clients[_PRIMARY_PHONE] = _make_client("account")
    return _clients[_PRIMARY_PHONE]


def get_all_clients() -> dict[str, TelegramClient]:
    return _clients


async def load_accounts_from_db() -> None:
    """Load semua akun dari DB ke _clients saat startup."""
    import database as db

    # Load akun utama dari .env ke DB kalau belum ada
    if _PRIMARY_PHONE:
        if not db.get_account_by_phone(_PRIMARY_PHONE):
            string_session = os.getenv("STRING_SESSION", "").strip()
            if string_session:
                from telethon.sessions import StringSession
                client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    name = f"{me.first_name or ''} {me.last_name or ''}".strip()
                    username = me.username or ""
                    session_name = _PRIMARY_PHONE.replace("+", "")
                    db.add_account(_PRIMARY_PHONE, session_name, name, username)
                    _clients[_PRIMARY_PHONE] = client
                    logger.info(f"Akun utama .env dimuat: {_PRIMARY_PHONE}")
            else:
                session_name = _PRIMARY_PHONE.replace("+", "")
                db.add_account(_PRIMARY_PHONE, session_name)

    accounts = db.get_active_accounts()
    for acc in accounts:
        phone = acc["phone"]
        if phone not in _clients:
            if acc["string_session"]:
                from telethon.sessions import StringSession
                _clients[phone] = TelegramClient(StringSession(acc["string_session"]), API_ID, API_HASH)
            else:
                _clients[phone] = _make_client(acc["session_name"])
    logger.info(f"Loaded {len(accounts)} akun dari DB")


async def connect_all() -> list[str]:
    """Connect semua client. Return list phone yang berhasil connect."""
    connected = []
    for phone, client in list(_clients.items()):
        try:
            if not client.is_connected():
                await client.connect()
            if await client.is_user_authorized():
                connected.append(phone)
                logger.info(f"Connected: {phone}")
            else:
                logger.warning(f"Not authorized: {phone}")
        except Exception as e:
            logger.error(f"connect_all error [{phone}]: {e}")
    return connected


async def is_connected(phone: str | None = None) -> bool:
    client = get_client(phone)
    if not client.is_connected():
        return False
    return await client.is_user_authorized()


async def get_me(phone: str | None = None) -> dict | None:
    try:
        client = get_client(phone)
        if not await is_connected(phone):
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


async def get_all_me() -> list[dict]:
    """Ambil info semua akun yang terkoneksi."""
    result = []
    for phone, client in list(_clients.items()):
        try:
            if not client.is_connected():
                await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                result.append({
                    "phone":    phone,
                    "id":       me.id,
                    "username": me.username or "",
                    "name":     f"{me.first_name or ''} {me.last_name or ''}".strip(),
                    "connected": True,
                })
            else:
                result.append({"phone": phone, "connected": False})
        except Exception as e:
            result.append({"phone": phone, "connected": False, "error": str(e)})
    return result


async def connect(phone: str | None = None) -> bool:
    try:
        client = get_client(phone)
        if not client.is_connected():
            await client.connect()
        return await client.is_user_authorized()
    except Exception as e:
        logger.error(f"connect error: {e}")
        return False


async def send_code(phone: str) -> str | None:
    """Kirim OTP ke nomor HP. Return phone_code_hash."""
    try:
        # Buat client baru untuk akun baru
        if phone not in _clients:
            _clients[phone] = _make_client(phone.replace("+", ""))
        client = _clients[phone]
        if not client.is_connected():
            await client.connect()
        result = await client.send_code_request(phone)
        return result.phone_code_hash
    except Exception as e:
        logger.error(f"send_code error: {e}")
        return None


async def sign_in(phone: str, code: str, phone_code_hash: str) -> tuple[bool, bool, str]:
    try:
        client = get_client(phone)
        if not client.is_connected():
            await client.connect()
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        return True, False, ""
    except SessionPasswordNeededError:
        return False, True, ""
    except Exception as e:
        logger.error(f"sign_in error: {type(e).__name__}: {e}")
        return False, False, f"{type(e).__name__}: {e}"


async def sign_in_2fa(phone: str, password: str) -> bool:
    try:
        client = get_client(phone)
        await client.sign_in(password=password)
        return True
    except Exception as e:
        logger.error(f"sign_in_2fa error: {e}")
        return False


async def logout(phone: str | None = None) -> bool:
    try:
        client = get_client(phone)
        await client.log_out()
        target_phone = phone or _PRIMARY_PHONE
        _clients.pop(target_phone, None)
        return True
    except Exception as e:
        logger.error(f"logout error: {e}")
        return False


async def remove_client(phone: str) -> None:
    """Disconnect dan hapus client dari memory."""
    client = _clients.pop(phone, None)
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception:
            pass


async def resolve_target(identifier: str, phone: str | None = None) -> dict | None:
    try:
        client = get_client(phone)
        if not await is_connected(phone):
            logger.error("resolve_target: client tidak connected")
            return None

        identifier = identifier.strip()
        if identifier.startswith("https://t.me/"):
            identifier = identifier.replace("https://t.me/", "")
        if "/" in identifier:
            identifier = identifier.split("/")[0]
        if identifier.startswith("@"):
            identifier = identifier[1:]

        display_username = identifier
        logger.info(f"resolve_target: mencoba akses '{identifier}'")

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
        return None
    except Exception as e:
        logger.error(f"resolve_target '{identifier}' error: {type(e).__name__}: {e}")
        return None


async def send_message_to(chat_id: int, message: str, phone: str | None = None) -> None:
    """Kirim pesan via akun Telethon."""
    client = get_client(phone)
    if chat_id > 0:
        full_id = int(f"-100{chat_id}")
    else:
        full_id = chat_id
    await client.send_message(full_id, message)


async def join_and_resolve(identifier: str, phone: str | None = None) -> dict:
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.functions.messages import ImportChatInviteRequest
    from telethon.errors import UserAlreadyParticipantError

    client = get_client(phone)
    raw = identifier.strip()

    invite_hash = None
    if "t.me/+" in raw or "t.me/joinchat/" in raw:
        invite_hash = raw.split("/+")[-1] if "/+" in raw else raw.split("/joinchat/")[-1]

    username = raw
    if username.startswith("https://t.me/"):
        username = username.replace("https://t.me/", "").split("/")[0]
    username = username.lstrip("@")

    try:
        entity = None
        try:
            entity = await client.get_entity(username if not invite_hash else raw)
        except Exception:
            pass

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
            try:
                entity = await client.get_entity(username if not invite_hash else raw)
            except Exception as e:
                return {"error": str(e), "username": username}
        else:
            try:
                if invite_hash:
                    await client(ImportChatInviteRequest(invite_hash))
                elif isinstance(entity, Channel):
                    await client(JoinChannelRequest(entity))
            except UserAlreadyParticipantError:
                pass
            except Exception:
                pass

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


async def get_joined_groups(phone: str | None = None) -> list[dict]:
    client = get_client(phone)
    if not await is_connected(phone):
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


async def disconnect(phone: str | None = None) -> None:
    global _clients
    if phone:
        client = _clients.pop(phone, None)
        if client and client.is_connected():
            await client.disconnect()
    else:
        for client in list(_clients.values()):
            if client.is_connected():
                await client.disconnect()
        _clients.clear()
