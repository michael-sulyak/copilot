import asyncio
import logging
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
from .web.middlewares import browser_security_middleware, index_middleware


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
        self._clearing_chats = set()
        self._settings_lock = asyncio.Lock()
        self._opening_chat_names = set()
        self._had_gui_connection = False
        self._gui_transports = set()

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
                desktop_app._had_gui_connection = True

                for opened_chat in desktop_app.opened_chats_map.values():
                    opened_chat.conversation.rpc_client = desktop_app.rpc_client

                super().add(ws_connect)

        self.rpc_server.rpc_websockets = CustomWeakSetToTrack()

        self.rpc_server.add_methods((
            aiohttp_rpc.JSONRPCMethod(self.get_chat_state, name='get_chat_state'),
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

        app = web.Application(
            middlewares=(browser_security_middleware, index_middleware()),
            client_max_size=config.MAX_UPLOAD_TOTAL_BYTES,
        )
        app.router.add_routes((
            web.get('/rpc', self.handle_rpc_request),
            web.post('/upload-file', self.handle_file_upload),
        ))
        app.router.add_static(
            self.file_storage.showed_directory,
            path=self.file_storage.target_directory,
            name='uploads',
        )
        app.router.add_static('/', path=config.STATICS_DIR, name='static')
        app.on_shutdown.append(self.shutdown_rpc)

        cors = aiohttp_cors.setup(app, defaults={
            origin: aiohttp_cors.ResourceOptions(allow_headers=('Content-Type',))
            for origin in config.ALLOWED_ORIGINS
        })

        for route in list(app.router.routes()):
            cors.add(route)

        self.runner = web.AppRunner(app, shutdown_timeout=5)
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

    async def handle_rpc_request(self, request: web.Request) -> web.StreamResponse:
        transport = request.transport
        if transport is None or request.headers.get('Upgrade', '').lower() != 'websocket':
            return await self.rpc_server.handle_http_request(request)

        self._gui_transports.add(transport)
        response = None
        try:
            response = await self.rpc_server.handle_http_request(request)
            return response
        finally:
            if not isinstance(response, web_ws.WebSocketResponse) or response.closed:
                self._gui_transports.discard(transport)

    async def shutdown_rpc(self, app: web.Application) -> None:
        try:
            # AppRunner's shutdown_timeout does not cover on_shutdown hooks.
            async with asyncio.timeout(5):
                await self.rpc_server.on_shutdown(app)
        except TimeoutError:
            logging.warning('RPC shutdown timed out; closing remaining GUI transports.')
        finally:
            for transport in self._gui_transports:
                transport.abort()
            self._gui_transports.clear()

    async def run_browser(self) -> None:
        logging.info('Run browser...')

        url = f'http://{config.HOST_NAME}:{config.PORT}/'

        if config.USE_WEBVIEW:
            from .webview import run_webview

            await run_webview(url)
        else:
            # Chrome may reuse an existing process or keep running in the
            # background after the app window closes. Track GUI connections,
            # not the launcher process, so neither case blocks shutdown.
            await asyncio.create_subprocess_exec(
                'google-chrome',
                f'--app-id={self.google_app_id}' if self.google_app_id else f'--app={url}',
                '--disable-http-cache',
            )

    async def wait(self) -> None:
        logging.info('Waiting...')
        disconnected_at = None
        loop = asyncio.get_running_loop()

        while self.is_run:
            await asyncio.sleep(1)
            # A WebSocket's closed flag can lag behind its transport when the
            # RPC handler is still waiting for work. Do not let that stale
            # connection keep the application alive after the browser exits.
            self._gui_transports = {
                transport for transport in self._gui_transports
                if not transport.is_closing()
            }
            connected = bool(self._gui_transports) and any(
                not ws.closed for ws in self.rpc_server.rpc_websockets
            )
            if connected or self.dev_mode:
                disconnected_at = None
                continue

            if disconnected_at is None:
                disconnected_at = loop.time()

            # Allow initial browser startup more time than a reload/reconnect.
            # Running requests must not keep a closed desktop application alive;
            # clean() cancels them once this grace period expires.
            timeout = 5 if self._had_gui_connection else 60
            if loop.time() - disconnected_at >= timeout:
                logging.info('No GUI connections for %s seconds; stopping.', timeout)
                self.is_run = False
                break

    async def clean(self) -> None:
        logging.info('Cleaning...')

        # Cancel all chats together so remote cancellation waits do not add up
        # sequentially when many chat tabs are running.
        await asyncio.gather(*(
            self._cancel_chat_tasks(chat_uuid)
            for chat_uuid in list(self.processing_tasks)
        ))

        for chat_uuid in list(self.opened_chats_map):
            try:
                await self.close_chat(chat_uuid)
            except Exception:
                logging.exception('Failed to close chat "%s" during cleanup.', chat_uuid)

        for chat_uuid in list(self.processing_tasks):
            await self._cancel_chat_tasks(chat_uuid)

        if self.runner:
            await self.runner.cleanup()

    async def clear_chat(self, chat_uuid: str) -> dict:
        opened_chat = self._get_opened_chat(chat_uuid)

        if chat_uuid in self._clearing_chats:
            raise ValueError('This chat is already being cleared.')

        self._clearing_chats.add(chat_uuid)

        try:
            await self._cancel_chat_tasks(chat_uuid)
            await opened_chat.chat.clear_history()
            opened_chat.history.clear()

            if welcome_message := await opened_chat.chat.get_welcome_message():
                await opened_chat.conversation.answer(welcome_message)

            await opened_chat.conversation.finish()

            return await self.get_chat_state(chat_uuid)
        finally:
            self._clearing_chats.discard(chat_uuid)

    async def close_chat(self, chat_uuid: str) -> None:
        if chat_uuid in self._clearing_chats:
            raise ValueError('This chat is being cleared. Please wait.')
        opened_chat = self.opened_chats_map.pop(chat_uuid, None)

        if opened_chat is None:
            raise ValueError(f'Chat "{chat_uuid}" is not opened.')

        try:
            await self._cancel_chat_tasks(chat_uuid)
        finally:
            await opened_chat.chat.close()

    async def get_settings(self) -> dict:
        async with self._settings_lock:
            if not self.opened_chats_map:
                await self.open_chat(self._get_default_chat_name())

        return {
            'available_chats': [
                {
                    'name': name,
                }
                for name, chat in self.available_chats_map.items()
            ],
            'opened_chats': [
                {
                    'uuid': str(opened_chat.uuid),
                    'name': opened_chat.name,
                    'files_are_supported': opened_chat.chat.files_are_supported,
                    'revision': opened_chat.conversation.get_status()['revision'],
                }
                for opened_chat in self.opened_chats_map.values()
            ],
            'prompts': PROMPTS,
            'protocol_version': 1,
        }

    async def get_history(self, chat_uuid: str) -> list[dict]:
        if not self.opened_chats_map:
            return []

        opened_chat = self._get_opened_chat(chat_uuid)

        return self._serialize_history(opened_chat)

    def _serialize_history(self, opened_chat: OpenedChat) -> list[dict]:
        history = []
        for item in opened_chat.history.values():
            serialized = item.model_dump(by_alias=True)
            if isinstance(item, InputMessage) and not item.is_callback:
                # Resolve metadata from storage, never from client-provided UI state.
                serialized['attachments'] = [
                    file.get_meta_info() if (file := self.file_storage.get(file_id)) is not None else {
                        'id': file_id, 'name': 'Attachment unavailable', 'url': None,
                    }
                    for file_id in item.body.attachments
                ]
            history.append(serialized)
        return history

    async def get_chat_state(self, chat_uuid: str) -> dict:
        opened_chat = self._get_opened_chat(chat_uuid)
        state = opened_chat.conversation.get_status()
        return {
            'history': self._serialize_history(opened_chat),
            **state,
        }

    async def open_chat(self, chat_name: str) -> dict:
        if chat_name not in self.available_chats_map:
            raise ValueError(f'Chat "{chat_name}" is not available.')

        rpc_client = self._get_rpc_client()

        number = 0
        new_chat_name = chat_name
        used_names = {chat.name for chat in self.opened_chats_map.values()} | self._opening_chat_names
        while new_chat_name in used_names:
            number += 1
            new_chat_name = f'{chat_name} - {number}'
        self._opening_chat_names.add(new_chat_name)

        opened_chat = OpenedChat(
            name=new_chat_name,
            original_chat=self.available_chats_map[chat_name],
            rpc_client=rpc_client,
        )

        try:
            await opened_chat.init()
        except BaseException:
            if hasattr(opened_chat, 'chat'):
                await opened_chat.chat.close()
            raise
        finally:
            self._opening_chat_names.discard(new_chat_name)

        # Publish only initialized chats: settings/history RPCs may run concurrently.
        opened_chat.conversation.rpc_client = self._get_rpc_client()
        self.opened_chats_map[str(opened_chat.uuid)] = opened_chat
        return {
            'uuid': str(opened_chat.uuid),
            'name': opened_chat.name,
            'files_are_supported': opened_chat.chat.files_are_supported,
        }

    def finish(self) -> None:
        logging.info('Stopping...')

        if self.dev_mode:
            self.rpc_client = None
        else:
            self.is_run = False

    async def process_message(self, message: dict) -> dict:
        message = InputMessage.model_validate(message)
        opened_chat = self._get_opened_chat(message.chat_uuid)

        if message.chat_uuid in self._clearing_chats:
            raise ValueError('This chat is being cleared. Please wait.')

        is_processing = any(not task.done() for task in self.processing_tasks.get(message.chat_uuid, ()))

        if message.uuid in opened_chat.history:
            previous_message = opened_chat.history[message.uuid]

            if not isinstance(previous_message, InputMessage) or previous_message.body != message.body:
                raise ValueError('This message UUID is already used for different content.')

            return {
                'accepted': True, 'message_uuid': message.uuid, 'duplicate': True,
                **opened_chat.conversation.get_status(),
            }

        if is_processing and (
            not message.is_callback or not opened_chat.chat.can_handle_callback_while_processing(message.body.callback)
        ):
            raise ValueError('This chat is already processing a message.')

        # Callbacks must remain available while an agent waits for user approval.
        manages_status = not (message.is_callback and is_processing)

        if message.is_callback:
            request = Request(
                callback=message.body.callback,
                conversation=opened_chat.conversation,
            )
        else:
            attachments = [self.file_storage.get(file_id) for file_id in message.body.attachments]
            if any(file is None for file in attachments):
                raise ValueError('An attachment is no longer available. Please upload it again.')

            if attachments and not opened_chat.chat.files_are_supported:
                raise ValueError('This chat does not support attachments.')

            if not message.body.content.strip() and not attachments:
                raise ValueError('A message must contain text or attachments.')

            request = Request(
                content=message.body.content,
                attachments=attachments,
                conversation=opened_chat.conversation,
            )
            opened_chat.history[message.uuid] = message

        async def _process_request() -> None:
            cancelled = False

            try:
                if manages_status:
                    await opened_chat.conversation.start()

                if message.is_callback:
                    await opened_chat.chat.handle_callback(request)
                else:
                    await opened_chat.chat.handle(request)
            except asyncio.CancelledError:
                cancelled = True
                logging.info('Processing task for chat "%s" was cancelled.', message.chat_uuid)
                raise
            except ChatError as e:
                logging.warning(e)
                await opened_chat.conversation.error(str(e))
            except Exception as e:
                logging.exception('Unhandled exception')
                await opened_chat.conversation.exception(e)
            finally:
                # A closed chat no longer has UI state to reset. More
                # importantly, cancellation should not start new RPC work.
                if not cancelled and manages_status:
                    try:
                        await opened_chat.conversation.finish()
                    except Exception:
                        logging.exception('Failed to finish conversation for chat "%s".', message.chat_uuid)

        if manages_status:
            opened_chat.conversation.mark_loading()

        task = asyncio.create_task(_process_request())
        self._track_chat_task(message.chat_uuid, task)
        return {'accepted': True, 'message_uuid': message.uuid, 'duplicate': False}

    async def handle_file_upload(self, request: web.Request) -> web.Response:
        try:
            async with asyncio.timeout(120):
                saved_files = await self.file_storage.save_files(request)
        except TimeoutError as error:
            raise web.HTTPRequestTimeout(text='Upload timed out.') from error

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

            if self.dev_mode or not config.USE_WEBVIEW:
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

        async with asyncio.timeout(120):
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
        if not task.cancelled() and (error := task.exception()) is not None:
            logging.error('Chat task failed for "%s".', chat_uuid, exc_info=error)

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
