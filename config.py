import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "OPENROUTER_API_KEY",
    "TELEGRAM_TOKEN",
    "GOOGLE_SHEET_ID",
]

for _var in REQUIRED_VARS:
    if not os.getenv(_var):
        raise EnvironmentError(
            f"Missing required environment variable: {_var}\n"
            f"Check your .env file (see .env.example)"
        )

OPENROUTER_API_KEY: str = os.environ["OPENROUTER_API_KEY"]
TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
GOOGLE_SHEET_ID: str = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "config/service-account.json")
GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

# Optional: full path to poppler/bin on Windows (leave empty if poppler is in PATH)
POPPLER_PATH: str = os.getenv("POPPLER_PATH", "")

# OpenRouter
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = "qwen/qwen2-vl-7b-instruct:free"

# PDF processing
MAX_PAGES = 20
IMAGE_MAX_SIDE = 1024
IMAGE_DPI = 150
IMAGE_QUALITY = 85

# Retry settings
RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT = 2   # seconds
RETRY_MAX_WAIT = 10  # seconds

# Google Sheets columns (order matters)
SHEET_COLUMNS = [
    "Название",
    "Elevator Pitch",
    "Проблема",
    "Рынок (TAM/SAM/SOM)",
    "Решение / Продукт",
    "Технология",
    "Бизнес-модель",
    "Метрики / Тракшн",
    "Команда",
    "Раунд / Запрос",
    "Конкуренты",
    "Стадия",
    "Контакты",
    "Страна",
    "Отрасль",
    "Дата питча",
    "Файл",
    "Обработан",
]
