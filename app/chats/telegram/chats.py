import logging
import typing

from ...models.openai.base import BaseLLM
from ...utils.common import escape_markdown
from ..base import AnswerBtn, BaseChat, Message, Request
from .message_aggregator import MessageGroup, TelegramMessageAggregator
from .message_extractor import TelegramMessageExtractor


class TelegramMessageChat(BaseChat):
    _message_aggregator: TelegramMessageAggregator

    def __init__(self, *, message_aggregator: TelegramMessageAggregator) -> None:
        self._message_aggregator = message_aggregator

    async def init(self) -> None:
        await self._message_aggregator.init()

    async def handle(self, request: Request) -> None:
        await request.conversation.set_text_status('Gathering and aggregating data...')
        has_processed_messages = False

        try:
            async for answer in self._message_aggregator.iter_aggregated_messages(
                conversation=request.conversation,
            ):
                await request.conversation.answer(answer)
                has_processed_messages = True
        except Exception as e:
            logging.exception(e)
            await request.conversation.answer(Message(content=f'**ERROR:**\n```\n{escape_markdown(str(e))}\n```'))
        else:
            await request.conversation.answer(Message(
                content=(
                    'Information processing is completed.'
                    if has_processed_messages else
                    'Unfortunately there are no messages to process at the moment.'
                ),
                buttons=(AnswerBtn(name='Repeat?', callback='start_generating'),),
            ))

    async def get_welcome_message(self) -> Message:
        return Message(
            content='Are you ready to start?',
            buttons=(AnswerBtn(name='Yes', callback='start_generating'),),
        )

    async def handle_callback(self, request: Request) -> None:
        await self.handle(request)


def gen_telegram_folder_reader(
    *,
    gpt_model: BaseLLM,
    model_params: dict,
    folder_name: str,
    prompt_for_aggregation: str,
    topics_to_exclude: typing.Sequence[str] = (),
    important_key_words: typing.Sequence[str] = (),
) -> BaseChat:
    topics_to_exclude = set(topics_to_exclude)
    important_key_words = tuple(important_key_words)

    return TelegramMessageChat(
        message_aggregator=TelegramMessageAggregator(
            llm_model=gpt_model,
            model_params=model_params,
            message_extractor=TelegramMessageExtractor(
                folder_name=folder_name,
                filtering=lambda x: x['source']['channel_topic'] not in topics_to_exclude,
                key_words=important_key_words,
            ),
            prompt_for_aggregation=prompt_for_aggregation,
            grouping=lambda x: MessageGroup(
                id=(x['source']['channel_title'], x['source']['channel_topic']),
                titles=(x['source']['channel_title'], x['source']['channel_topic']),
                additional_context={
                    'channel_name': x['source']['channel_title'],
                    'channel_topic': x['source']['channel_topic'],
                },
            ),
        ),
    )
