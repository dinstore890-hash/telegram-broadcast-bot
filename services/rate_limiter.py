import asyncio
import logging
from config import BROADCAST_DELAY

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, delay: float = BROADCAST_DELAY):
        self.delay = delay

    async def wait(self) -> None:
        await asyncio.sleep(self.delay)

    async def handle_flood_wait(self, seconds: int) -> None:
        wait = seconds + 2
        logger.warning(f"FloodWait: menunggu {wait} detik sesuai permintaan Telegram...")
        await asyncio.sleep(wait)
