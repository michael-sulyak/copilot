import asyncio
import multiprocessing

import webview

from . import config


def create_webview(url: str) -> None:
    webview.create_window(
        title='Copilot',
        url=url,
        text_select=True,
        draggable=True,
        zoomable=True,
        maximized=True,
        on_top=True,
    )
    webview.start(icon=config.ICON_PATH, gui='gtk')


async def run_webview(url: str) -> None:
    loop = asyncio.get_running_loop()
    proc = multiprocessing.Process(target=create_webview, args=(url,), daemon=True)
    proc.start()
    await loop.run_in_executor(None, proc.join)
