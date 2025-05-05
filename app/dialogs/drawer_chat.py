import abc
import logging

from ..models.openai.base import BaseDrawer, Dalle, GptImage
from .base import BaseDialog, DialogError, Message, Request


class BaseDrawer(BaseDialog, abc.ABC):
    model: type[BaseDrawer]

    @property
    def files_are_supported(self) -> bool:
        return self.model.has_vision

    async def handle(self, request: Request) -> None:
        await request.discussion.set_text_status('Processing input...')

        images = []

        if self.model.has_vision and request.attachments:
            for attachment in request.attachments:
                if attachment.is_image:
                    logging.info(f'Image attachment: {attachment.name} ({attachment.mime_type})')
                    images.append(attachment)
                else:
                    raise DialogError(f'File "{attachment.name}" is not an image.')

        try:
            if images:
                await request.discussion.set_text_status('Editing image...')
                response = await self.model.edit(request.content, images=images)
            else:
                await request.discussion.set_text_status('Generating image...')
                response = await self.model.create(request.content)
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e

        await request.discussion.set_text_status('Sending image...')
        await request.discussion.answer(Message(content=f'![Image]({response.url})'))


class DalleDialog(BaseDrawer):
    model = Dalle


class GptImageDialog(BaseDrawer):
    model = GptImage
