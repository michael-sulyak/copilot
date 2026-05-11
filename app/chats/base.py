import abc
import dataclasses
import datetime
import time
import typing
import uuid

import aiohttp_rpc
from pydantic import BaseModel

from ..desktop_defs import InputMessage, OutputAction, OutputMessage
from ..utils.local_file_storage import File
from .constants import Actions, Statuses


if typing.TYPE_CHECKING:
    from .chat_loader import LazyChat

class ChatError(Exception):
    pass


class Roles:
    USER = 'user'
    SYSTEM = 'system'
    ASSISTANT = 'assistant'


@dataclasses.dataclass
class AnswerBtn:
    name: str
    callback: str

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'callback': self.callback,
        }


class BaseAnswer(abc.ABC):
    @abc.abstractmethod
    def to_dict(self) -> dict:
        pass

    @abc.abstractmethod
    def to_output_obj(self, *, default_chat_uuid: uuid.UUID | None = None) -> BaseModel:
        pass


@dataclasses.dataclass(frozen=True)
class Message(BaseAnswer):
    content: str
    buttons: tuple[AnswerBtn, ...] = ()
    duration: datetime.timedelta | None = None
    cost: float | None = None
    total_tokens: int | None = None
    chat_uuid: uuid.UUID | None = None
    uuid: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
    timestamp: int = dataclasses.field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            'uuid': str(self.uuid),
            'chat_uuid': self.chat_uuid and str(self.chat_uuid),
            'type': 'message',
            'from': 'bot',
            'body': {
                'content': self.content,
                'duration': None if self.duration is None else self.duration.total_seconds(),
                'cost': self.cost,
                'total_tokens': self.total_tokens,
            },
            'buttons': [
                button.to_dict()
                for button in self.buttons
            ],
            'timestamp': self.timestamp,
        }

    def to_output_obj(self, *, default_chat_uuid: uuid.UUID | None = None) -> OutputMessage:
        data = self.to_dict()

        if not self.chat_uuid and default_chat_uuid:
            data['chat_uuid'] = str(default_chat_uuid)

        return OutputMessage.model_validate(data)


@dataclasses.dataclass
class Action(BaseAnswer):
    name: str
    payload: typing.Any = None
    chat_uuid: uuid.UUID | None = None

    def to_dict(self) -> dict:
        return {
            'type': 'action',
            'chat_uuid': self.chat_uuid and str(self.chat_uuid),
            'name': self.name,
            'payload': self.payload,
            'timestamp': time.time_ns(),
        }

    def to_output_obj(self, *, default_chat_uuid: uuid.UUID | None = None) -> OutputAction:
        data = self.to_dict()

        if not self.chat_uuid and default_chat_uuid:
            data['chat_uuid'] = str(default_chat_uuid)

        return OutputAction.model_validate(data)


class Conversation:
    """
    A communication bridge between a chat and the DesktopApp, providing
    methods to send messages, update chat status, and report errors to the UI.
    """

    _rpc_client: aiohttp_rpc.WSJSONRPCClient
    _opened_chat: 'OpenedChat'
    _chat_status: Statuses.IDLE

    def __init__(self, *, rpc_client: aiohttp_rpc.WSJSONRPCClient, opened_chat: 'OpenedChat') -> None:
        self._rpc_client = rpc_client
        self._opened_chat = opened_chat

    async def answer(self, answer: BaseAnswer) -> None:
        output_obj = answer.to_output_obj(default_chat_uuid=self._opened_chat.uuid)

        if isinstance(output_obj, OutputMessage):
            self._opened_chat.messages[output_obj.uuid] = output_obj

        await self._rpc_client.notify('process_message', output_obj.model_dump(by_alias=True))

    async def notify(self, text: str) -> None:
        await self._rpc_client.notify('show_notification', text)

    async def start(self) -> None:
        self._chat_status = Statuses.LOADING
        await self.answer(Action(name=Actions.SET_CHAT_STATUS, payload={'status': self._chat_status, 'text': None}))

    async def finish(self) -> None:
        self._chat_status = Statuses.IDLE
        await self.answer(Action(name=Actions.SET_CHAT_STATUS, payload={'status': self._chat_status, 'text': None}))

    async def set_text_status(self, text: str) -> None:
        await self.answer(Action(name=Actions.SET_CHAT_STATUS, payload={'status': self._chat_status, 'text': text}))

    async def reset_text_status(self) -> None:
        await self.set_text_status('')

    async def error(self, text: str) -> None:
        await self.answer(Message(content=f'**ERROR:**\n```\n{text!s}\n```'))

    async def exception(self, e: Exception) -> None:
        await self.answer(Message(content=f'**UNEXPECTED ERROR:**\n```\n{e!s}\n```'))


class OpenedChat:
    uuid: uuid.UUID
    messages: dict[str, InputMessage | OutputMessage]
    original_chat: BaseChat | LazyChat
    chat: BaseChat
    conversation: Conversation

    def __init__(self, *, original_chat: typing.Union[BaseChat, 'LazyChat'], rpc_client: aiohttp_rpc.WSJSONRPCClient) -> None:
        self.uuid = uuid.uuid4()
        self.messages = {}
        self.original_chat = original_chat
        self.conversation = Conversation(rpc_client=rpc_client, opened_chat=self)

    async def init(self) -> None:
        from .chat_loader import LazyChat

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


@dataclasses.dataclass
class Request:
    conversation: Conversation
    content: str | None = None
    callback: str | None = None
    attachments: list[File] | None = None


class BaseChat:
    """
    Abstract base class defining the lifecycle and behavior of a chat,
    including message handling, callbacks, initialization, and cleanup.
    """

    files_are_supported: bool = False

    async def init(self) -> None:
        pass

    async def handle(self, request: Request) -> None:
        pass

    async def clear_history(self) -> None:
        pass

    async def get_welcome_message(self) -> Message | None:
        # todo: replace `get_welcome_message` -> `welcome` and use discussion
        return None

    async def handle_callback(self, request: Request) -> None:
        await request.conversation.answer(Message(content='Not implemented.'))
