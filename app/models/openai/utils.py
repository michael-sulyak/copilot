import base64
import logging
import math
import re
import typing
from io import BytesIO

import tiktoken
from PIL import Image
from openai.types.chat import ChatCompletionMessageParam
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage, ResponseOutputText,
    ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails
from tiktoken.model import MODEL_TO_ENCODING
from tiktoken.registry import get_encoding


if typing.TYPE_CHECKING:
    from app.models.openai.base import BaseLLM, LLMRequest

MODELS_2_TOKEN_LIMITS = {
    'gpt-35-turbo': 4000,
    'gpt-3.5-turbo': 4000,
    'gpt-35-turbo-16k': 16000,
    'gpt-3.5-turbo-16k': 16000,
    'gpt-4': 8100,
    'gpt-4-32k': 32000,
    'gpt-4v': 128000,
    'gpt-4o': 128000,
}

AOAI_2_OAI = {'gpt-35-turbo': 'gpt-3.5-turbo', 'gpt-35-turbo-16k': 'gpt-3.5-turbo-16k', 'gpt-4v': 'gpt-4-turbo-vision'}

ALL_MODELS = {*MODELS_2_TOKEN_LIMITS.keys(), *AOAI_2_OAI}


def encoding_for_model(model: str, default_to_cl100k=False) -> tiktoken.Encoding:
    """
    Get the encoding for a given GPT model name (OpenAI.com or Azure OpenAI supported).
    Args:
        model (str): The name of the model to get the encoding for.
        default_to_cl100k (bool): Whether to default to the CL100k encoding if the model is not found.
    Returns:
        tiktoken.Encoding: The encoding for the model.
    """

    for item in ALL_MODELS:
        if model.startswith(item):
            model = item

    if model not in AOAI_2_OAI and model not in MODELS_2_TOKEN_LIMITS and not default_to_cl100k:
        raise ValueError('Expected valid OpenAI GPT model name')
    model = AOAI_2_OAI.get(model, model)
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        if default_to_cl100k:
            logging.warning('Model %s not found, defaulting to CL100k encoding', model)
            return tiktoken.get_encoding('cl100k_base')

        raise


def num_tokens_from_messages(messages: typing.Sequence[ChatCompletionMessageParam], model: str,
                             default_to_cl100k=False) -> int:
    return sum(
        num_tokens_from_message(message, model, default_to_cl100k)
        for message in messages
    )


def num_tokens_from_message(message: ChatCompletionMessageParam, model: str, default_to_cl100k=False) -> int:
    """
    Calculate the number of tokens required to encode a message. Based off cookbook:
    https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb

    Args:
        model (str): The name of the model to use for encoding.
        message (Mapping): The message to encode, in a dictionary-like object.
        default_to_cl100k (bool): Whether to default to the CL100k encoding if the model is not found.
    Returns:
        int: The total number of tokens required to encode the message.

    >> model = 'gpt-3.5-turbo'
    >> message = {'role': 'user', 'content': 'Hello, how are you?'}
    >> count_tokens_for_message(model, message)
    13

    See https://github.com/pamelafox/openai-messages-token-helper/
    """
    encoding = encoding_for_model(model, default_to_cl100k)

    # Assumes we're using a recent model
    tokens_per_message = 3

    num_tokens = tokens_per_message
    for key, value in message.items():
        if isinstance(value, list):
            # For GPT-4-vision support, based on https://github.com/openai/openai-cookbook/pull/881/files
            for item in value:
                # Note: item[type] does not seem to be counted in the token count
                if item['type'] == 'text':
                    num_tokens += len(encoding.encode(item['text']))
                elif item['type'] == 'image_url':
                    num_tokens += count_tokens_for_image(item['image_url']['url'], item['image_url']['detail'])
        elif isinstance(value, str):
            num_tokens += len(encoding.encode(value))
        else:
            raise ValueError(f'Could not encode unsupported message value type: {type(value)}')
        if key == 'name':
            num_tokens += 1

    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>

    return num_tokens


def warm_tiktoken_encoders() -> None:
    for encoding_name in MODEL_TO_ENCODING.values():
        get_encoding(encoding_name)


def get_image_dims(image_uri: str) -> tuple[int, int]:
    # From https://github.com/openai/openai-cookbook/pull/881/files
    if re.match(r'data:image\/\w+;base64', image_uri):
        image_uri = re.sub(r'data:image\/\w+;base64,', '', image_uri)
        image = Image.open(BytesIO(base64.b64decode(image_uri)))
        return image.size

    raise ValueError('Image must be a base64 string.')


def count_tokens_for_image(image_uri: str, detail: str = 'auto') -> int:
    # From https://github.com/openai/openai-cookbook/pull/881/files
    # Based on https://platform.openai.com/docs/guides/vision
    LOW_DETAIL_COST = 85
    HIGH_DETAIL_COST_PER_TILE = 170
    ADDITIONAL_COST = 85

    if detail == 'auto':
        # assume high detail for now
        detail = 'high'

    if detail == 'low':
        # Low detail images have a fixed cost
        return LOW_DETAIL_COST

    if detail == 'high':
        # Calculate token cost for high detail images
        width, height = get_image_dims(image_uri)
        # Check if resizing is needed to fit within a 2048 x 2048 square
        if max(width, height) > 2048:
            # Resize dimensions to fit within a 2048 x 2048 square
            ratio = 2048 / max(width, height)
            width = int(width * ratio)
            height = int(height * ratio)
        # Further scale down to 768px on the shortest side
        if min(width, height) > 768:
            ratio = 768 / min(width, height)
            width = int(width * ratio)
            height = int(height * ratio)
        # Calculate the number of 512px squares
        num_squares = math.ceil(width / 512) * math.ceil(height / 512)
        # Calculate the total token cost
        total_cost = num_squares * HIGH_DETAIL_COST_PER_TILE + ADDITIONAL_COST
        return total_cost

    # Invalid detail_option
    raise ValueError('Invalid value for detail parameter. Use "low" or "high".')


def prepare_llm_response_content(content: str | None) -> str | None:
    if content is None:
        return None

    content = content.replace('\u2003', '\t')
    return content


async def process_llm_request_via_old_api(*, llm: type['BaseLLM'], llm_request: 'LLMRequest') -> Response:
    raw_llm_request = llm_request.dump()
    raw_llm_request['messages'] = raw_llm_request.pop('input')

    if raw_llm_request.get('reasoning'):
        raw_llm_request['reasoning_effort'] = raw_llm_request.pop('reasoning').effort

    raw_response = await llm.config.client.chat.completions.create(
        **raw_llm_request,
    )

    if raw_func_call := raw_response.choices[0].message.function_call:
        response_output = ResponseFunctionToolCall(
            arguments=raw_func_call['arguments'],
            call_id='0',
            name=raw_func_call['name'],
            type='function_call',
        )
    else:
        response_output = ResponseOutputMessage(
            id='0',
            content=[
                ResponseOutputText(
                    annotations=[],
                    text=raw_response.choices[0].message.content,
                    type='output_text',
                ),
            ],
            role='assistant',
            status='completed',
            type='message',
        )

    response = Response(
        id=raw_response.id,
        usage=ResponseUsage(
            input_tokens=raw_response.usage.prompt_tokens,
            output_tokens=raw_response.usage.completion_tokens,
            total_tokens=raw_response.usage.total_tokens,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        ),
        created_at=raw_response.created,
        model=raw_response.model,
        object='response',
        output=[response_output],
        parallel_tool_calls=False,
        tool_choice='auto',
        tools=[],
    )

    return response
