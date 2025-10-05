import logging
import typing

from .base import BaseDialog, DialogError, Message, Request
from .profiles import BaseProfile
from .tools import BaseLLMTool
from ..memory import BaseMemory
from ..models.openai.base import BaseLLM, LLMMessage
from ..models.openai.constants import LLMMessageRoles, NOTSET
from ..utils.file_processor import FileProcessor


class Dialog(BaseDialog):
    profile: BaseProfile
    memory: BaseMemory
    model: BaseLLM
    tools: typing.Sequence[BaseLLMTool]

    def __init__(
        self, *,
        profile: BaseProfile,
        memory: BaseMemory,
        model: BaseLLM,
        files_are_supported: bool = False,
        tools: typing.Sequence[BaseLLMTool] = (),
    ) -> None:
        self.profile = profile
        self.memory = memory
        self.model = model
        self.files_are_supported = files_are_supported
        self.tools = tools

        if context := self.profile.get_context():
            self.memory.add_context(LLMMessage(role=LLMMessageRoles.SYSTEM, content=context))

    async def handle(self, request: Request) -> None:
        attachments = []
        base64_images = []

        if request.attachments:
            for attachment in request.attachments:
                if attachment.is_image:
                    logging.info(f'Image attachment: {attachment.name} ({attachment.mime_type})')
                    base64_images.append(FileProcessor(attachment).to_base64())
                else:
                    logging.info(f'File attachment: {attachment.name} ({attachment.mime_type})')
                    attachments.append(attachment)

        if attachments:
            await request.discussion.set_text_status('Parsing attachments...')

            for attachment in attachments:
                self.memory.add_message(LLMMessage(
                    role=LLMMessageRoles.SYSTEM,
                    content=(
                        f'There has been provided an attachment '
                        f'with name `{attachment.name}` and MIME type `{attachment.mime_type}`.'
                        f'The content of the attachment is as follows:\n'
                        f'{FileProcessor(attachment).to_txt()}'
                    ),
                ))

            await request.discussion.reset_text_status()

        if base64_images and not self.model.has_vision:
            raise DialogError('The models does not support vision.')

        self.memory.add_message(LLMMessage(
            role=LLMMessageRoles.USER,
            content=request.content,
            base64_images=tuple(base64_images),
        ))

        logging.info(f'Count of images: {len(base64_images)}')
        logging.info(f'Count of other attachments: {len(attachments)}')

        await request.discussion.set_text_status(f'Processing via {self.model.showed_model_name}...')
        await request.discussion.answer(await self.handle_via_gpt())

    async def handle_via_gpt(self) -> Message:
        logging.info('History: %s', self.memory.get_buffer())

        params = {}

        if not self.model.is_reasoning:
            if self.profile.temperature is not NOTSET:
                params['temperature'] = self.profile.temperature

            if self.profile.top_p is not NOTSET:
                params['top_p'] = self.profile.top_p

        if self.model.is_reasoning and self.profile.reasoning_effort is not NOTSET:
            params['reasoning_effort'] = self.profile.reasoning_effort

        if self.tools:
            params['tools'] = self.tools

        try:
            response = await self.model.process(
                messages=self.memory.get_buffer(),
                **params,
            )
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e

        content = response.content

        if response.annotations:
            content += f'\n---\n**Sources:**\n{"\n".join(map(lambda x: f"* {x}", response.annotations))}'

        self.memory.add_message(LLMMessage(role=LLMMessageRoles.ASSISTANT, content=content))

        return Message(
            content=content,
            duration=response.duration,
            cost=response.cost,
            total_tokens=response.total_tokens,
        )

    async def clear_history(self) -> None:
        self.memory.clear()
