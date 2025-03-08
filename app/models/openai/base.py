import asyncio
import dataclasses
import datetime
import json
import logging
import typing
from functools import cached_property

import openai
import yaml
from openai import APIConnectionError, AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI
from openai.types.chat import ChatCompletion

from ... import config
from ...utils.common import chunk_generator
from .constants import NOTSET, GPTContentTypes, GPTFuncParamTypes, GPTRoles
from .utils import num_tokens_from_messages


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
class GPTResponse:
    content: str | None
    func_call: typing.Optional['GPTFuncCall']
    duration: datetime.timedelta
    cost: float
    total_tokens: int
    original_response: ChatCompletion
    generated_at: datetime.datetime = dataclasses.field(
        default_factory=datetime.datetime.now,
    )

    def to_gpt_message(self) -> 'GPTMessage':
        if self.func_call:
            return GPTMessage(
                role=GPTRoles.FUNCTION,
                name=self.func_call.name,
                content=json.dumps(self.func_call.args),
            )

        return GPTMessage(
            role=GPTRoles.ASSISTANT,
            content=self.content,
        )


@dataclasses.dataclass(frozen=True)
class GPTMessage:
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

        assert self.name is None or self.role == GPTRoles.FUNCTION

        if self.role == GPTRoles.FUNCTION:
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
                        'type': GPTContentTypes.TEXT,
                        'text': self.content,
                    },
                    *(
                        {
                            'type': GPTContentTypes.IMAGE_URL,
                            'image_url': {
                                'url': base64_image,
                                'detail': 'high',
                            },
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
class GPTFuncParam:
    name: str
    type: str
    description: str
    enum: tuple[str, ...] | None = None
    required: bool = False


@dataclasses.dataclass(frozen=True)
class GPTFuncCall:
    name: str
    args: dict[str, typing.Any] | None
    raw_args: str | None
    is_valid: bool


@dataclasses.dataclass(frozen=True)
class GPTFunc:
    name: str
    description: str
    parameters: tuple[GPTFuncParam, ...]

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
            'description': self.description,
            'parameters': {
                'type': GPTFuncParamTypes.OBJECT,
                'properties': properties,
                'required': required,
            },
        }


@dataclasses.dataclass(frozen=True)
class GPTRequest:
    model: str
    messages: typing.Sequence[GPTMessage]
    n: int
    temperature: float | NOTSET = NOTSET
    top_p: float | NOTSET = NOTSET
    response_format: str | NOTSET = NOTSET
    functions: tuple[GPTFunc, ...] | NOTSET = NOTSET
    reasoning_effort: str | NOTSET = NOTSET

    def dump(self) -> dict:
        result = {
            'model': self.model,
            'messages': [
                message.dump()
                for message in self.messages
            ],
            'n': self.n,
        }

        if self.temperature is not NOTSET:
            result['temperature'] = self.temperature

        if self.top_p is not NOTSET:
            result['top_p'] = self.top_p

        if self.response_format is not NOTSET:
            result['response_format'] = self.response_format

        if self.reasoning_effort is not NOTSET:
            result['reasoning_effort'] = self.reasoning_effort

        if self.functions is not NOTSET:
            result['tools'] = [
                {
                    'type': 'function',
                    'function': function.dump(),
                }
                for function in self.functions
            ]

        return result


class BaseGPT:
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
                      messages: typing.Sequence[GPTMessage], *,
                      temperature: float | NOTSET = NOTSET,
                      top_p: float | NOTSET = NOTSET,
                      check_total_length: bool = False,
                      functions: tuple[GPTFunc, ...] | NOTSET = NOTSET,
                      response_format: str | NOTSET = NOTSET,
                      reasoning_effort: str | NOTSET = NOTSET,
                      _count_of_repeats: int = 0) -> GPTResponse:
        started_at = datetime.datetime.now()

        gpt_request = GPTRequest(
            model=cls.model_name,
            temperature=temperature,
            top_p=top_p,
            messages=messages,
            n=1,
            response_format=response_format,
            functions=functions,
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
                response = await cls.config.client.chat.completions.create(
                    **gpt_request.dump(),
                )
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
            response.usage.prompt_tokens * cls.input_price
            + response.usage.completion_tokens * cls.output_price
        )

        logging.info('Processing time: %s', processing_time)
        logging.info('Cost: %s$', round(cost, 6))

        if raw_func_call := response.choices[0].message.function_call:
            raw_func_args = raw_func_call['arguments']

            try:
                func_args = json.loads(raw_func_call['arguments'])
            except json.JSONDecodeError as e:
                logging.warning(e)

                func_is_valid = False
                func_args = None
            else:
                func_is_valid = True

            gpt_func_call = GPTFuncCall(
                name=raw_func_call['name'],
                args=func_args,
                raw_args=raw_func_args,
                is_valid=func_is_valid,
            )
        else:
            gpt_func_call = None

        return GPTResponse(
            content=response.choices[0].message.content,
            func_call=gpt_func_call,
            duration=processing_time,
            cost=cost,
            total_tokens=response.usage.total_tokens,
            original_response=response,
        )

    @classmethod
    def count_tokens(cls, messages: typing.Sequence[GPTMessage]) -> int:
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
        return cls.count_tokens((GPTMessage(role=GPTRoles.USER, content=text),))

    @classmethod
    def has_enough_tokens_to_answer(cls, count_of_tokens: int, *, min_response_volume: float | None = None) -> bool:
        if min_response_volume is None:
            min_response_volume = cls.min_response_volume

        return count_of_tokens + cls.max_tokens * min_response_volume <= cls.max_tokens


OPENAI_CONFIG = OpenAiConfig(
    api_key=config.OPENAI_API_KEY,
    base_url=config.OPENAI_BASE_URL,
)


# class GPT4o(BaseGPT):
#     showed_model_name = 'GPT4o'
#     model_name = 'gpt-4o-2024-11-20'
#     max_tokens = 128_000
#     input_price = 2.5 / 1_000_000
#     output_price = 10 / 1_000_000
#     config = OPENAI_CONFIG
#     has_vision = True
#
#
# class GPT4mini(BaseGPT):
#     showed_model_name = 'GPT4o mini'
#     model_name = 'gpt-4o-mini-2024-07-18'
#     max_tokens = 128_000
#     input_price = 0.15 / 1_000_000
#     output_price = 0.6 / 1_000_000
#     config = OPENAI_CONFIG
#     has_vision = True
#
#
# class GPTo3mini(BaseGPT):
#     showed_model_name = 'GPTo3 mini'
#     model_name = 'o3-mini-2025-01-31'
#     max_tokens = 200_000
#     input_price = 1.1 / 1_000_000
#     output_price = 4.4 / 1_000_000
#     config = OPENAI_CONFIG
#     is_reasoning = True


def load_gpt_models_config() -> typing.Generator:
    with open(config.MODELS_PATH) as file:
        models_config = yaml.safe_load(file)

    model_infos = models_config.get('gpt_models', [])

    for model_info in model_infos:
        yield type(model_info['showed_model_name'], (BaseGPT,), {**model_info, 'config': OPENAI_CONFIG})


AVAILABLE_GPT_MODELS = tuple(load_gpt_models_config())


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
class ImageResponse:
    url: str
    cost: float


class Dalle:
    model_name = 'dall-e-3'
    price = 0.12
    max_prompt_length = 1_000
    config = OPENAI_CONFIG

    @classmethod
    async def process(cls, text: str) -> ImageResponse:
        if len(text) >= cls.max_prompt_length:
            raise openai.OpenAIError('The maximum length is 1000 characters')

        response = await cls.config.client.images.generate(
            prompt=text,
            n=1,
            model=cls.model_name,
            quality='hd',
            size='1792x1024',
        )
        return ImageResponse(
            url=response.data[0].url,
            cost=cls.price,
        )


@dataclasses.dataclass
class WhisperResponse:
    text: str
    cost: float


class Whisper:
    model_name = 'whisper-1'
    price = 0.006
    config = OPENAI_CONFIG

    @classmethod
    async def process(cls, audio: typing.BinaryIO) -> WhisperResponse:
        response = await cls.config.client.audio.transcriptions.create(
            model=cls.model_name,
            file=audio,
            response_format='verbose_json',
        )

        return WhisperResponse(
            text=response.text,
            cost=response.duration / 60 * cls.price,
        )
