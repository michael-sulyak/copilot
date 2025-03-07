import functools
import inspect
import typing
import uuid

from .base import AnswerBtn, BaseDialog, Discussion, Message, Request
from .prompts import PROMPTS


def setting(*, name: str) -> typing.Callable:
    def decorate(func: typing.Callable) -> typing.Callable:
        @functools.wraps(func)
        def wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            return func(*args, **kwargs)

        wrapper.name = name
        wrapper.uuid = str(uuid.uuid4())
        wrapper.is_setting = True

        return wrapper

    return decorate


class SettingsDialog(BaseDialog):
    settings: dict

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.settings = {
            method.uuid: method
            for method_name, method in inspect.getmembers(self, predicate=inspect.ismethod)
            if getattr(method, 'is_setting', False)
        }

    async def get_welcome_message(self) -> Message | None:
        return Message(
            'What do you wish for?',
            buttons=(
                AnswerBtn(name=self._show_templates.name, callback=self._show_templates.uuid),
                AnswerBtn(name=self._show_profiles.name, callback=self._show_profiles.uuid),
            ),
        )

    async def handle(self, request: Request) -> None:
        await request.discussion.answer(Message(content='Choose action'))

    async def handle_callback(self, request: Request) -> None:
        await self.settings[request.callback](request.discussion)

    @setting(name='Check my prompt templates')
    async def _show_templates(self, discussion: Discussion) -> None:
        if not PROMPTS:
            await discussion.answer(Message(content='No prompts available'))

        for prompt in PROMPTS:
            await discussion.answer(
                Message(
                    content=f'**Name:**\n\n{prompt["name"]}\n\n**Text:**\n\n{prompt["text"]}\n```',
                ),
            )

    @setting(name='Check my profiles')
    async def _show_profiles(self, discussion: Discussion) -> None:
        await discussion.answer(Message(content='222'))
