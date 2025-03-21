import asyncio
import logging
import subprocess

from app import config
from app.desktop import DesktopApp


logging_handlers = [
    logging.StreamHandler(),
]

if config.LOG_FILE:
    logging_handlers.append(
        logging.FileHandler(
            config.LOG_FILE,
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
    try:
        app = DesktopApp(
            dev_mode=config.DEV_MODE,
            google_app_id=config.GOOGLE_APP_ID,
        )
        await app.run()
    except Exception as e:
        subprocess.run(
            ['/usr/bin/notify-send', '--icon=error', f'Occurred unexpected error (check logs):\n{e}'],
            check=False,
        )

        raise


if __name__ == '__main__':
    asyncio.run(main())
