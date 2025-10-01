import abc
import dataclasses
import logging
import typing
from functools import cached_property

from ...models.openai.base import BaseLLM, LLMMessage, LLMResponse
from ...models.openai.constants import LLMMessageRoles
from ...utils.common import escape_markdown, gen_optimized_json
from ...utils.text_processing import remove_triple_backticks
from ..base import AnswerBtn, Discussion, Message
from .message_extractor import TelegramMessageExtractor


@dataclasses.dataclass
class MessageGroup(abc.ABC):
    id: typing.Any
    titles: tuple[str, ...]
    additional_context: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MessageGroup) and self.id == other.id


class TelegramMessageAggregator:
    _message_extractor: TelegramMessageExtractor
    _unprocessed_message_iter: typing.Iterator | None = None
    _llm_model: BaseLLM
    _model_params: dict
    _is_inited: bool
    _prompt_for_aggregation: str
    _grouping: typing.Callable | None

    def __init__(
        self, *,
        llm_model: BaseLLM,
        model_params: dict,
        message_extractor: TelegramMessageExtractor,
        prompt_for_aggregation: str,
        grouping: typing.Callable | None = None,
    ) -> None:
        self._message_extractor = message_extractor
        self._llm_model = llm_model
        self._model_params = model_params
        self._is_inited = False
        self._prompt_for_aggregation = prompt_for_aggregation
        self._grouping = grouping
        self._unprocessed_message_iter: typing.Iterator | None = None

    async def init(self) -> None:
        if not self._is_inited:
            await self._message_extractor.init()
            self._is_inited = True

    @cached_property
    def _max_tokens_per_message(self) -> float:
        return (
            self._llm_model.max_tokens // 2 - self._llm_model.count_tokens_in_text(
            self._prompt_for_aggregation)
        ) * 0.8

    async def iter_aggregated_messages(self, *, discussion: Discussion) -> typing.AsyncIterator[Message]:
        logging.info('Start iterating over compressed messages...')
        messages_iter = self._iter_messages(discussion=discussion)
        chunk, number_of_tokens, prev_group = [], 0, None

        async for message in messages_iter:
            prepared_message = self._prepare_message(message)
            number_of_tokens_in_text = self._llm_model.count_tokens_in_text(gen_optimized_json(prepared_message))
            group = self._grouping(message) if self._grouping else None

            if prev_group is None:
                prev_group = group

            is_the_same_group = group == prev_group

            if number_of_tokens + number_of_tokens_in_text <= self._max_tokens_per_message and is_the_same_group:
                chunk.append(prepared_message)
                number_of_tokens += number_of_tokens_in_text
            else:
                if chunk:
                    await discussion.set_text_status(f'Processing chunk ({len(chunk)} messages)...')
                    yield await self._process_chunk(chunk, prev_group)

                chunk, number_of_tokens = [prepared_message], number_of_tokens_in_text
                prev_group = group

        if chunk:
            await discussion.set_text_status(f'Processing last chunk ({len(chunk)} messages)...')
            yield await self._process_chunk(chunk, prev_group)

    async def _iter_messages(self, *, discussion: Discussion) -> typing.AsyncIterator[dict[str, typing.Any]]:
        if self._unprocessed_message_iter is not None:
            unprocessed_messages_iter = self._unprocessed_message_iter
            self._unprocessed_message_iter = None

            for message in unprocessed_messages_iter:
                yield message

        async for message in self._message_extractor.iter_messages(discussion=discussion):
            yield message

    async def _process_chunk(self, chunk: list, group: MessageGroup) -> Message:
        try:
            content = self._generate_content(chunk, group)
            response = await self._process_via_model(content)
            return self._prepare_answer_for_llm_response(group, response)
        except Exception as e:
            logging.exception(e)
            self._unprocessed_message_iter = iter(chunk)
            return self._prepare_answer_for_error(e)

    def _generate_content(self, data: list[dict], group: MessageGroup) -> str:
        return self._prompt_for_aggregation.format(posts=gen_optimized_json(data), **group.additional_context)

    @staticmethod
    def _prepare_message(message: dict[str, typing.Any]) -> dict[str, typing.Any]:
        text_size_limit = 3_000
        text = message['text']

        return {
            'text': f'{text[:text_size_limit]}...' if len(text) > text_size_limit else text,
            'source': message['source']['url'],
            'author': message['author'],
        }

    @staticmethod
    def _prepare_answer_for_llm_response(group: MessageGroup | None, llm_response: LLMResponse) -> Message:
        content = remove_triple_backticks(llm_response.content)

        if group:
            prefix = ''.join(
                f'{"#" * (i + 1)} {escape_markdown(str(item))}\n'
                for i, item in enumerate(group.titles)
                if item is not None
            )
            content = f'{prefix}---\n\n{content}'

        return Message(
            content=content,
            duration=llm_response.duration,
            cost=llm_response.cost,
            total_tokens=llm_response.total_tokens,
        )

    @staticmethod
    def _prepare_answer_for_error(exception: Exception) -> Message:
        return Message(
            content=f'**ERROR:**\n```\n{escape_markdown(str(exception))}\n```\n\nDo you want to repeat?',
            buttons=(AnswerBtn(name='Yes', callback='send_news'),),
        )

    async def _process_via_model(self, content: str) -> LLMResponse:
        return await self._llm_model.process(
            messages=(LLMMessage(role=LLMMessageRoles.USER, content=content),),
            check_total_length=True,
            **self._model_params,
        )
