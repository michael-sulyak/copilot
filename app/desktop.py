import asyncio
import datetime
import logging
import typing
import weakref

import aiohttp_cors
import aiohttp_rpc
from aiohttp import web, web_ws

from . import config
from .chats.base import ChatError, OpenedChat, Request
from .chats.chat_loader import load_chats
from .chats.prompts import PROMPTS
from .desktop_defs import InputMessage
from .models.openai.base import Gpt4oTranscriber
from .utils.local_file_storage import LocalFileStorage, get_file_storage
from .utils.system import ask_gui_confirmation, get_pids_using_port, get_processes_using_port, kill_pids
from .web.middlewares import index_middleware


class StopDesktopApp(Exception):
    pass


class DesktopApp:
    runner: web.AppRunner | None = None
    is_run: bool = True
    rpc_server: aiohttp_rpc.WSJSONRPCServer | None = None
    rpc_client: aiohttp_rpc.WSJSONRPCClient | None = None
    opened_chats_map: dict[str, OpenedChat]
    available_chats_map: dict
    processing_tasks: dict[str, set[asyncio.Task]]
    dev_mode: bool
    google_app_id: str | None
    file_storage: LocalFileStorage

    def __init__(self, *, dev_mode: bool, google_app_id: str | None) -> None:
        self.dev_mode = dev_mode
        self.google_app_id = google_app_id
        self.is_run = True

    async def init(self) -> None:
        self.file_storage = get_file_storage()
        self.available_chats_map = load_chats(config.CHATS_PATH)
        self.opened_chats_map = {}
        self.processing_tasks = {}

    async def start(self) -> None:
        logging.info('Starting...')

        self.rpc_server = aiohttp_rpc.WSJSONRPCServer(
            middlewares=aiohttp_rpc.middlewares.DEFAULT_MIDDLEWARES,
        )

        desktop_app = self

        class CustomWeakSetToTrack(weakref.WeakSet):
            def add(self, ws_connect: web_ws.WebSocketResponse) -> None:
                logging.info('Added `rpc_client`.')
                desktop_app.rpc_client = aiohttp_rpc.WSJSONRPCClient(ws_connect=ws_connect)

                for opened_chat in desktop_app.opened_chats_map.values():
                    opened_chat.conversation.rpc_client = desktop_app.rpc_client

                super().add(ws_connect)

        self.rpc_server.rpc_websockets = CustomWeakSetToTrack()

        self.rpc_server.add_methods((
            aiohttp_rpc.JSONRPCMethod(self.process_message, name='process_message'),
            aiohttp_rpc.JSONRPCMethod(self.finish, name='finish'),
            aiohttp_rpc.JSONRPCMethod(self.get_history, name='get_history'),
            aiohttp_rpc.JSONRPCMethod(self.get_settings, name='get_settings'),
            aiohttp_rpc.JSONRPCMethod(self.open_chat, name='open_chat'),
            aiohttp_rpc.JSONRPCMethod(self.clear_chat, name='clear_chat'),
            aiohttp_rpc.JSONRPCMethod(self.close_chat, name='close_chat'),
            aiohttp_rpc.JSONRPCMethod(self.process_audio, name='process_audio'),
            # aiohttp_rpc.JSONRPCMethod(self.delete_message, name='delete_message'),
        ))

        app = web.Application(middlewares=(
            index_middleware(),
        ))
        app.router.add_routes((
            web.get('/rpc', self.rpc_server.handle_http_request),
            web.post('/upload-file', self.handle_file_upload),
        ))
        app.router.add_static(
            self.file_storage.showed_directory,
            path=self.file_storage.target_directory,
            name='uploads',
        )
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

        site = web.TCPSite(self.runner, config.HOST_NAME, port=config.PORT)

        try:
            await site.start()
        except OSError:
            process_info = await get_processes_using_port(config.PORT)
            pids = await get_pids_using_port(config.PORT)

            if not pids:
                logging.exception('Port is busy, but no process was found.')
                raise StopDesktopApp

            confirmed = await ask_gui_confirmation(
                title='Port is already in use',
                text=(
                    f'{process_info}\n\n'
                    f'Do you want to kill the process and continue?'
                ),
            )

            if not confirmed:
                logging.info('User declined to kill process.')
                raise StopDesktopApp

            await kill_pids(pids, signal='-2')
            await site.stop()
            await asyncio.sleep(1)

            remaining_pids = await get_pids_using_port(config.PORT)

            if remaining_pids:
                confirmed_force = await ask_gui_confirmation(
                    title='Process did not stop',
                    text=(
                        f'The process using port {config.PORT} did not stop gracefully.\n\n'
                        f'Remaining PID(s): {", ".join(map(str, remaining_pids))}\n\n'
                        f'Force kill them?'
                    ),
                )

                if not confirmed_force:
                    logging.info('User declined force kill.')
                    raise StopDesktopApp

                await kill_pids(remaining_pids, signal='-9')

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

    async def wait(self) -> typing.NoReturn:
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

        for chat_uuid in list(self.processing_tasks.keys()):
            await self._cancel_chat_tasks(chat_uuid)

        if self.runner:
            await self.runner.cleanup()

    async def clear_chat(self, chat_uuid: str) -> None:
        opened_chat = self._get_opened_chat(chat_uuid)
        opened_chat.history.clear()
        await opened_chat.chat.clear_history()

    async def close_chat(self, chat_uuid: str) -> None:
        self._get_opened_chat(chat_uuid)

        await self._cancel_chat_tasks(chat_uuid)
        del self.opened_chats_map[chat_uuid]

    async def get_settings(self) -> dict:
        if not self.opened_chats_map:
            await self.open_chat(self._get_default_chat_name())

        return {
            'available_chats': [
                {
                    'name': name,
                    'files_are_supported': self._chat_files_are_supported(chat),
                }
                for name, chat in self.available_chats_map.items()
            ],
            'opened_chats': [
                {
                    'uuid': str(opened_chat.uuid),
                    'name': opened_chat.name,
                    'files_are_supported': self._chat_files_are_supported(opened_chat.chat),
                }
                for opened_chat in self.opened_chats_map.values()
            ],
            'prompts': PROMPTS,
        }

    async def get_history(self, chat_uuid: str) -> list[dict]:
        if not self.opened_chats_map:
            return []

        opened_chat = self._get_opened_chat(chat_uuid)

        return [
            item.model_dump(by_alias=True)
            for item in opened_chat.history.values()
        ]

    async def open_chat(self, chat_name: str) -> dict:
        if chat_name not in self.available_chats_map:
            raise ValueError(f'Chat "{chat_name}" is not available.')

        rpc_client = self._get_rpc_client()

        number = 0
        new_chat_name = chat_name
        chat_name_is_correct = None

        while not chat_name_is_correct:
            for opened_chat in self.opened_chats_map.values():
                if new_chat_name == opened_chat.name:
                    number += 1
                    new_chat_name = f'{chat_name} - {number}'
                    break
            else:
                chat_name_is_correct = True

        opened_chat = OpenedChat(
            name=new_chat_name,
            original_chat=self.available_chats_map[chat_name],
            rpc_client=rpc_client,
        )

        self.opened_chats_map[str(opened_chat.uuid)] = opened_chat

        try:
            await opened_chat.init()
        except Exception:
            self.opened_chats_map.pop(str(opened_chat.uuid), None)
            raise

        return {
            'uuid': str(opened_chat.uuid),
            'name': opened_chat.name,
            'files_are_supported': self._chat_files_are_supported(opened_chat.chat),
        }

    def finish(self) -> None:
        logging.info('Stopping...')

        if self.dev_mode:
            self.rpc_client = None
        else:
            self.is_run = False

    async def process_message(self, message: dict) -> None:
        message = InputMessage.model_validate(message)
        opened_chat = self._get_opened_chat(message.chat_uuid)

        if message.is_callback:
            request = Request(
                callback=message.body.callback,
                conversation=opened_chat.conversation,
            )
        else:
            request = Request(
                content=message.body.content,
                attachments=[
                    file
                    for file_id in message.body.attachments
                    if (file := self.file_storage.get(file_id))
                ],
                conversation=opened_chat.conversation,
            )
            opened_chat.history[message.uuid] = message

        async def _process_request() -> None:
            try:
                if message.is_callback:
                    await opened_chat.chat.handle_callback(request)
                else:
                    await opened_chat.chat.handle(request)
            except asyncio.CancelledError:
                logging.info('Processing task for chat "%s" was cancelled.', message.chat_uuid)
                raise
            except ChatError as e:
                logging.warning(e)
                await opened_chat.conversation.error(str(e))
            except Exception as e:
                logging.exception('Unhandled exception')
                await opened_chat.conversation.exception(e)
            finally:
                try:
                    await opened_chat.conversation.finish()
                except Exception:
                    logging.exception('Failed to finish conversation for chat "%s".', message.chat_uuid)

        await opened_chat.conversation.start()

        task = asyncio.create_task(_process_request())
        self._track_chat_task(message.chat_uuid, task)

    async def handle_file_upload(self, request: web.Request) -> web.Response:
        saved_files = await self.file_storage.save_files(request)

        return web.json_response({
            'files': [
                saved_file.get_meta_info()
                for saved_file in saved_files
            ],
        })

    async def run(self) -> None:
        await self.init()

        try:
            await self.start()

            if not self.dev_mode:
                await self.run_browser()

            if not config.USE_WEBVIEW:
                await self.wait()
        except StopDesktopApp:
            pass
        finally:
            await self.clean()

    # async def edit_message(self, message: dict) -> None:
    #     message = InputMessage.model_validate(message)
    #
    #     if message.uuid not in self.opened_chat.history:
    #         raise RuntimeError(f'Message with UUID "{message.uuid}" not found.')
    #
    #     self.opened_chat.history[message.uuid] = message

    # async def delete_message(self, message_uuid: str) -> None:
    #     self.opened_chat.history.pop(message_uuid, None)

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
            result = await Gpt4oTranscriber.process(file)

        return {
            'error': None,
            'text': result.text,
            'cost': result.cost,
        }

    def _get_rpc_client(self) -> aiohttp_rpc.WSJSONRPCClient:
        if self.rpc_client is None:
            raise RuntimeError('RPC client is not connected.')

        return self.rpc_client

    def _get_opened_chat(self, chat_uuid: str) -> OpenedChat:
        opened_chat = self.opened_chats_map.get(chat_uuid)

        if not opened_chat:
            raise ValueError(f'Chat "{chat_uuid}" is not opened.')

        return opened_chat

    def _get_default_chat_name(self) -> str:
        try:
            return next(iter(self.available_chats_map.keys()))
        except StopIteration:
            raise RuntimeError('No chats are available.')

    def _track_chat_task(self, chat_uuid: str, task: asyncio.Task) -> None:
        self.processing_tasks.setdefault(chat_uuid, set()).add(task)
        task.add_done_callback(lambda completed_task: self._discard_chat_task(chat_uuid, completed_task))

    def _discard_chat_task(self, chat_uuid: str, task: asyncio.Task) -> None:
        tasks = self.processing_tasks.get(chat_uuid)

        if not tasks:
            return

        tasks.discard(task)

        if not tasks:
            self.processing_tasks.pop(chat_uuid, None)

    async def _cancel_chat_tasks(self, chat_uuid: str) -> None:
        tasks = self.processing_tasks.pop(chat_uuid, set())

        if not tasks:
            return

        for task in tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _chat_files_are_supported(chat: typing.Any) -> bool:
        return bool(
            getattr(
                chat,
                'files_are_supported',
                getattr(
                    chat,
                    'files_supported',
                    getattr(chat, 'supports_files', False),
                ),
            ),
        )
