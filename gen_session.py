from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = 32708612
API_HASH = "cc2cda832e40d995a824e135c9ec12b6"

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n✅ String Session kamu:\n")
    print(client.session.save())
    print("\nCopy string di atas dan paste ke bot.")
