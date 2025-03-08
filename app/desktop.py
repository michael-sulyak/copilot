import asyncio
import datetime
import logging
import os
import uuid
import weakref
from typing import NoReturn

import aiohttp_cors
import aiohttp_rpc
from aiohttp import web, web_ws

from . import config
from .dialogs.base import BaseAnswer, BaseDialog, DialogError, Discussion, Message, Request
from .dialogs.dialog_loader import LazyDialog, load_dialogs
from .dialogs.prompts import PROMPTS
from .models.openai.base import Whisper
from .utils.local_file_storage import LocalFileStorage
from .web.middlewares import index_middleware


class DesktopApp:
    runner: web.AppRunner | None = None
    is_run: bool = True
    rpc_server: aiohttp_rpc.WsJsonRpcServer | None = None
    rpc_client: aiohttp_rpc.WsJsonRpcClient | None = None
    active_dialog: BaseDialog | None = None
    dialogs_map: dict
    dev_mode: bool
    google_app_id: str | None
    history: list[dict | str]
    file_storage: LocalFileStorage

    def __init__(self, *, dev_mode: bool, google_app_id: str | None) -> None:
        self.dev_mode = dev_mode
        self.google_app_id = google_app_id
        self.history = []

    async def init(self) -> None:
        file_storage_path = os.path.join(config.UPLOADS_DIR, str(uuid.uuid4()))

        if not os.path.exists(file_storage_path):
            os.makedirs(file_storage_path)

        self.file_storage = LocalFileStorage(
            target_directory=file_storage_path,
        )

        self.dialogs_map = load_dialogs(config.DIALOGS_PATH)


    async def start(self) -> None:
        logging.info('Staring...')

        self.rpc_server = aiohttp_rpc.WsJsonRpcServer(
            middlewares=aiohttp_rpc.middlewares.DEFAULT_MIDDLEWARES,
        )

        desktop_app = self

        class CustomWeakSetToTrack(weakref.WeakSet):
            def add(self, ws_connect: web_ws.WebSocketResponse) -> None:
                logging.info('Added `rpc_client`.')
                desktop_app.rpc_client = aiohttp_rpc.WsJsonRpcClient(ws_connect=ws_connect)
                super().add(ws_connect)

        self.rpc_server.rcp_websockets = CustomWeakSetToTrack()

        self.rpc_server.add_methods((
            aiohttp_rpc.JsonRpcMethod(self.process_message, name='process_message'),
            aiohttp_rpc.JsonRpcMethod(self.finish, name='finish'),
            aiohttp_rpc.JsonRpcMethod(self.get_history, name='get_history'),
            aiohttp_rpc.JsonRpcMethod(self.get_settings, name='get_settings'),
            aiohttp_rpc.JsonRpcMethod(self.activate_dialog, name='activate_dialog'),
            aiohttp_rpc.JsonRpcMethod(self.clear_dialog, name='clear_dialog'),
            aiohttp_rpc.JsonRpcMethod(self.process_audio, name='process_audio'),
        ))

        app = web.Application(middlewares=(
            index_middleware(),
        ))
        app.router.add_routes((
            web.get('/rpc', self.rpc_server.handle_http_request),
            web.post('/upload-file', self.handle_file_upload),
        ))
        app.router.add_static('/', path=config.STATICS_DIR, name='static')
        app.on_shutdown.append(self.rpc_server.on_shutdown)

        cors = aiohttp_cors.setup(app, defaults={
            '*': aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers='*',
                allow_headers='*',
            ),
        })

        for route in list(app.router.routes()):
            cors.add(route)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        os.system(f'kill -2 `lsof -t -i:{config.PORT}`')

        site = web.TCPSite(self.runner, config.HOST_NAME, port=config.PORT)

        await site.start()

    async def run_browser(self) -> None:
        logging.info('Run browser...')

        url = f'http://{config.HOST_NAME}:{config.PORT}/'

        if config.USE_WEBVIEW:
            from .webview import run_webview

            await run_webview(url)
        else:
            proc = await asyncio.create_subprocess_exec(
                'google-chrome',
                f'--app-id={self.google_app_id}' if self.google_app_id else f'--app={url}',
                '--disable-http-cache',
            )

            await proc.communicate()

    async def wait(self) -> NoReturn:
        logging.info('Waiting...')
        wait_time = datetime.timedelta(minutes=1)
        started_looking_at = datetime.datetime.now()

        while self.is_run:
            await asyncio.sleep(3)

            if not self.dev_mode and not self.rpc_client and datetime.datetime.now() - started_looking_at > wait_time:
                logging.info('Time limit.')
                break

    async def clean(self) -> None:
        logging.info('Cleaning...')

        if self.runner:
            await self.runner.cleanup()

    async def notify(self, text: str) -> None:
        await self.rpc_client.notify('show_notification', text)

    async def answer(self, answer: BaseAnswer) -> None:
        raw_answer = answer.to_dict()

        if isinstance(answer, Message):
            self.history.append(raw_answer)

        await self.rpc_client.notify('process_message', raw_answer)

    async def clear_dialog(self) -> None:
        self.history.clear()

        if self.active_dialog is not None:
            await self.active_dialog.clear_history()

    async def get_settings(self) -> dict:
        if self.active_dialog is None:
            await self.activate_dialog(next(iter(self.dialogs_map.keys())))

        return {
            'dialogs': [
                {
                    'name': name,
                    'is_active': self.active_dialog == dialog,
                    'files_are_supported': None if isinstance(dialog, LazyDialog) else dialog.files_are_supported,
                }
                for name, dialog in self.dialogs_map.items()
            ],
            'prompts': PROMPTS,
        }

    async def get_history(self) -> list[dict]:
        return self.history

    async def activate_dialog(self, dialog_name: str) -> None:
        await self.clear_dialog()

        if isinstance(self.dialogs_map[dialog_name], LazyDialog):
            try:
                self.dialogs_map[dialog_name] = self.dialogs_map[dialog_name]()
            except Exception as e:
                await self.notify(f'Failed to activate dialog "{dialog_name}":\n{e}')
                raise

        self.active_dialog = self.dialogs_map[dialog_name]

        await self.active_dialog.init()

        if welcome_message := await self.active_dialog.get_welcome_message():
            await self.answer(welcome_message)

    def finish(self) -> None:
        logging.info('Stopping...')

        if self.dev_mode:
            self.rpc_client = None
        else:
            self.is_run = False

    async def process_message(self, message: dict) -> None:
        is_callback = bool(message['body'].get('callback'))

        discussion = Discussion(app=self)

        if is_callback:
            request = Request(
                callback=message['body']['callback'],
                discussion=discussion,
            )
        else:
            request = Request(
                content=message['body']['content'],
                attachments=[
                    file
                    for file_id in message['body']['attachments']
                    if (file := self.file_storage.get(file_id))
                ],
                discussion=discussion,
            )
            self.history.append(message)

        async def _process_request() -> None:
            try:
                if is_callback:
                    await self.active_dialog.handle_callback(request)
                else:
                    await self.active_dialog.handle(request)
            except DialogError as e:
                logging.warning(e)
                await discussion.error(str(e))
            except Exception as e:
                logging.exception('Unhandled exception')
                await discussion.exception(e)
            finally:
                await discussion.finish()

        await discussion.start()
        asyncio.create_task(_process_request())

    async def handle_file_upload(self, request: web.Request) -> web.Response:
        saved_files = await self.file_storage.save_files(request)

        return web.json_response({
            'files': [
                saved_file.get_meta_info()
                for saved_file in saved_files
            ],
        })

    async def run(self) -> NoReturn:
        await self.init()

        try:
            await self.start()

            if not self.dev_mode:
                await self.run_browser()

            if not config.USE_WEBVIEW:
                await self.wait()
        finally:
            await self.clean()

    async def process_audio(self, file_id: str) -> dict:
        audio_file = self.file_storage.get(file_id)

        if not audio_file:
            error_message = 'Audio file not found.'
            logging.error(error_message)
            return {
                'error': error_message,
                'text': None,
                'cost': None,
            }

        with audio_file.open() as file:
            result = await Whisper.process(file)

        return {
            'error': None,
            'text': result.text,
            'cost': result.cost,
        }
