import asyncio
import datetime
import logging
import uuid
import weakref
from typing import NoReturn

import aiohttp_cors
import aiohttp_rpc
from aiohttp import web, web_ws

from . import config
from .chats.base import BaseAnswer, BaseChat, ChatError, Conversation, Request
from .chats.chat_loader import LazyChat, load_chats
from .chats.prompts import PROMPTS
from .desktop_defs import InputMessage, OutputMessage
from .models.openai.base import Gpt4oTranscriber
from .utils.local_file_storage import LocalFileStorage, get_file_storage
from .utils.system import ask_gui_confirmation, get_pids_using_port, get_processes_using_port, kill_pids
from .web.middlewares import index_middleware


class OpenedChat:
    uuid: uuid.UUID
    messages: dict[str, InputMessage | OutputMessage]
    original_chat: BaseChat | LazyChat
    chat: BaseChat
    conversation: Conversation

    def __init__(self, *, original_chat: BaseChat | LazyChat, conversation: Conversation) -> None:
        self.messages = {}
        self.original_chat = original_chat
        self.conversation = conversation
        self.uuid = uuid.uuid4()

    async def init(self) -> None:
        if isinstance(self.original_chat, LazyChat):
            try:
                self.chat = self.original_chat()
            except Exception as e:
                await self.conversation.notify(f'Failed to activate chat:\n{e}')
                raise
        else:
            self.chat = self.original_chat

        await self.chat.init()

        if welcome_message := await self.chat.get_welcome_message():
            await self.conversation.answer(welcome_message)


class StopDesktopApp(Exception):
    pass

class DesktopApp:
    runner: web.AppRunner | None = None
    is_run: bool = True
    rpc_server: aiohttp_rpc.WSJSONRPCServer | None = None
    rpc_client: aiohttp_rpc.WSJSONRPCClient | None = None
    opened_chat: OpenedChat | None = None
    chats_map: dict
    dev_mode: bool
    google_app_id: str | None
    file_storage: LocalFileStorage

    def __init__(self, *, dev_mode: bool, google_app_id: str | None) -> None:
        self.dev_mode = dev_mode
        self.google_app_id = google_app_id

    async def init(self) -> None:
        self.file_storage = get_file_storage()
        self.chats_map = load_chats(config.CHATS_PATH)

    async def start(self) -> None:
        logging.info('Staring...')

        self.rpc_server = aiohttp_rpc.WSJSONRPCServer(
            middlewares=aiohttp_rpc.middlewares.DEFAULT_MIDDLEWARES,
        )

        desktop_app = self

        class CustomWeakSetToTrack(weakref.WeakSet):
            def add(self, ws_connect: web_ws.WebSocketResponse) -> None:
                logging.info('Added `rpc_client`.')
                desktop_app.rpc_client = aiohttp_rpc.WSJSONRPCClient(ws_connect=ws_connect)
                super().add(ws_connect)

        self.rpc_server.rpc_websockets = CustomWeakSetToTrack()

        self.rpc_server.add_methods((
            aiohttp_rpc.JSONRPCMethod(self.process_message, name='process_message'),
            aiohttp_rpc.JSONRPCMethod(self.finish, name='finish'),
            aiohttp_rpc.JSONRPCMethod(self.get_history, name='get_history'),
            aiohttp_rpc.JSONRPCMethod(self.get_settings, name='get_settings'),
            aiohttp_rpc.JSONRPCMethod(self.open_chat, name='open_chat'),
            aiohttp_rpc.JSONRPCMethod(self.clear_chat, name='clear_chat'),
            aiohttp_rpc.JSONRPCMethod(self.process_audio, name='process_audio'),
            aiohttp_rpc.JSONRPCMethod(self.delete_message, name='delete_message'),
        ))

        app = web.Application(middlewares=(
            index_middleware(),
        ))
        app.router.add_routes((
            web.get('/rpc', self.rpc_server.handle_http_request),
            web.post('/upload-file', self.handle_file_upload),
        ))
        app.router.add_static(self.file_storage.showed_directory, path=self.file_storage.target_directory,
                              name='uploads')
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
                        f'Remaining PID(s): {", ".join(remaining_pids)}\n\n'
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
        output_obj = answer.to_output_obj()

        if isinstance(output_obj, OutputMessage):
            self.opened_chat.messages[output_obj.uuid] = output_obj

        await self.rpc_client.notify('process_message', output_obj.model_dump(by_alias=True))

    async def clear_chat(self) -> None:
        if self.opened_chat is not None:
            self.opened_chat.messages.clear()
            await self.opened_chat.chat.clear_history()

    async def get_settings(self) -> dict:
        if self.opened_chat is None:
            await self.open_chat(next(iter(self.chats_map.keys())))

        return {
            'available_chats': [
                {
                    'name': name,
                }
                for name, chat in self.chats_map.items()
            ],
            'opened_chats': [
                {
                    'uuid': str(self.opened_chat.uuid),
                    'name': name,
                }
                for name, chat in self.chats_map.items()
                if self.opened_chat and self.opened_chat.original_chat == chat
            ],
            'prompts': PROMPTS,
        }

    async def get_history(self) -> list[dict]:
        if not self.opened_chat:
            return []

        return [
            item.model_dump(by_alias=True)
            for item in self.opened_chat.messages.values()
        ]

    async def open_chat(self, chat_name: str) -> None:
        await self.clear_chat()

        self.opened_chat = OpenedChat(
            original_chat=self.chats_map[chat_name],
            conversation=Conversation(app=self),
        )

        await self.opened_chat.init()

    def finish(self) -> None:
        logging.info('Stopping...')

        if self.dev_mode:
            self.rpc_client = None
        else:
            self.is_run = False

    async def process_message(self, message: dict) -> None:
        message = InputMessage.model_validate(message)
        conversation = Conversation(app=self)

        if message.is_callback:
            request = Request(
                callback=message.body.callback,
                conversation=conversation,
            )
        else:
            request = Request(
                content=message.body.content,
                attachments=[
                    file
                    for file_id in message.body.attachments
                    if (file := self.file_storage.get(file_id))
                ],
                conversation=conversation,
            )
            self.opened_chat.messages[message.uuid] = message

        async def _process_request() -> None:
            try:
                if message.is_callback:
                    await self.opened_chat.chat.handle_callback(request)
                else:
                    await self.opened_chat.chat.handle(request)
            except ChatError as e:
                logging.warning(e)
                await conversation.error(str(e))
            except Exception as e:
                logging.exception('Unhandled exception')
                await conversation.exception(e)
            finally:
                await conversation.finish()

        await conversation.start()
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
        except StopDesktopApp:
            pass
        finally:
            await self.clean()

    async def edit_message(self, message: dict) -> None:
        message = InputMessage.model_validate(message)

        if message.uuid not in self.opened_chat.messages:
            raise RuntimeError(f'Message with UUID "{message.uuid}" not found.')

        self.opened_chat.messages[message.uuid] = message

    async def delete_message(self, message_uuid: str) -> None:
        self.opened_chat.messages.pop(message_uuid, None)

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
