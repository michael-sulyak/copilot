import typing

import yaml

from ..memory import Memory
from ..models.openai.base import AVAILABLE_LLM_MODELS_MAP
from .base import BaseDialog
from .drawer_chat import GptImageDialog
from .greetings import GreetingsDialog
from .llm_chat import Dialog
from .profiles import PROFILES
from .telegram.content_generator import TelegramContentGeneratorDialog
from .telegram.dialogs import gen_telegram_folder_reader


def load_dialogs_config(path: str) -> dict:
    with open(path) as file:
        config = yaml.safe_load(file)

    return config


class LazyDialog:
    _dialog_creator: typing.Callable

    def __init__(self, dialog_creator: typing.Callable) -> None:
        self._dialog_creator = dialog_creator

    def __call__(self) -> BaseDialog:
        return self._dialog_creator()


def create_dialog(dialog_data: dict) -> tuple[str, LazyDialog | BaseDialog]:
    dialog_type = dialog_data.get('type')
    name = dialog_data.get('name')
    model_name = dialog_data.get('model')

    if dialog_type == 'chat':
        profile_slug = dialog_data.get('profile')
        profile = PROFILES.get(profile_slug)
        memory_data = dialog_data.get('memory', {})
        memory = Memory(**memory_data)
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        files_supported = dialog_data.get('files_supported', False)
        return name, LazyDialog(lambda: Dialog(
            profile=profile,
            memory=memory,
            model=model,
            files_are_supported=files_supported,
        ))

    if dialog_type == 'gpt_image':
        return name, LazyDialog(lambda: GptImageDialog())

    if dialog_type == 'greetings':
        return name, LazyDialog(lambda: GreetingsDialog())

    if dialog_type == 'telegram_content_generator':
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        extra = dialog_data.get('extra', {})
        return name, LazyDialog(lambda: TelegramContentGeneratorDialog(
            model=model,
            **extra,
        ))

    if dialog_type == 'telegram_folder_reader':
        model = AVAILABLE_LLM_MODELS_MAP[model_name]()
        extra = dialog_data.get('extra', {})
        return name, LazyDialog(lambda: gen_telegram_folder_reader(
            gpt_model=model,
            **extra,
        ))

    raise ValueError(f'Unknown dialog type: {dialog_type}')


def load_dialogs(path: str) -> dict:
    config = load_dialogs_config(path)
    dialogs = {}

    for dialog_data in config.get('dialogs', []):
        name, dialog_instance = create_dialog(dialog_data)
        dialogs[name] = dialog_instance

    return dialogs
