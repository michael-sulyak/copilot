import logging
from pprint import pprint

from .base import BaseDialog, DialogError, Message, Request
from .profiles import BaseProfile
from ..memory import BaseMemory
from ..models.openai.base import BaseGPT, GPTMessage
from ..models.openai.constants import GPTRoles, NOTSET
from ..utils.file_processor import FileProcessor


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
        print('History:')
        pprint(self.memory.get_buffer())

        try:
            response = await self.model.process(
                messages=self.memory.get_buffer(),
                temperature=NOTSET if self.model.is_reasoning else self.profile.temperature,
                top_p=NOTSET if self.model.is_reasoning else self.profile.top_p,
                reasoning_effort=self.profile.reasoning_effort if self.model.is_reasoning else NOTSET,
            )
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e

        self.memory.add_message(GPTMessage(role=GPTRoles.ASSISTANT, content=response.content))

        return Message(
            content=response.content,
            duration=response.duration,
            cost=response.cost,
            total_tokens=response.total_tokens,
        )

    async def clear_history(self) -> None:
        self.memory.clear()
