import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Maps parser dict keys → column order from config.SHEET_COLUMNS
_KEY_TO_COLUMN = [
    "name", "elevator_pitch", "problem", "market", "solution",
    "technology", "business_model", "traction", "team", "round",
    "competitors", "stage", "contacts", "country", "industry", "pitch_date",
    # "Файл" and "Обработан" are added separately in append_pitch_data
]


def init_sheets() -> gspread.Worksheet:
    """Authorize and return the first worksheet. Ensures headers exist."""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH,
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
    worksheet = spreadsheet.sheet1

    _ensure_headers(worksheet)
    logger.info("Google Sheets initialized successfully")
    return worksheet


def _ensure_headers(worksheet: gspread.Worksheet) -> None:
    """Write column headers to row 1 if they are missing."""
    first_row = worksheet.row_values(1)
    if first_row == config.SHEET_COLUMNS:
        return
    logger.info("Writing headers to Google Sheet")
    worksheet.update("A1", [config.SHEET_COLUMNS])
    # Make header row bold
    worksheet.format("1:1", {"textFormat": {"bold": True}})


@retry(
    stop=stop_after_attempt(config.RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=config.RETRY_MIN_WAIT,
        max=config.RETRY_MAX_WAIT,
    ),
    reraise=True,
)
def append_pitch_data(
    worksheet: gspread.Worksheet,
    data: dict,
    filename: str,
) -> int:
    """
    Append one row to the sheet. Returns the row number written.
    Column order follows config.SHEET_COLUMNS.
    """
    row = [data.get(key, "-") for key in _KEY_TO_COLUMN]
    row.append(filename)
    row.append(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    worksheet.append_row(row, value_input_option="USER_ENTERED")

    # Find the row we just wrote (last row)
    row_number = len(worksheet.col_values(1))
    logger.info(f"Appended pitch data to row {row_number}: {data.get('name', '?')}")
    return row_number
