import typing

import yaml

from ..memory import Memory
from ..models.openai.base import AVAILABLE_LLM_MODELS_MAP
from ..utils.yaml import load_yaml_file
from .base import BaseChat
from .code_reviewer.chats import CodeManager
from .drawer_chat import GptImageChat
from .greetings import GreetingsChat
from .llm_chat import Chat
from .profiles import PROFILES
from .telegram.chats import gen_telegram_folder_reader
from .telegram.content_generator import TelegramContentGeneratorChat
from .tools import TOOLS_MAP


def load_chat_config(path: str) -> dict:
    with open(path) as file:
        config = yaml.safe_load(file)

    return config


class LazyChat:
    _chat_creator: typing.Callable

    def __init__(self, chat_creator: typing.Callable) -> None:
        self._chat_creator = chat_creator

    def __call__(self) -> BaseChat:
        return self._chat_creator()


def create_chat(chat_data: dict) -> tuple[str, LazyChat | BaseChat]:
    chat_type = chat_data.get('type')
    name = chat_data.get('name')
    model_name = chat_data.get('model')

    if chat_type == 'chat':
        profile_slug = chat_data.get('profile')
        profile = PROFILES.get(profile_slug)
        memory_data = chat_data.get('memory', {})
        memory = Memory(**memory_data)
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        files_supported = chat_data.get('files_supported', False)
        tools = tuple(
            TOOLS_MAP[tool_name]()
            for tool_name in chat_data.get('tools', {})
        )

        return name, LazyChat(lambda: Chat(
            profile=profile,
            memory=memory,
            model=model,
            files_are_supported=files_supported,
            tools=tools,
        ))

    if chat_type == 'gpt_image':
        return name, LazyChat(lambda: GptImageChat())

    if chat_type == 'greetings':
        return name, LazyChat(lambda: GreetingsChat())

    if chat_type == 'telegram_content_generator':  # TODO: Refactor chat describing here.
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        extra = chat_data.get('extra', {})
        return name, LazyChat(lambda: TelegramContentGeneratorChat(
            model=model,
            **extra,
        ))

    if chat_type == 'telegram_folder_reader':
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        extra = chat_data.get('extra', {})
        model_params = chat_data.get('model_params', {})
        return name, LazyChat(lambda: gen_telegram_folder_reader(
            gpt_model=model,
            model_params=model_params,
            **extra,
        ))

    if chat_type == 'code_manager':
        profile_slug = chat_data.get('profile')
        profile = PROFILES.get(profile_slug)
        memory_data = chat_data.get('memory', {})
        memory = Memory(**memory_data)
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        files_supported = chat_data.get('files_supported', False)
        work_dirs = chat_data.get('work_dirs', [])
        tools = chat_data.get('tools', [])

        return name, LazyChat(lambda: CodeManager(
            profile=profile,
            memory=memory,
            model=model,
            files_are_supported=files_supported,
            work_dirs=work_dirs,
            tools=tools,  # TODO: `Messenger` also has `tools`
        ))

    raise ValueError(f'Unknown chat type: {chat_type}')


def load_chats(path: str) -> dict:
    config = load_yaml_file(path)
    chats = {}

    for chat_data in config.get('chats', []):
        name, chat_instance = create_chat(chat_data)
        chats[name] = chat_instance

    return chats
