import asyncio
import logging

from app import config
from app.desktop import DesktopApp


logging_handlers = (
    logging.StreamHandler(),
    logging.FileHandler(
        'logs.txt',
        mode='w',
    ),
)

logging_formatter = logging.Formatter(
    '%(asctime)s;%(levelname)s;%(message)s',
    '%Y-%m-%d %H:%M:%S',
)

for handler in logging_handlers:
    handler.setFormatter(logging_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=logging_handlers,
)


async def main() -> None:
    app = DesktopApp(
        dev_mode=config.DEV_MODE,
        google_app_id=config.GOOGLE_APP_ID,
    )
    await app.run()


if __name__ == '__main__':
    asyncio.run(main())
