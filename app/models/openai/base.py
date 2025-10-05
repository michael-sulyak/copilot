import abc
import asyncio
import base64
import dataclasses
import datetime
import json
import logging
import typing
from contextlib import ExitStack
from functools import cached_property

import openai
import yaml
from openai import APIConnectionError, AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI
from openai.types import Reasoning
from openai.types.responses import (
    Response,
    ResponseFormatTextJSONSchemaConfigParam,
    ResponseFunctionToolCall,
    ResponseOutputText,
    ResponseTextConfigParam,
)
from pydantic import BaseModel

from .constants import LLMContentTypes, LLMMessageRoles, LLMToolParamTypes, NOTSET
from .utils import num_tokens_from_messages, prepare_llm_response_content
from ... import config
from ...utils.common import chunk_generator, gen_optimized_json
from ...utils.local_file_storage import File


@dataclasses.dataclass(frozen=True)
class OpenAiConfig:
    base_url: str | None = None
    api_key: str | None = None
    api_version: str | None = None
    azure_endpoint: str | None = None
    azure_deployment: str | None = None

    @property
    def is_available(self) -> bool:
        has_openai_credentials = False
        has_custom_credentials = False

        if self.azure_endpoint:
            has_custom_credentials = bool(
                self.api_key
                and self.api_version
                and self.azure_deployment,
            )
        else:
            has_openai_credentials = bool(
                self.api_key
                and not self.api_version
                and not self.azure_deployment,
            )

        return has_openai_credentials or has_custom_credentials

    @cached_property
    def client(self) -> AsyncAzureOpenAI | AsyncOpenAI:
        if self.azure_endpoint:
            client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                azure_deployment=self.azure_deployment,
                api_version=self.api_version,
                api_key=self.api_key,
            )
        else:
            client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )

        return client


@dataclasses.dataclass(frozen=True)
class LLMResponse:
    content: str | None
    parsed_content: BaseModel | None
    tool_calls: list['LLMToolCall']
    duration: datetime.timedelta
    cost: float
    total_tokens: int
    original_response: Response
    annotations: tuple[str, ...] | None = None
    generated_at: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now,
    )

    def to_llm_message(self) -> 'LLMMessage':
        if self.tool_calls:
            return LLMMessage(
                role=LLMMessageRoles.FUNCTION,
                name=self.tool_calls.name,
                content=json.dumps(self.tool_calls.args),
            )

        return LLMMessage(
            role=LLMMessageRoles.ASSISTANT,
            content=self.content,
        )


@dataclasses.dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str
    base64_images: tuple[str, ...] | None = None
    name: str | None = None
    _cached_dump: dict = dataclasses.field(
        default_factory=dict,
    )

    def dump(self) -> dict:
        if 'dump' in self._cached_dump:
            return self._cached_dump['dump']

        assert self.name is None or self.role == LLMMessageRoles.FUNCTION

        if self.role == LLMMessageRoles.FUNCTION:
            result = {
                'role': self.role,
                'content': self.content,
                'name': self.name,
            }
        elif self.base64_images:
            result = {
                'role': self.role,
                'content': [
                    {
                        'type': LLMContentTypes.TEXT,
                        'text': self.content,
                    },
                    *(
                        {
                            'type': LLMContentTypes.IMAGE,
                            'image_url': base64_image,
                            'detail': 'high',
                        }
                        for base64_image in self.base64_images
                    ),
                ],
            }
        else:
            result = {
                'role': self.role,
                'content': self.content,
            }

        self._cached_dump['dump'] = result

        return result


@dataclasses.dataclass(frozen=True)
class LLMToolParam:
    name: str
    type: str
    description: str
    enum: tuple[str, ...] | None = None
    required: bool = False


@dataclasses.dataclass(frozen=True)
class LLMToolCall:
    name: str
    args: dict[str, typing.Any] | None
    raw_args: str | None
    is_valid: bool


class BaseLLMTool(abc.ABC):
    name: str

    @abc.abstractmethod
    def dump(self) -> dict[str, typing.Any]:
        pass


@dataclasses.dataclass(frozen=True)
class FunctionLLMTool(BaseLLMTool):
    name: str
    description: str
    parameters: tuple[LLMToolParam, ...]
    func: typing.Callable | None = None

    def dump(self) -> dict:
        properties = {}
        required = []

        for parameter in self.parameters:
            properties[parameter.name] = {
                'type': parameter.type,
                'description': parameter.description,
            }

            if parameter.enum is not None:
                properties[parameter.name]['enum'] = list(parameter.enum)

            if parameter.required:
                required.append(parameter.name)

        return {
            'name': self.name,
            'type': 'function',
            'description': self.description,
            'parameters': {
                'type': LLMToolParamTypes.OBJECT,
                'properties': properties,
                'required': required,
            },
        }


@dataclasses.dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: typing.Sequence[LLMMessage]
    temperature: float | NOTSET = NOTSET
    top_p: float | NOTSET = NOTSET
    response_format: BaseModel | NOTSET = NOTSET
    tools: tuple[FunctionLLMTool, ...] | NOTSET = NOTSET
    reasoning_effort: str | NOTSET = NOTSET

    def dump(self) -> dict:
        result = {
            'model': self.model,
            'input': [
                message.dump()
                for message in self.messages
            ],
        }

        if self.temperature is not NOTSET:
            result['temperature'] = self.temperature

        if self.top_p is not NOTSET:
            result['top_p'] = self.top_p

        if self.response_format is not NOTSET:
            json_schema = self.response_format.model_json_schema()
            json_schema['additionalProperties'] = False

            result['text'] = ResponseTextConfigParam(format=ResponseFormatTextJSONSchemaConfigParam(
                name=self.response_format.__name__,
                type='json_schema',
                description=self.response_format.__doc__ or '',
                schema=json_schema,
                strict=True,
            ))

        if self.reasoning_effort is not NOTSET:
            result['reasoning'] = Reasoning(effort=self.reasoning_effort)

        if self.tools is not NOTSET:
            result['tools'] = [
                function.dump()
                for function in self.tools
            ]

        return result


class BaseLLM:
    showed_model_name: str
    model_name: str
    max_tokens: int
    input_price: float
    output_price: float
    min_response_volume = 0.1
    max_retries: int = 3
    config: OpenAiConfig
    has_vision: bool = False
    is_reasoning: bool = False

    @classmethod
    async def process(cls,
                      messages: typing.Sequence[LLMMessage], *,
                      temperature: float | NOTSET = NOTSET,
                      top_p: float | NOTSET = NOTSET,
                      check_total_length: bool = False,
                      tools: tuple[BaseLLMTool, ...] | NOTSET = NOTSET,
                      response_format: type[BaseModel] | NOTSET = NOTSET,
                      reasoning_effort: str | NOTSET = NOTSET,
                      _count_of_repeats: int = 0) -> LLMResponse:
        started_at = datetime.datetime.now()

        llm_request = LLMRequest(
            model=cls.model_name,
            temperature=temperature,
            top_p=top_p,
            messages=messages,
            response_format=response_format,
            tools=tools,
            reasoning_effort=reasoning_effort,
        )

        logging.info('Send messages to %s:', cls.model_name)
        logging.info(messages)

        count_of_tokens = cls.count_tokens(messages)

        logging.info('Expected count of tokens: %s', count_of_tokens)

        if not cls.has_enough_tokens_to_answer(count_of_tokens):
            raise openai.OpenAIError('There are too few tokens left to answer.')

        response = None

        for attempt in range(1, cls.max_retries + 1):
            backoff = 2 ** attempt

            try:
                response = await cls.config.client.responses.create(**llm_request.dump())
            except openai.RateLimitError as e:
                logging.warning(e)

                if attempt >= cls.max_retries:
                    raise

                logging.warning(e)

                await asyncio.sleep(backoff)
            except APIConnectionError as e:
                logging.warning(e)

                if attempt >= cls.max_retries:
                    raise

                logging.warning(e)

                await asyncio.sleep(backoff)
            else:
                break

        logging.info('Response: %s', response)

        if check_total_length and response.usage.total_tokens >= cls.max_tokens:
            raise openai.OpenAIError('Rate limit')

        processing_time = datetime.datetime.now() - started_at
        cost = (
            response.usage.input_tokens * cls.input_price
            + response.usage.output_tokens * cls.output_price
        )

        logging.info('Processing time: %s', processing_time)
        logging.info('Cost: %s$', round(cost, 6))

        llm_tool_calls = []
        content = None
        target_response_output = response.output[-1]

        annotations = None

        if isinstance(target_response_output, ResponseFunctionToolCall):
            tool_call = target_response_output

            try:
                func_args = json.loads(tool_call.arguments)
            except json.JSONDecodeError as e:
                logging.warning(e)

                call_is_valid = False
                func_args = None
            else:
                call_is_valid = True

            llm_tool_calls.append(LLMToolCall(
                name=tool_call.name,
                args=func_args,
                raw_args=tool_call.arguments,
                is_valid=call_is_valid,
            ))
        elif target_response_output.content and isinstance(target_response_output.content[0], ResponseOutputText):
            annotations = target_response_output.content[0].annotations or None

            if annotations:
                annotations = tuple(annotation.url for annotation in annotations)

            content = prepare_llm_response_content(target_response_output.content[0].text)

        if response_format is NOTSET:
            parsed_content = None
        else:
            parsed_content = response_format.model_validate_json(content)

        return LLMResponse(
            content=content,
            parsed_content=parsed_content,
            tool_calls=llm_tool_calls,
            duration=processing_time,
            cost=cost,
            total_tokens=response.usage.total_tokens,
            original_response=response,
            annotations=annotations,
        )

    @classmethod
    async def execute(
        cls,
        *,
        messages: typing.Sequence[LLMMessage],
        tools: tuple[FunctionLLMTool, ...],
        temperature: float | NOTSET = NOTSET,
        top_p: float | NOTSET = NOTSET,
        reasoning_effort: str | NOTSET = NOTSET,
        response_format: type[BaseModel] | NOTSET = NOTSET,
        max_steps: int = 8,
        check_total_length: bool = False,
        stop_when: typing.Callable[[LLMToolCall, typing.Any], bool] | None = None,
    ) -> LLMResponse:
        """
        Runs the model-tool loop:
        - calls the model
        - executes tool calls via `executors`
        - feeds back function outputs
        - repeats until assistant returns text or `stop_when` says to stop
        Returns a final LLMResponse with aggregated cost/tokens and the last model message as content.
        """

        started_at = datetime.datetime.now()
        total_cost = 0
        total_tokens = 0
        tool_trace: list[LLMToolCall] = []
        history: list[LLMMessage] = list(messages)
        last_raw_response: Response | None = None
        executors_map = {
            tool.name: tool.func
            for tool in tools
        }

        for step in range(1, max_steps + 1):
            current_tokens = cls.count_tokens(history)
            if not cls.has_enough_tokens_to_answer(current_tokens):
                raise openai.OpenAIError('There are too few tokens left to answer.')

            step_response = await cls.process(
                messages=tuple(history),
                temperature=temperature,
                top_p=top_p,
                check_total_length=check_total_length,
                tools=tools,
                reasoning_effort=reasoning_effort,
            )

            total_cost += step_response.cost
            total_tokens += step_response.total_tokens
            last_raw_response = step_response.original_response

            if step_response.tool_calls:
                for call in step_response.tool_calls:
                    tool_trace.append(call)

                    history.append(LLMMessage(
                        role=LLMMessageRoles.ASSISTANT,
                        content=f'Execute tool: "{call.name}":\nArguments:\n{gen_optimized_json(call.args)}',
                    ))

                    exec_fn = executors_map.get(call.name)
                    if not call.is_valid or exec_fn is None:
                        # Tell the model we couldn't execute so it can self-correct
                        history.append(LLMMessage(
                            role=LLMMessageRoles.SYSTEM,
                            content=f'ERROR: Tool "{call.name}" unavailable or arguments invalid. raw_args={call.raw_args}',
                        ))
                        continue

                    try:
                        maybe_coro = exec_fn(call)
                        result_value = await maybe_coro if asyncio.iscoroutine(maybe_coro) else maybe_coro
                    except Exception:
                        logging.exception(f'Exception while executing tool "{call.name}"')
                        result_value = f'ERROR: Unexpected exception while executing tool "{call.name}"'

                    result_content = f'Executed tool: "{call.name}":\nResult:\n{result_value}'

                    history.append(LLMMessage(
                        role=LLMMessageRoles.SYSTEM,
                        content=result_content,
                    ))

                    if stop_when and stop_when(call, result_value):
                        final_turn = await cls.process(
                            messages=tuple(history),
                            temperature=temperature,
                            top_p=top_p,
                            check_total_length=check_total_length,
                            tools=tools,
                            response_format=response_format,
                            reasoning_effort=reasoning_effort,
                        )
                        total_cost += final_turn.cost
                        total_tokens += final_turn.total_tokens

                        return LLMResponse(
                            content=final_turn.content,
                            parsed_content=final_turn.parsed_content if response_format is not NOTSET else None,
                            tool_calls=tool_trace,
                            duration=datetime.datetime.now() - started_at,
                            cost=total_cost,
                            total_tokens=total_tokens,
                            original_response=final_turn.original_response,
                        )

                continue
            else:
                history.append(LLMMessage(
                    role=LLMMessageRoles.ASSISTANT,
                    content=step_response.content,
                ))

            if step_response.content is not None:
                parsed_content = None
                if response_format is not NOTSET:
                    parsed_content = response_format.model_validate_json(step_response.content)

                return LLMResponse(
                    content=step_response.content,
                    parsed_content=parsed_content,
                    tool_calls=tool_trace,
                    duration=datetime.datetime.now() - started_at,
                    cost=total_cost,
                    total_tokens=total_tokens,
                    original_response=last_raw_response or step_response.original_response,
                )

        return LLMResponse(
            content=None,
            parsed_content=None,
            tool_calls=tool_trace,
            duration=datetime.datetime.now() - started_at,
            cost=total_cost,
            total_tokens=total_tokens,
            original_response=last_raw_response,
        )

    @classmethod
    def count_tokens(cls, messages: typing.Sequence[LLMMessage]) -> int:
        return num_tokens_from_messages(
            tuple(
                message.dump()
                for message in messages
            ),
            model=cls.model_name,
            default_to_cl100k=True,
        )

    @classmethod
    def count_tokens_in_text(cls, text: str) -> int:
        return cls.count_tokens((LLMMessage(role=LLMMessageRoles.USER, content=text),))

    @classmethod
    def has_enough_tokens_to_answer(cls, count_of_tokens: int, *, min_response_volume: float | None = None) -> bool:
        if min_response_volume is None:
            min_response_volume = cls.min_response_volume

        return count_of_tokens + cls.max_tokens * min_response_volume <= cls.max_tokens


OPENAI_CONFIG = OpenAiConfig(
    api_key=config.OPENAI_API_KEY,
    base_url=config.OPENAI_BASE_URL,
)


def load_llm_models_config() -> typing.Generator:
    with open(config.MODELS_PATH) as file:
        models_config = yaml.safe_load(file)

    model_infos = models_config.get('gpt_models', [])

    for model_info in model_infos:
        model_info['input_price'] = float(model_info['input_price'])
        model_info['output_price'] = float(model_info['output_price'])
        yield type(model_info['showed_model_name'], (BaseLLM,), {**model_info, 'config': OPENAI_CONFIG})


AVAILABLE_LLM_MODELS = tuple(load_llm_models_config())
AVAILABLE_LLM_MODELS_MAP = {
    model.showed_model_name: model
    for model in AVAILABLE_LLM_MODELS
}


@dataclasses.dataclass
class EmbeddingResponse:
    vectors: list[list[float]]
    cost: float


class Embedding:
    model_name = 'text-embedding-3-small'
    max_tokens = 8191
    price = 0.02 / 1_000_000
    config = OPENAI_CONFIG
    max_input = 16

    @classmethod
    async def process(cls, texts: typing.Sequence[str]) -> EmbeddingResponse:
        for text in texts:
            count_of_tokens = cls.count_tokens_in_text(text)

            logging.info(f'{count_of_tokens = }')

            if count_of_tokens >= cls.max_tokens:
                raise openai.OpenAIError('Rate limit')

        embedding_response = EmbeddingResponse(
            vectors=[],
            cost=0,
        )

        for chunk in chunk_generator(texts, chunk_size=cls.max_input):
            response = await cls.config.client.embeddings.create(
                input=list(chunk),
                model=cls.model_name,
            )

            embedding_response.vectors.extend(map(lambda x: x['embedding'], response['data']))
            embedding_response.cost += response['usage']['total_tokens'] * cls.price

        return embedding_response

    @classmethod
    def count_tokens_in_text(cls, text: str) -> int:
        return num_tokens_from_messages(
            [{'content': text}],
            model=cls.model_name,
            default_to_cl100k=True,
        )


@dataclasses.dataclass
class DrawerResponse:
    url: str | None = None
    data: bytes | None = None
    cost: float | None = None


class BaseDrawer(abc.ABC):
    model_name: str
    input_price: float
    output_price: float
    max_prompt_length: int
    size: str
    has_vision: bool
    config: OpenAiConfig

    @classmethod
    async def create(cls, text: str) -> DrawerResponse:
        if len(text) >= cls.max_prompt_length:
            raise openai.OpenAIError(f'The maximum length is {cls.max_prompt_length} characters')

        response = await cls.config.client.images.generate(
            prompt=text,
            n=1,
            model=cls.model_name,
            quality='high',
            size=cls.size,
        )

        if response.data[0].url is None:
            image_base64 = response.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)
        else:
            image_bytes = None

        cost = 0
        if response.usage:
            cost += response.usage.input_tokens * cls.input_price
            cost += response.usage.output_tokens * cls.output_price

        return DrawerResponse(
            url=response.data[0].url,
            data=image_bytes,
            cost=cost,
        )

    @classmethod
    async def edit(cls, text: str, *, images: typing.Sequence[File]) -> DrawerResponse:
        if len(text) >= cls.max_prompt_length:
            raise openai.OpenAIError(f'The maximum length is {cls.max_prompt_length} characters')

        with ExitStack() as stack:
            opened_images = [stack.enter_context(image.open()) for image in images]

            response = await cls.config.client.images.edit(
                prompt=text,
                n=1,
                model=cls.model_name,
                quality='high',
                size=cls.size,
                image=opened_images,
            )

        if response.data[0].url is None:
            image_base64 = response.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)
        else:
            image_bytes = None

        return DrawerResponse(
            url=response.data[0].url,
            data=image_bytes,
        )


class GPTImage(BaseDrawer):
    model_name = 'gpt-image-1'
    input_price = 10 / 1_000_000
    output_price = 40 / 1_000_000
    max_prompt_length = 10_000
    size = '1536x1024'
    has_vision = True
    config = OPENAI_CONFIG


@dataclasses.dataclass
class TranscriberResponse:
    text: str
    cost: float


class BaseTranscriber(abc.ABC):
    model_name: str
    input_price: float
    output_price: float
    config: OpenAiConfig

    @classmethod
    async def process(cls, audio: typing.BinaryIO) -> TranscriberResponse:
        response = await cls.config.client.audio.transcriptions.create(
            model=cls.model_name,
            file=audio,
            response_format='json',
        )

        return TranscriberResponse(
            text=response.text,
            cost=0,
        )


class Gpt4oTranscriber(BaseTranscriber):
    model_name = 'gpt-4o-transcribe'
    input_price = 2.5 / 1_000_000
    output_price = 10 / 1_000_000
    config = OPENAI_CONFIG


@dataclasses.dataclass(frozen=True)
class ModeratorResponse:
    is_flagged: bool


class BaseModerator(abc.ABC):
    model_name: str
    config: OpenAiConfig

    @classmethod
    async def process(cls, text: str) -> ModeratorResponse:
        response = await cls.config.client.moderations.create(
            model=cls.model_name,
            input=text,
        )

        return ModeratorResponse(
            is_flagged=response.results[0].flagged,
        )


class GPTModerator(BaseModerator):
    model_name = 'omni-moderation-latest'
