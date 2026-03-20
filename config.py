import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "GROQ_API_KEY",
    "TELEGRAM_TOKEN",
    "GOOGLE_SHEET_ID",
]

for _var in REQUIRED_VARS:
    if not os.getenv(_var):
        raise EnvironmentError(
            f"Missing required environment variable: {_var}\n"
            f"Check your .env file (see .env.example)"
        )

GROQ_API_KEY: str = os.environ["GROQ_API_KEY"]
TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
GOOGLE_SHEET_ID: str = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "config/service-account.json")
GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

# Groq
LLM_MODEL = "llama-3.3-70b-versatile"

# PDF processing
MAX_PAGES = 20

# Retry settings
RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT = 2
RETRY_MAX_WAIT = 10

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
