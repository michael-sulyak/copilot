import abc
import dataclasses
import datetime
import time
import typing
import uuid

from pydantic import BaseModel

from ..desktop_defs import OutputAction, OutputMessage
from ..utils.local_file_storage import File
from .constants import Actions, Statuses


if typing.TYPE_CHECKING:
    from ..desktop import DesktopApp


class DialogError(Exception):
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
    def to_output_obj(self) -> BaseModel:
        pass


@dataclasses.dataclass(frozen=True)
class Message(BaseAnswer):
    content: str
    buttons: tuple[AnswerBtn, ...] = ()
    duration: datetime.timedelta | None = None
    cost: float | None = None
    total_tokens: int | None = None
    uuid: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: int = dataclasses.field(default_factory=time.time_ns)

    def to_dict(self) -> dict:
        return {
            'uuid': self.uuid,
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

    def to_output_obj(self) -> OutputMessage:
        return OutputMessage.model_validate(self.to_dict())


@dataclasses.dataclass
class Action(BaseAnswer):
    name: str
    payload: typing.Any = None

    def to_dict(self) -> dict:
        return {
            'type': 'action',
            'name': self.name,
            'payload': self.payload,
            'timestamp': time.time_ns(),
        }

    def to_output_obj(self) -> OutputAction:
        return OutputAction.model_validate(self.to_dict())


class Discussion:
    _chat_status: Statuses.IDLE

    def __init__(self, *, app: 'DesktopApp') -> None:
        self._app = app

    async def answer(self, answer: BaseAnswer) -> None:
        await self._app.answer(answer)

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

    async def notify(self, text: str) -> None:
        await self._app.notify(text)

    async def error(self, text: str) -> None:
        await self.answer(Message(content=f'**ERROR:**\n```\n{text!s}\n```'))

    async def exception(self, e: Exception) -> None:
        await self.answer(Message(content=f'**UNEXPECTED ERROR:**\n```\n{e!s}\n```'))


@dataclasses.dataclass
class Request:
    discussion: Discussion
    content: str | None = None
    callback: str | None = None
    attachments: list[File] | None = None


class BaseDialog:
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
        await request.discussion.answer(Message(content='Not implemented.'))
