import yaml

from .base import BaseDialog
from .dalle_chat import DalleDialog
from .gpt_chat import Dialog
from .profiles import PROFILES
from .telegram.dialogs import gen_telegram_folder_reader
from ..memory import Memory
from ..models.openai.base import AVAILABLE_GPT_MODELS


def load_dialogs_config(path: str) -> dict:
    with open(path, 'r') as file:
        config = yaml.safe_load(file)

    return config


def create_dialog(dialog_data: dict) -> tuple[str, BaseDialog]:
    dialog_type = dialog_data.get('type')
    name = dialog_data.get('name')
    model_name = dialog_data.get('model')
    models_map = {
        model.showed_model_name: model
        for model in AVAILABLE_GPT_MODELS
    }

    if dialog_type == 'chat':
        profile_slug = dialog_data.get('profile')
        profile = PROFILES.get(profile_slug)
        memory_data = dialog_data.get('memory', {})
        memory = Memory(**memory_data)
        model = models_map[model_name]()
        files_supported = dialog_data.get('files_supported', False)
        return name, Dialog(
            profile=profile,
            memory=memory,
            model=model,
            files_are_supported=files_supported,
        )
    elif dialog_type == 'dalle':
        return name, DalleDialog()
    elif dialog_type == 'telegram_folder_reader':
        model = models_map[model_name]()
        extra = dialog_data.get('extra', {})
        return name, gen_telegram_folder_reader(
            gpt_model=model,
            **extra,
        )
    else:
        raise ValueError(f'Unknown dialog type: {dialog_type}')


def load_dialogs(path: str) -> dict:
    config = load_dialogs_config(path)
    dialogs = {}

    for dialog_data in config.get('dialogs', []):
        name, dialog_instance = create_dialog(dialog_data)
        dialogs[name] = dialog_instance

    return dialogs
