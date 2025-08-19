import json
import logging
import re
import typing
from dataclasses import dataclass
from functools import cached_property
from io import BytesIO
from typing import Any

from pydantic import BaseModel
from telethon.tl.types import Channel

from app.dialogs.base import AnswerBtn, BaseDialog, Discussion, Message, Request
from app.dialogs.telegram.utils import get_telegram_client, init_telegram_client
from app.models.openai.base import BaseLLM, GPTImage, LLMMessage, LLMTool, LLMToolParam
from app.models.openai.constants import LLMMessageRoles, LLMToolParamTypes
from app.utils.common import gen_optimized_json
from app.utils.local_file_storage import LocalFileStorage, get_file_storage
from app.utils.searching import Searcher


def sanitize_html(html: str) -> str:
    """
    Minimal sanitizer: drops tags outside ALLOWED_TAGS, strips attributes except pre.language.
    For production, consider a robust sanitizer.
    """

    def repl_tag(m: re.Match) -> str:
        allowed_tags = {'b', 'i', 'code', 'strike', 'u', 'pre'}
        full = m.group(0)
        name = m.group(1).lower()
        closing = full.startswith('</')
        if name not in allowed_tags:
            return ''  # drop entire tag
        if name == 'pre':
            if closing:
                return '</pre>'
            attrs = re.findall(r'(\w+)\s*=\s*"([^"]*)"', full)
            lang = None
            for k, v in attrs:
                if k.lower() == 'language':
                    lang = v
                    break
            if lang:
                safe_lang = re.sub(r'[^a-zA-Z0-9_+-]', '', lang)
                return f'<pre language="{safe_lang}">'
            return '<pre>'
        return f'</{name}>' if closing else f'<{name}>'

    sanitized = re.sub(r'</?([a-zA-Z0-9]+)(\s+[^>]*)?>', repl_tag, html)
    return sanitized


def fix_telegram_html_whitespace(text: str) -> str:
    # Telegram HTML is sensitive to messy whitespace; keep it tidy
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


@dataclass
class DraftPost:
    text: str | None = None
    image: str | bytes | None = None


class ContentGenerator:
    def __init__(
        self,
        *,
        model: BaseLLM,
        status_updater: typing.Callable,
        initial_prompt: str,
    ) -> None:
        self.general_gpt = model
        self.status_updater = status_updater
        self.init_prompt = initial_prompt

    @cached_property
    def toolset(self) -> tuple[LLMTool, ...]:
        return (
            LLMTool(
                name='search',
                description='Search in the internet',
                parameters=(
                    LLMToolParam(
                        name='query',
                        type=LLMToolParamTypes.STRING,
                        description='Search query',
                    ),
                ),
            ),
            LLMTool(
                name='generate_image_and_attach_to_message',
                description='Generate an image from a descriptive, original prompt and attach it',
                parameters=(
                    LLMToolParam(
                        name='prompt',
                        type=LLMToolParamTypes.STRING,
                        description='Descriptive prompt for image generation',
                    ),
                ),
            ),
            LLMTool(
                name='set_message_text',
                description='Set the final HTML text for the message (use only allowed tags)',
                parameters=(
                    LLMToolParam(
                        name='prompt',
                        type=LLMToolParamTypes.STRING,
                        description='The final HTML caption/text',
                    ),
                ),
            ),
            LLMTool(
                name='finish_and_send_message',
                description='Finish composing and send the message',
                parameters=(
                    LLMToolParam(
                        name='prompt',
                        type=LLMToolParamTypes.STRING,
                        description='Any final short note or leave empty',
                    ),
                ),
            ),
        )

    async def _model_safety_review(self, content: str) -> tuple[bool, str]:
        review_system = (
            'You are a strict content safety reviewer. Check the user text for the following:\n'
            '- No politics (current or persuasive). Avoid politicians, parties, elections, policies.\n'
            '- No hate/harassment.\n'
            '- No sexual content.\n'
            '- No dangerous/illegal instructions.\n'
            '- No copyrighted franchises or trademarked terms; no imitation of living authors.\n'
            'If unsafe, rewrite minimally to make it safe while preserving the core idea and tone.\n'
            'Respond in JSON with keys: safe (true/false), text (string or null if doesn\'t have changes).'
        )
        msgs = [
            LLMMessage(role=LLMMessageRoles.SYSTEM, content=review_system),
            LLMMessage(role=LLMMessageRoles.USER, content=content),
        ]

        class SafeReviewResponse(BaseModel):
            safe: bool
            text: str | None

        gpt_response = await self.general_gpt.process(messages=msgs, response_format=SafeReviewResponse)
        data = SafeReviewResponse.model_validate_json(gpt_response.content)
        return data.safe, content if data.safe else data.text

    @staticmethod
    async def _gen_image_from_prompt(prompt: str) -> str | bytes:
        response = await GPTImage.create(prompt)

        if response.data:
            return response.data

        return response.url

    def _build_initial_messages(self, topic_hint: str) -> list[LLMMessage]:
        return [
            LLMMessage(role=LLMMessageRoles.SYSTEM, content=self.init_prompt),
            LLMMessage(
                role=LLMMessageRoles.USER,
                content=(
                    f'Compose a short channel post with the vibe above. Topic hint: {topic_hint}\n'
                    f'Follow the workflow with tools. Avoid disallowed content. Keep HTML within the allowed set.'
                ),
            ),
        ]

    async def _handle_tool_call(self, *, name: str, args: dict[str, Any], draft: DraftPost) -> str:
        logging.info(f'Executing {name} with args: {args}')
        await self.status_updater(f'Executing "{name}"...')

        if name == 'search':
            query = str(args.get('query', '')).strip()
            s_out = gen_optimized_json(await Searcher.find(query))
            s_text = s_out or 'No result found.'
            return f'SAFE-SEARCH-RESULT:\n{s_text}'

        if name == 'generate_image_and_attach_to_message':
            prompt = str(args.get('prompt', '')).strip()
            safe, fixed = await self._model_safety_review(prompt)
            img_prompt = prompt if safe else fixed
            draft.image = await self._gen_image_from_prompt(img_prompt)
            return 'IMAGE-ATTACHED-OK' if safe else 'IMAGE-ATTACHED-AUTOFIXED'

        if name == 'set_message_text':
            text = str(args.get('prompt', '')).strip()
            safe, fixed = await self._model_safety_review(text)
            draft.text = sanitize_html(fixed if not safe else text)
            return 'TEXT-SET-OK' if safe else 'TEXT-AUTOFIXED'

        if name == 'finish_and_send_message':
            if not draft.text:
                return 'SEND-BLOCKED: No safe text set. Please set_message_text first.'

            draft.text = fix_telegram_html_whitespace(draft.text)

            return 'READY-TO-SEND'

        return 'UNKNOWN-TOOL'

    async def run(self, topic_hint: str, max_steps: int = 12) -> DraftPost:
        draft = DraftPost()
        msgs: list[LLMMessage] = self._build_initial_messages(topic_hint)

        for step in range(max_steps):
            await self.status_updater(f'Processing... ({step + 1} step)')
            gpt_response = await self.general_gpt.process(messages=tuple(msgs), tools=self.toolset)

            for func_call in gpt_response.tool_calls:
                msgs.append(LLMMessage(
                    role=LLMMessageRoles.ASSISTANT,
                    content=json.dumps({'call_func': func_call.name, 'args': func_call.args}, ensure_ascii=False),
                ))

                result = await self._handle_tool_call(name=func_call.name, args=func_call.args, draft=draft)

                logging.info(f'Result of {func_call.name}: {result}')

                msgs.append(LLMMessage(
                    role=LLMMessageRoles.SYSTEM,
                    content=json.dumps({'executed_tool_name': func_call.name, 'result': result}, ensure_ascii=False),
                ))

                if func_call.name == 'finish_and_send_message' and 'READY-TO-SEND' in result:
                    return draft

            # Guardrail: if text exists but model hasn't finished after a few steps, return anyway
            if draft.text and step >= 3:
                return draft

        raise RuntimeError(f'No message generated for topic_hint: {topic_hint}.')


class TelegramContentGeneratorDialog(BaseDialog):
    _html_parse_mode: str = 'html'
    _channel_name: str
    _initial_prompt: str
    _model: BaseLLM
    _telegram_channel: Channel
    _file_storage: LocalFileStorage

    def __init__(self, *, channel_name: str, model: BaseLLM, initial_prompt: str) -> None:
        super().__init__()

        self._channel_name = channel_name
        self._model = model
        self._file_storage = get_file_storage()
        self._initial_prompt = initial_prompt.strip()

    async def init(self) -> None:
        self.client = get_telegram_client()
        await init_telegram_client(self.client)
        self._telegram_channel = await self.client.get_entity(self._channel_name)

    async def get_welcome_message(self) -> Message | None:
        return Message(
            content=(
                'Ready to draft a short, safe post with your vibe.\n'
                'Send me a topic hint (e.g., “regularization as warding”).'
            ),
            buttons=(AnswerBtn(name='Generate random post', callback='generate_random'),),
        )

    async def handle(self, request: Request) -> None:
        topic_hint = (request.content or 'Use random topic to generate the content').strip()
        await self._process(discussion=request.discussion, topic_hint=topic_hint)

    async def handle_callback(self, request: Request) -> None:
        if request.callback == 'generate_random':
            await self._process(discussion=request.discussion)
        elif request.callback == 'post':
            await request.discussion.set_text_status('Posting...')

            text = sanitize_html(self.draft.text)
            text = fix_telegram_html_whitespace(text)

            if self.draft.image:
                file = await self.client.upload_file(self.draft.image, file_name='Poster.png')

                await self.client.send_file(
                    self._telegram_channel,
                    file=file,
                    caption=text,
                    parse_mode=self._html_parse_mode,
                )
            else:
                await self.client.send_message(
                    self._telegram_channel,
                    message=text,
                    parse_mode=self._html_parse_mode,
                )

            await request.discussion.reset_text_status()
            await request.discussion.answer(Message(content='Posted!'))
        else:
            await request.discussion.answer(Message(content='Unknown callback type'))

    async def _process(self, *, discussion: Discussion, topic_hint: str | None = None) -> None:
        await discussion.set_text_status(f'Planning post for topic "{topic_hint or "random"}"...')

        async def _status_updater(status: str) -> None:
            await discussion.set_text_status(status)

        draft = await ContentGenerator(
            model=self._model,
            status_updater=_status_updater,
            initial_prompt=self._initial_prompt,
        ).run(topic_hint=topic_hint)

        await discussion.set_text_status('Composing preview...')

        image_md = ''
        if draft.image:
            try:
                if isinstance(draft.image, bytes):
                    file = await self._file_storage.save_file(file_name='chaos_image.png', buffer=BytesIO(draft.image))
                    image_url = file.url
                else:
                    image_url = draft.image

                if image_url:
                    image_md = f'\n\n![Image]({image_url})'
            except Exception as e:
                logging.exception(e)
                image_md = '\n\n_Image generation failed to attach._'

        html_preview = draft.text or '(no text)'
        html_preview = sanitize_html(html_preview)

        content = (
            f'Draft ready.\n\n'
            f'HTML (to post):\n'
            f'```\n{html_preview}\n```'
            f'{image_md}'
        )

        self.draft = draft

        await discussion.answer(Message(content=content, buttons=(AnswerBtn(name='Post', callback='post'),)))
        await discussion.reset_text_status()

    def _update_status(self, status: str) -> None:
        self.draft.status = status
