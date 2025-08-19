from functools import lru_cache

from telethon import TelegramClient

from ... import config


@lru_cache
def get_telegram_client() -> TelegramClient:
    return TelegramClient(
        session='bot',
        api_id=config.TELEGRAM_API_ID,
        api_hash=config.TELEGRAM_API_HASH,
        system_version='4.16.30-vxCUSTOM',  # See https://github.com/LonamiWebs/Telethon/issues/4051
    )


async def init_telegram_client(client: TelegramClient) -> None:
    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        await client.start()
