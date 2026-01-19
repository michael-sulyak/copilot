import dataclasses
import logging
import typing

import telethon.tl.types
from telethon import TelegramClient
from telethon.tl.custom import Message as TelegramMessage
from telethon.tl.functions.messages import (
    GetDialogFiltersRequest,
    GetForumTopicsRequest, ReadDiscussionRequest,
)

from ...utils.common import escape_markdown
from ..base import Discussion, Message
from .utils import get_telegram_client, init_telegram_client


# Note: https://my.telegram.org/apps


@dataclasses.dataclass
class Source:
    dialog: telethon.tl.custom.Dialog
    topic: telethon.tl.types.ForumTopic
    filter_for_reply_to: int | None
    unread_count: int

    @classmethod
    def parse(cls, dialog: telethon.tl.custom.Dialog, topic: telethon.tl.types.ForumTopic | None = None) -> 'Source':
        unread_count = (topic or dialog).unread_count

        if not unread_count and dialog.dialog.unread_mark:
            unread_count = 1

        return cls(
            dialog=dialog,
            topic=topic,
            filter_for_reply_to=topic.id if topic else None,
            unread_count=unread_count,
        )


class TelegramMessageExtractor:
    _folder_name: str
    _client: TelegramClient
    _filtering: typing.Callable | None
    _key_words: tuple[str, ...]

    def __init__(
        self,
        *,
        folder_name: str,
        filtering: typing.Callable | None = None,
        key_words: tuple[str, ...] = (),
    ) -> None:
        self._folder_name = folder_name
        self._client = get_telegram_client()
        self._filtering = filtering
        self._key_words = key_words

    async def init(self) -> None:
        await init_telegram_client(self._client)

    async def iter_messages(self, *, discussion: Discussion) -> typing.AsyncGenerator:
        sources = [source async for source in self._iter_target_sources()]

        await discussion.answer(Message(
            content=self._generate_first_message(sources=sources),
        ))

        sources = tuple(
            source
            for source in sources
            if source.unread_count
        )

        for i, source in enumerate(sources):
            channel_title = source.dialog.title
            channel_topic = source.topic.title if source.topic else None

            prepared_messages = []
            read_dialog_messages = []

            logging.info(
                f'Reading {channel_title}'
                + f' ({channel_topic})' if channel_topic is not None else f'... ({i + 1}/{len(sources)})',
            )

            if i == 0:
                await discussion.set_text_status('Reading channel...')
            else:
                await discussion.set_text_status(f'Reading channel... {round(i / len(sources) * 100)}%')

            async for message in self._client.iter_messages(
                source.dialog,
                reply_to=source.filter_for_reply_to,
                limit=source.unread_count,
            ):
                if getattr(message.chat, 'username', None):
                    post_link = f'https://t.me/{message.chat.username}/{message.id}'
                else:
                    post_link = f'https://t.me/c/{message.chat.id}/{message.id}'

                read_dialog_messages.append(message)

                if not message.text:
                    logging.info(f'Skip "{post_link}", because it doesn\'t have a text.')
                    continue

                lower_text = message.text.lower()
                for key_word in self._key_words:
                    if key_word.lower() in lower_text:
                        await discussion.answer(Message(content=f'Found key word "{key_word}" in {post_link}'))
                        break

                if self._is_ad(message):
                    logging.info(f'Skip "{post_link}", because it is ad.')
                    continue

                if message.sender:
                    author = f'@{message.sender.username}' if message.sender.username else f'id{message.sender.id}'
                else:
                    author = 'unknown'

                prepared_message = {
                    'text': message.text,
                    'source': {
                        'channel_title': channel_title,
                        'channel_topic': channel_topic,
                        'url': post_link,
                    },
                    'author': author,
                    'sent_at': message.date,
                }

                if not self._filtering or self._filtering(prepared_message):
                    prepared_messages.append(prepared_message)
                else:
                    logging.info(f'Skip "{post_link}", because the filtering ({prepared_message}).')

            if read_dialog_messages:
                await self._mark_as_read(source.dialog, read_dialog_messages)

                if source.topic:
                    for message in read_dialog_messages:
                        await self._client(ReadDiscussionRequest(
                            source.dialog,
                            msg_id=source.topic.id,
                            read_max_id=message.id,  # Note: It doesn't want to read all messages using last msg id.
                        ))

            for prepared_message in prepared_messages:
                yield prepared_message

    @staticmethod
    def _generate_first_message(*, sources: typing.Sequence[Source]) -> str:
        dialog_titles = {
            f'**{escape_markdown(source.dialog.title)}**'
            for source in sources
        }

        return f'Reading messages from channels:\n\n{", ".join(sorted(dialog_titles))}'

    async def _iter_target_sources(self) -> typing.AsyncGenerator:
        filter_by_news = await self._get_filter_by_target_folder()

        # Note: https://core.telegram.org/constructor/dialogFilter
        async for dialog in self._client.iter_dialogs():
            if dialog.input_entity not in filter_by_news.include_peers:
                if (
                    not filter_by_news.contacts
                    and dialog.is_user
                    and dialog.entity.contact
                ):
                    continue

                if (
                    not filter_by_news.non_contacts
                    and dialog.is_user
                    and not dialog.entity.contact
                ):
                    continue

                if not filter_by_news.groups and dialog.is_group:
                    continue

                if not filter_by_news.broadcasts and dialog.is_channel:
                    continue

                if not filter_by_news.bots and dialog.is_user and dialog.entity.bot:
                    continue

                if filter_by_news.exclude_archived and dialog.archived:
                    continue

            if dialog.input_entity in filter_by_news.exclude_peers:
                continue

            if dialog.is_channel and dialog.entity.forum:
                for topic in (await self._client(GetForumTopicsRequest(
                    dialog.entity,
                    offset_date=None,
                    offset_id=0,
                    offset_topic=0,
                    limit=100,
                ))).topics:
                    yield Source.parse(dialog=dialog, topic=topic)
            else:
                yield Source.parse(dialog=dialog)

    async def _get_filter_by_target_folder(self) -> telethon.tl.types.DialogFilter:
        for dialog_filter in (await self._client(GetDialogFiltersRequest())).filters:
            if isinstance(dialog_filter,
                          telethon.tl.types.DialogFilter) and dialog_filter.title.text == self._folder_name:
                return dialog_filter

        raise Exception('The folder is not found.')

    async def _mark_as_read(self, dialog, messages) -> None:
        await self._client.send_read_acknowledge(
            entity=dialog,
            message=messages,
            clear_mentions=True,
            clear_reactions=True,
        )

    @staticmethod
    def _is_ad(message: TelegramMessage) -> bool:
        stop_words = {
            '#реклама',
        }

        for stop_word in stop_words:
            if isinstance(stop_word, str):
                if stop_word in message.text:
                    return True
            elif all(
                (stop_word_part in message.text)
                for stop_word_part in stop_word
            ):
                return True

        return False
