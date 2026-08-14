import os
import asyncio
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE_NUMBER", "")


async def main():
    if not API_ID or not API_HASH:
        print("API_ID and API_HASH must be set in .env")
        return

    print("Starting Telethon client to generate a StringSession.")
    print("If you didn't set PHONE_NUMBER in .env, you'll be prompted.")

    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        await client.start(phone=PHONE or None)
        session_str = client.session.save()
        print("\n--- Save this string to use as your session ---\n")
        print(session_str)
        print("\n----------------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
