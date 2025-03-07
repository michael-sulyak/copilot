import os


OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')

GOOGLE_APP_ID = os.getenv('GOOGLE_APP_ID')

DEBUG_COPILOT = True
DEV_MODE = os.getenv('DEV_MODE') == 'true'

HOST_NAME = os.getenv('HOST_NAME', 'localhost')
PORT = int(os.getenv('PORT', 8123))

UPLOADS_DIR = os.getenv('UPLOADS_DIR', '/tmp')
CONFIGS_DIR = os.getenv('PROMPTS_DIR', './configs')
PROFILES_DIR = os.path.join(CONFIGS_DIR, 'profiles')
PROMPTS_DIR = os.path.join(CONFIGS_DIR, 'prompts')
DIALOGS_PATH = os.path.join(CONFIGS_DIR, 'dialogs.yaml')
