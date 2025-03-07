import logging

from .base import BaseDialog, DialogError, Message, Request
from ..models.openai.base import Dalle


class DalleDialog(BaseDialog):
    async def handle(self, request: Request) -> None:
        await request.discussion.set_text_status('Generating image...')

        try:
            response = await Dalle.process(request.content)
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e

        await request.discussion.set_text_status('Sending image...')
        await request.discussion.answer(Message(content=f'![Image]({response.url})'))
