import os

import yaml


BASE_CONFIG_PATH = os.getenv('BASE_CONFIG_PATH', './configs/base.yaml')


def load_yaml_config(file_path=BASE_CONFIG_PATH):
    if os.path.exists(file_path):
        with open(file_path) as f:
            config = yaml.safe_load(f) or {}
            return {key.lower(): value for key, value in config.items()}

    return {}


yaml_config = load_yaml_config()


def get_config_value(name: str, default: object = None) -> object:
    env_value = os.getenv(name.upper())

    if env_value is not None:
        return env_value

    return yaml_config.get(name.lower(), default)


OPENAI_API_KEY = get_config_value('openai_api_key')
OPENAI_BASE_URL = get_config_value('openai_base_url')
OPENROUTER_API_KEY = get_config_value('openrouter_api_key')

if OPENROUTER_API_KEY:
    OPENAI_API_KEY = OPENROUTER_API_KEY
    if not OPENAI_BASE_URL:
        OPENAI_BASE_URL = 'https://openrouter.ai/api/v1'

os.environ['TIKTOKEN_CACHE_DIR'] = get_config_value('tiktoken_cache_dir',
                                                    './app/models/openai/resources/tiktoken_cache')

TELEGRAM_API_ID = get_config_value('telegram_api_id')
TELEGRAM_API_HASH = get_config_value('telegram_api_hash')
GOOGLE_APP_ID = get_config_value('google_app_id')

DEBUG_COPILOT = get_config_value('debug_copilot', False)
DEV_MODE = get_config_value('dev_mode', False)

HOST_NAME = get_config_value('host_name', 'localhost')
PORT = int(get_config_value('port', 8123))

UPLOADS_DIR = get_config_value('uploads_dir', '/tmp')
CONFIGS_DIR = get_config_value('prompts_dir', './configs')
PROFILES_DIR = os.path.join(CONFIGS_DIR, 'profiles')
PROMPTS_DIR = os.path.join(CONFIGS_DIR, 'prompts')
DIALOGS_PATH = os.path.join(CONFIGS_DIR, 'dialogs.yaml')
