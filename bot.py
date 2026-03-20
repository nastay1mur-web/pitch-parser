import io
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import parser as pitch_parser
import sheets

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Initialized once at startup
_worksheet = None


def get_worksheet():
    global _worksheet
    if _worksheet is None:
        _worksheet = sheets.init_sheets()
    return _worksheet


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я парсю питч-деки стартапов и записываю данные в Google Таблицу.\n\n"
        "Просто отправь мне PDF-файл с питчем — я извлеку всю информацию по блокам:\n"
        "название, проблему, рынок, команду, раунд и многое другое.\n\n"
        "Ограничения:\n"
        f"• Максимум {MAX_FILE_SIZE_MB} МБ\n"
        f"• Максимум {config.MAX_PAGES} страниц (остальные будут проигнорированы)"
    )


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document
    filename = document.file_name or "pitch.pdf"

    # --- Validation ---
    if document.mime_type != "application/pdf":
        await update.message.reply_text(
            "Пожалуйста, отправь файл в формате PDF."
        )
        return

    if document.file_size > MAX_FILE_SIZE_BYTES:
        await update.message.reply_text(
            f"Файл слишком большой. Максимум {MAX_FILE_SIZE_MB} МБ."
        )
        return

    # --- Download ---
    status_msg = await update.message.reply_text(
        "Получил питч. Начинаю обработку, это займёт до 1 минуты..."
    )

    try:
        tg_file = await document.get_file()
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        pdf_bytes = buf.getvalue()
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        await status_msg.edit_text("Не удалось скачать файл. Попробуй ещё раз.")
        return

    # --- Magic bytes check ---
    if not pdf_bytes.startswith(b"%PDF"):
        await status_msg.edit_text(
            "Файл не является валидным PDF. Проверь файл и попробуй снова."
        )
        return

    # --- Parse ---
    try:
        await status_msg.edit_text("Конвертирую страницы в изображения...")
        data, total_pages = pitch_parser.process_pdf(pdf_bytes)
    except Exception as e:
        logger.error(f"Parsing failed for {filename}: {e}", exc_info=True)
        await status_msg.edit_text(
            "Не удалось обработать PDF. Возможно, файл повреждён или защищён паролем."
        )
        return

    # --- Write to Sheets ---
    try:
        await status_msg.edit_text("Записываю данные в таблицу...")
        worksheet = get_worksheet()
        row_number = sheets.append_pitch_data(worksheet, data, filename)
    except Exception as e:
        logger.error(f"Sheets write failed: {e}", exc_info=True)
        await status_msg.edit_text(
            "Данные извлечены, но не удалось записать в таблицу. Проверь настройки Google Sheets."
        )
        return

    # --- Success message ---
    truncated_note = ""
    if total_pages > config.MAX_PAGES:
        truncated_note = f"\n⚠️ Обработано первых {config.MAX_PAGES} из {total_pages} страниц."

    sheet_url = f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}"

    result_text = (
        f"Питч обработан и записан в строку {row_number}.\n\n"
        f"*{_esc(data['name'])}*\n"
        f"{_esc(data['elevator_pitch'])}\n\n"
        f"Страна: {_esc(data['country'])} | Отрасль: {_esc(data['industry'])}\n"
        f"Стадия: {_esc(data['stage'])} | Раунд: {_esc(data['round'])}\n"
        f"Команда: {_esc(data['team'])}\n\n"
        f"[Открыть таблицу]({sheet_url})"
        f"{truncated_note}"
    )

    await status_msg.edit_text(result_text, parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Successfully processed pitch: {filename} -> row {row_number}")


def _esc(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def build_application() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(
        MessageHandler(filters.Document.ALL, handle_pdf)
    )
    return app
