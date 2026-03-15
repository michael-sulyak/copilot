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

import httpx
import openai
import yaml
from openai import APIConnectionError, AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI
from openai.types import Reasoning
from openai.types.responses import (
    Response,
    ResponseFormatTextJSONSchemaConfigParam,
    ResponseFunctionToolCall,
    ResponseOutputMessage, ResponseOutputText,
    ResponseTextConfigParam, ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails
from pydantic import BaseModel

from .constants import LLMContentTypes, LLMMessageRoles, LLMToolParamTypes, NOTSET
from .utils import (
    format_tool_chat_message, get_iter_for_background_llm_task_processing, num_tokens_from_messages,
    prepare_llm_response_content,
    process_llm_request_via_old_api, serialize_tool_output,
)
from ... import config
from ...utils.common import chunk_generator, gen_optimized_json
from ...utils.local_file_storage import File


@dataclasses.dataclass(frozen=True)
class ApiConnectionConfig:
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
        timeout = httpx.Timeout(
            timeout=datetime.timedelta(minutes=30).total_seconds(),
            connect=datetime.timedelta(seconds=30).total_seconds(),
        )

        if self.azure_endpoint:
            client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                azure_deployment=self.azure_deployment,
                api_version=self.api_version,
                api_key=self.api_key,
                timeout=timeout,
            )
        else:
            client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=timeout,
            )

        return client


@dataclasses.dataclass(frozen=True)
class LLMResponse:
    content: str | None
    parsed_content: BaseModel | None
    tool_calls: list['LLMFunctionCall']
    duration: datetime.timedelta
    cost: float
    total_tokens: int
    original_response: Response
    annotations: tuple[str, ...] | None = None
    generated_at: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now,
    )


class BaseLLMMessage(abc.ABC):
    @abc.abstractmethod
    def dump(self) -> dict:
        pass


@dataclasses.dataclass(frozen=True)
class LLMMessage(BaseLLMMessage):
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
class LLMFunctionCall(BaseLLMMessage):
    name: str
    args: dict[str, typing.Any] | None
    raw_args: str | None
    is_valid: bool
    call_id: str | None = None
    _cached_dump: dict = dataclasses.field(
        default_factory=dict,
    )

    def dump(self) -> dict:
        if 'dump' in self._cached_dump:
            return self._cached_dump['dump']

        result = {
            'type': LLMContentTypes.FUNCTION_CALL,
            'call_id': self.call_id,
            'name': self.name,
            'arguments': self.raw_args,
        }

        self._cached_dump['dump'] = result

        return result


@dataclasses.dataclass(frozen=True)
class LLMFunctionCallOutput(BaseLLMMessage):
    call_id: str | None = None
    output: str | None = None
    _cached_dump: dict = dataclasses.field(
        default_factory=dict,
    )

    def dump(self) -> dict:
        if 'dump' in self._cached_dump:
            return self._cached_dump['dump']

        result = {
            'type': LLMContentTypes.FUNCTION_CALL_OUTPUT,
            'call_id': self.call_id,
            'output': self.output,
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
    items: typing.Optional['LLMToolParams'] = None


@dataclasses.dataclass(frozen=True)
class LLMToolParams:
    type: str = LLMToolParamTypes.OBJECT
    items: typing.Self | None = None
    parameters: tuple[LLMToolParam, ...] | None = None

    def dump(self) -> dict:
        result: dict[str, typing.Any] = {'type': self.type}

        if self.type == LLMToolParamTypes.OBJECT:
            result['properties'] = {}
            result['required'] = []

            if self.parameters:
                for parameter in self.parameters:
                    result['properties'][parameter.name] = {
                        'type': parameter.type,
                        'description': parameter.description,
                    }

                    if parameter.enum is not None:
                        result['properties'][parameter.name]['enum'] = list(parameter.enum)

                    if parameter.items is not None:
                        result['properties'][parameter.name]['items'] = parameter.items.dump()

                    if parameter.required:
                        result['required'].append(parameter.name)

        return result


class BaseLLMTool(abc.ABC):
    name: str

    @abc.abstractmethod
    def dump(self) -> dict[str, typing.Any]:
        pass


@dataclasses.dataclass(frozen=True)
class FunctionLLMTool(BaseLLMTool):
    name: str
    description: str
    parameters: tuple[LLMToolParam, ...] | LLMToolParams
    func: typing.Callable | None = None

    def dump(self) -> dict:
        parameters = self.parameters

        if not isinstance(self.parameters, LLMToolParams):
            parameters = LLMToolParams(parameters=parameters)

        return {
            'name': self.name,
            'type': 'function',
            'description': self.description,
            'parameters': parameters.dump(),
        }


@dataclasses.dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: typing.Sequence[BaseLLMMessage]
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
                tool.dump()
                for tool in self.tools
            ]

        return result


class BaseLLM:
    showed_model_name: str
    model_name: str
    max_tokens: int
    input_price: float
    output_price: float
    min_response_volume = 0.05
    max_retries: int = 8
    config: ApiConnectionConfig
    has_vision: bool = False
    is_reasoning: bool = False
    use_old_api: bool = False
    delay_for_status_checking: float = 0.5
    clean_responses: bool | None = None
    _background_tasks: set = set()

    @classmethod
    async def process(cls,
                      messages: typing.Sequence[BaseLLMMessage], *,
                      temperature: float | NOTSET = NOTSET,
                      top_p: float | NOTSET = NOTSET,
                      check_total_length: bool = True,
                      tools: tuple[BaseLLMTool, ...] | NOTSET = NOTSET,
                      response_format: type[BaseModel] | NOTSET = NOTSET,
                      reasoning_effort: str | NOTSET = NOTSET,
                      use_background_processing: bool = True,
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

        logging.info(
            'Expected count of tokens for input: %s (%s%%)',
            count_of_tokens,
            round(count_of_tokens / cls.max_tokens * 100, 2),
        )

        if check_total_length and not cls.has_enough_tokens_to_answer(count_of_tokens):
            raise openai.OpenAIError('There are too few tokens left to answer.')

        if cls.use_old_api:
            response = await cls._make_raw_request(
                lambda: process_llm_request_via_old_api(llm=cls, llm_request=llm_request),
            )
            use_background_processing = False
        else:
            response = await cls._make_raw_request(
                lambda: cls.config.client.responses.create(**llm_request.dump(), background=use_background_processing),
            )

        if use_background_processing:
            async def _check_response() -> None:
                nonlocal response

                iter_for_delay = get_iter_for_background_llm_task_processing()

                while response.status in {'queued', 'in_progress'}:
                    logging.info(f'Current status of background request: "{response.status}"')
                    await asyncio.sleep(next(iter_for_delay))
                    response = await cls.config.client.responses.retrieve(response.id)

                logging.info(f'Last status of background request: "{response.status}"')

            await cls._make_raw_request(_check_response)

        logging.info('Response: %s', response)

        if response.usage is None:
            logging.warning('No usage info available.')
            response.usage = ResponseUsage(
                total_tokens=0,
                input_tokens=0,
                output_tokens=0,
                input_tokens_details=InputTokensDetails(cached_tokens=0),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            )

        processing_time = datetime.datetime.now() - started_at
        cost = response.usage and (
            response.usage.input_tokens * cls.input_price
            + response.usage.output_tokens * cls.output_price
        )

        logging.info('Processing time: %s', processing_time)
        logging.info('Cost: %s$', round(cost, 6))

        llm_tool_calls: list[LLMFunctionCall] = []
        content_parts: list[str] = []
        annotation_urls: list[str] = []

        for output_item in response.output:
            if isinstance(output_item, ResponseFunctionToolCall):
                try:
                    func_args = json.loads(output_item.arguments)
                except json.JSONDecodeError as e:
                    logging.warning(e)
                    call_is_valid = False
                    func_args = None
                else:
                    call_is_valid = True

                llm_tool_calls.append(LLMFunctionCall(
                    name=output_item.name,
                    args=func_args,
                    raw_args=output_item.arguments,
                    is_valid=call_is_valid,
                    call_id=output_item.call_id,
                ))
                continue

            if isinstance(output_item, ResponseOutputMessage):
                for content_item in output_item.content or []:
                    if not isinstance(content_item, ResponseOutputText):
                        continue

                    if content_item.annotations:
                        annotation_urls.extend(
                            annotation.url
                            for annotation in content_item.annotations
                            if getattr(annotation, 'url', None)
                        )

                    prepared_text = prepare_llm_response_content(content_item.text)
                    if prepared_text:
                        content_parts.append(prepared_text)

        content = '\n'.join(content_parts) or None
        annotations = tuple(dict.fromkeys(annotation_urls)) or None

        if response_format is NOTSET:
            parsed_content = None
        else:
            parsed_content = response_format.model_validate_json(content)

        if cls.clean_responses or (cls.clean_responses is None and config.CLEAN_RESPONSES):
            task = asyncio.create_task(cls.config.client.responses.delete(response.id))
            cls._background_tasks.add(task)
            task.add_done_callback(cls._background_tasks.discard)

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
        messages: typing.Sequence[BaseLLMMessage],
        tools: tuple[FunctionLLMTool, ...],
        temperature: float | NOTSET = NOTSET,
        top_p: float | NOTSET = NOTSET,
        reasoning_effort: str | NOTSET = NOTSET,
        response_format: type[BaseModel] | NOTSET = NOTSET,
        max_steps: int = 8,
        check_total_length: bool = True,
        stop_when: typing.Callable[[LLMFunctionCall, typing.Any], bool] | None = None,
        logger: typing.Callable | None = None,
    ) -> LLMResponse:
        """
        Runs the model-tool loop:
        - calls the model
        - executes tool calls
        - appends native function_call_output items
        - repeats until assistant returns text or `stop_when` says to stop

        For Responses API models, this preserves reasoning items by feeding
        `response.output` back into the next request exactly as returned.
        """

        started_at = datetime.datetime.now()
        total_cost = 0
        total_tokens = 0
        tool_trace: list[LLMFunctionCall] = []
        history: list[typing.Any] = list(messages)
        last_raw_response: Response | None = None
        executors_map = {
            tool.name: tool.func
            for tool in tools
        }

        for step in range(1, max_steps + 1):
            current_tokens = cls.count_tokens(history)
            if check_total_length and not cls.has_enough_tokens_to_answer(current_tokens):
                raise openai.OpenAIError('There are too few tokens left to answer.')

            step_response = await cls.process(
                messages=tuple(history),
                temperature=temperature,
                top_p=top_p,
                check_total_length=check_total_length,
                tools=tools,
                reasoning_effort=reasoning_effort,
                use_background_processing=True,
            )

            total_cost += step_response.cost
            total_tokens += step_response.total_tokens
            last_raw_response = step_response.original_response

            if cls.use_old_api:
                raise RuntimeError('Old API is not supported for using tools.')

            if step_response.tool_calls:
                history.extend(step_response.tool_calls)

                for call in step_response.tool_calls:
                    tool_trace.append(call)

                    if logger:
                        await logger(
                            format_tool_chat_message(
                                tool_name=call.name,
                                stage='call',
                                arguments=call.raw_args,
                            ),
                        )

                    exec_fn = executors_map.get(call.name)
                    result_value = None

                    if not call.is_valid or exec_fn is None:
                        if call.call_id is None:
                            raise openai.OpenAIError(f'No call_id received for tool "{call.name}"')

                        error_payload = {
                            'error': f'Tool "{call.name}" unavailable or arguments invalid',
                            'raw_args': call.raw_args,
                        }

                        history.append(
                            LLMFunctionCallOutput(
                                call_id=call.call_id,
                                output=serialize_tool_output(error_payload),
                            ),
                        )

                        if logger:
                            await logger(
                                format_tool_chat_message(
                                    tool_name=call.name,
                                    stage='error',
                                    arguments=call.raw_args,
                                    error='Tool unavailable or arguments invalid',
                                ),
                            )

                        continue

                    try:
                        maybe_coro = exec_fn(call)
                        result_value = await maybe_coro if asyncio.iscoroutine(maybe_coro) else maybe_coro
                    except Exception:
                        logging.exception(f'Exception while executing tool "{call.name}"')

                        if call.call_id is None:
                            raise openai.OpenAIError(f'No call_id received for tool "{call.name}"')

                        history.append(
                            LLMFunctionCallOutput(
                                call_id=call.call_id,
                                output=serialize_tool_output({
                                    'error': 'Unexpected exception while executing tool',
                                }),
                            ),
                        )

                        if logger:
                            await logger(
                                format_tool_chat_message(
                                    tool_name=call.name,
                                    stage='error',
                                    arguments=call.raw_args,
                                    error='Unexpected exception while executing tool',
                                ),
                            )
                    else:
                        if call.call_id is None:
                            raise openai.OpenAIError(f'No call_id received for tool "{call.name}"')

                        history.append(
                            LLMFunctionCallOutput(
                                call_id=call.call_id,
                                output=gen_optimized_json(result_value),
                            ),
                        )

                        if logger:
                            await logger(
                                format_tool_chat_message(
                                    tool_name=call.name,
                                    stage='result',
                                    result=result_value,
                                ),
                            )

                    if stop_when and stop_when(call, result_value):
                        final_turn = await cls.process(
                            messages=tuple(history),
                            temperature=temperature,
                            top_p=top_p,
                            check_total_length=check_total_length,
                            tools=tools,
                            response_format=response_format,
                            reasoning_effort=reasoning_effort,
                            use_background_processing=True,
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
                if step_response.content is None:
                    history.append(LLMMessage(
                        role=LLMMessageRoles.ASSISTANT,
                        content='',
                    ))
                    history.append(LLMMessage(
                        role=LLMMessageRoles.SYSTEM,
                        content='Got empty response. Process the request again',
                    ))
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
    def count_tokens(cls, messages: typing.Sequence[BaseLLMMessage]) -> int:
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

    @classmethod
    async def _make_raw_request(cls, func: typing.Callable) -> typing.Any:
        response = None

        for attempt in range(1, cls.max_retries + 1):
            backoff = 2 ** attempt

            try:
                response = await func()
            except openai.APITimeoutError:
                raise
            except (openai.RateLimitError, openai.InternalServerError,) as e:
                logging.warning(e, exc_info=True)

                if attempt >= cls.max_retries:
                    raise

                logging.warning(e)

                logging.info('Sleep %s seconds before retrying', backoff)
                await asyncio.sleep(backoff)
            except APIConnectionError as e:
                logging.warning(e)

                if attempt >= cls.max_retries:
                    raise

                logging.warning(e)

                logging.info('Sleep %s seconds before retrying', backoff)
                await asyncio.sleep(backoff)
            else:
                if isinstance(response, Response) and response.error and response.error.code == 'too_many_requests':
                    logging.info('Server blocked the request due to too many requests.')
                    logging.info('Sleep %s seconds before retrying', backoff)
                    await asyncio.sleep(backoff)

                break

        return response


DEFAULT_MODEL_CONNECTION_API_CONFIG = ApiConnectionConfig(
    api_key=config.MODEL_CONNECTION_API_KEY,
    base_url=config.MODEL_CONNECTION_API_BASE_URL,
)


def load_llm_models_config() -> typing.Generator:
    with open(config.MODELS_PATH) as file:
        models_config = yaml.safe_load(file)

    model_infos = models_config.get('llm_models', [])

    for model_info in model_infos:
        model_info['input_price'] = float(model_info['input_price'])
        model_info['output_price'] = float(model_info['output_price'])

        if 'connection_api_config' in model_info:
            connection_api_config = ApiConnectionConfig(
                api_key=model_info['connection_api_config']['api_key'],
                base_url=model_info['connection_api_config']['base_url'],
            )
        else:
            connection_api_config = DEFAULT_MODEL_CONNECTION_API_CONFIG

        yield type(model_info['showed_model_name'], (BaseLLM,), {**model_info, 'config': connection_api_config})


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
    config = DEFAULT_MODEL_CONNECTION_API_CONFIG
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
    has_vision: bool
    config: ApiConnectionConfig

    @classmethod
    async def create(cls, text: str) -> DrawerResponse:
        if len(text) >= cls.max_prompt_length:
            raise openai.OpenAIError(f'The maximum length is {cls.max_prompt_length} characters')

        response = await cls.config.client.images.generate(
            prompt=text,
            n=1,
            model=cls.model_name,
            quality='high',
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
    model_name = 'gpt-image-1.5'
    input_price = 8 / 1_000_000
    output_price = 32 / 1_000_000
    max_prompt_length = 10_000
    has_vision = True
    config = DEFAULT_MODEL_CONNECTION_API_CONFIG


@dataclasses.dataclass
class TranscriberResponse:
    text: str
    cost: float


class BaseTranscriber(abc.ABC):
    model_name: str
    input_price: float
    output_price: float
    config: ApiConnectionConfig

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
    config = DEFAULT_MODEL_CONNECTION_API_CONFIG


@dataclasses.dataclass(frozen=True)
class ModeratorResponse:
    is_flagged: bool


class BaseModerator(abc.ABC):
    model_name: str
    config: ApiConnectionConfig

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
