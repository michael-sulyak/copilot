import logging

from ..memory import BaseMemory
from ..models.openai.base import BaseGPT, GPTMessage
from ..models.openai.constants import NOTSET, GPTRoles
from ..utils.file_processor import FileProcessor
from .base import BaseDialog, DialogError, Message, Request
from .profiles import BaseProfile


class Dialog(BaseDialog):
    profile: BaseProfile
    memory: BaseMemory
    model: BaseGPT

    def __init__(
        self, *,
        profile: BaseProfile,
        memory: BaseMemory,
        model: BaseGPT,
        files_are_supported: bool = False,
    ) -> None:
        self.profile = profile
        self.memory = memory
        self.model = model
        self.files_are_supported = files_are_supported

        if context := self.profile.get_context():
            self.memory.add_context(GPTMessage(role=GPTRoles.SYSTEM, content=context))

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

        for attachment in attachments:
            self.memory.add_message(GPTMessage(
                role=GPTRoles.SYSTEM,
                content=(
                    f'There has been provided an attachment '
                    f'with name `{attachment.name}` and MIME type `{attachment.mime_type}`.'
                    f'The content of the attachment is as follows:\n'
                    f'{FileProcessor(attachment).to_txt()}'
                ),
            ))

        if base64_images and not self.model.has_vision:
            raise DialogError('The models does not support vision.')

        self.memory.add_message(GPTMessage(
            role=GPTRoles.USER,
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

        if not self.model.is_reasoning and not self.model.is_searching:
            if self.profile.temperature is not NOTSET:
                params['temperature'] = self.profile.temperature

            if self.profile.top_p is not NOTSET:
                params['top_p'] = self.profile.top_p

                if self.profile.top_p is not NOTSET:
                    params['top_p'] = self.profile.top_p

        if self.model.is_reasoning:
            params['reasoning_effort'] = self.profile.reasoning_effort

        try:
            response = await self.model.process(
                messages=self.memory.get_buffer(),
                **params,
            )
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e

        self.memory.add_message(GPTMessage(role=GPTRoles.ASSISTANT, content=response.content))

        content = response.content

        if self.model.is_searching and response.annotations:
            additional_info = '\n\n---\n\n**Sources:**\n\n'

            for annotation in response.annotations:
                additional_info += f'* [{annotation["url_citation"]["title"]}])({annotation["url_citation"]['url']})\n'

            content += additional_info

        return Message(
            content=content,
            duration=response.duration,
            cost=response.cost,
            total_tokens=response.total_tokens,
        )

    async def clear_history(self) -> None:
        self.memory.clear()
