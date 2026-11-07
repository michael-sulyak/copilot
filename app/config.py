import datetime
import os
import shutil
import sys

import yaml


if getattr(sys, 'frozen', False):
    # When running as a bundled/compiled executable (AppImage in this case)
    BASE_PATH = sys._MEIPASS
else:
    # When running in a normal Python environment (e.g. during development)
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

BASE_PATH = os.path.normpath(os.path.join(BASE_PATH, '..'))

CONFIGS_DIR = os.path.normpath(os.path.join(BASE_PATH, os.getenv('CONFIGS_DIR', './configs')))
BASE_CONFIG_PATH = os.path.join(CONFIGS_DIR, 'base.yaml')
INIT_CONFIGS_DIR = os.getenv('INIT_CONFIGS_DIR', './demo_configs/')
STATICS_DIR = os.path.normpath(os.path.join(BASE_PATH, os.getenv('STATICS_DIR', './gui/build')))
ICON_PATH = os.path.join(STATICS_DIR, 'icon.png')
LOG_FILE = os.getenv('LOG_FILE', './logs.txt')

if INIT_CONFIGS_DIR and not os.path.isdir(CONFIGS_DIR):
    shutil.copytree(INIT_CONFIGS_DIR, CONFIGS_DIR)


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


MODEL_CONNECTION_API_KEY = get_config_value('model_connection_api_key')
MODEL_CONNECTION_API_BASE_URL = get_config_value('model_connection_api_base_url')

os.environ['TIKTOKEN_CACHE_DIR'] = get_config_value(
    'tiktoken_cache_dir',
    './app/models/openai/resources/tiktoken_cache',
)

TELEGRAM_API_ID = get_config_value('telegram_api_id')
TELEGRAM_API_HASH = get_config_value('telegram_api_hash')
GOOGLE_APP_ID = get_config_value('google_app_id')


def get_bool_config(name: str, default: bool = False) -> bool:
    value = get_config_value(name, default)

    if isinstance(value, bool):
        return value

    if value is None:
        return default

    normalized = str(value).strip().lower()
    if normalized not in {'true', 'false'}:
        raise ValueError(f'{name} must be a boolean.')

    return normalized in {'true'}


DEBUG_COPILOT = get_bool_config('debug_copilot')
DEV_MODE = get_bool_config('dev_mode')
USE_WEBVIEW = get_bool_config('use_webview')

HOST_NAME = get_config_value('host_name', 'localhost')
PORT = int(get_config_value('port', 8123))

UPLOADS_DIR = get_config_value('uploads_dir', '/tmp')
SHOWED_UPLOADS_DIR = get_config_value('showed_uploads_dir', '/uploads')
PROFILES_DIR = os.path.join(CONFIGS_DIR, 'profiles')
PROMPTS_DIR = os.path.join(CONFIGS_DIR, 'prompts')
CHATS_PATH = os.path.join(CONFIGS_DIR, 'chats.yaml')
MODELS_PATH = os.path.join(CONFIGS_DIR, 'models.yaml')
CLEAN_RESPONSES = get_bool_config('clean_responses')
AI_WEB_SEARCH_MODEL = get_config_value('ai_web_search_model', 'GPT5 mini')
MAX_UPLOAD_FILE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_TOTAL_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_FILES = 20
ALLOWED_ORIGINS = {
    f'http://{HOST_NAME}:{PORT}',
}
if HOST_NAME in {'localhost', '127.0.0.1', '::1'}:
    ALLOWED_ORIGINS.update({f'http://localhost:{PORT}', f'http://127.0.0.1:{PORT}', f'http://[::1]:{PORT}'})
if DEV_MODE:
    ALLOWED_ORIGINS.update({'http://localhost:3000', 'http://127.0.0.1:3000'})
ALLOWED_ORIGINS.update(
    origin.strip().rstrip('/')
    for origin in str(get_config_value('allowed_origins', '')).split(',')
    if origin.strip()
)

MAX_TIME_TO_WAIT_QUEUED = datetime.timedelta(minutes=5)
MAX_TIME_TO_WAIT_IN_PROGRESS = datetime.timedelta(minutes=15)
