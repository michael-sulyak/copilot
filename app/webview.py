import asyncio
import multiprocessing

import webview


def create_webview(url: str) -> None:
    webview.create_window('Copilot', url)
    webview.start()


async def run_webview(url: str) -> None:
    loop = asyncio.get_running_loop()
    proc = multiprocessing.Process(target=create_webview, args=(url,), daemon=True)
    proc.start()
    await loop.run_in_executor(None, proc.join)
