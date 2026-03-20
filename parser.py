import io
import json
import logging
import re
from typing import Optional

import pdfplumber
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from prompts import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

EXPECTED_KEYS = [
    "name", "elevator_pitch", "problem", "market", "solution",
    "technology", "business_model", "traction", "team", "round",
    "competitors", "stage", "contacts", "country", "industry", "pitch_date",
]

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def pdf_to_text(pdf_bytes: bytes) -> tuple[str, int]:
    """Extract text from PDF bytes. Returns (text, total_pages)."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        total_pages = len(pdf.pages)
        pages_to_process = min(total_pages, config.MAX_PAGES)
        for i, page in enumerate(pdf.pages[:pages_to_process]):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(f"--- Slide {i+1} ---\n{page_text}")

    full_text = "\n\n".join(text_parts)
    if not full_text.strip():
        full_text = "(No text could be extracted from this PDF)"

    logger.info(f"Extracted {len(full_text)} characters from {pages_to_process} pages")
    return full_text, total_pages


@retry(
    stop=stop_after_attempt(config.RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=config.RETRY_MIN_WAIT,
        max=config.RETRY_MAX_WAIT,
    ),
    reraise=True,
)
def call_llm_api(text: str) -> str:
    """Send extracted text to Groq LLM. Returns raw text response."""
    payload = {
        "model": config.LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{USER_PROMPT}\n\n{text}"},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info(f"Calling Groq API, text length: {len(text)} chars")
    response = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=60)

    if not response.ok:
        raise RuntimeError(f"Groq API {response.status_code}: {response.text[:500]}")

    raw = response.json()["choices"][0]["message"]["content"]
    logger.info("Groq API responded successfully")
    return raw


def _extract_json(raw: str) -> Optional[dict]:
    """Try to extract a JSON object from raw LLM response."""
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        candidate = match.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return None
        candidate = raw[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}\nCandidate:\n{candidate[:500]}")
        return None


def parse_llm_response(raw: str) -> dict:
    """Parse raw LLM response into a clean dict with all 16 expected keys."""
    data = _extract_json(raw)
    if data is None:
        logger.error("Could not extract JSON from LLM response, using fallback")
        data = {}

    result = {}
    for key in EXPECTED_KEYS:
        value = data.get(key)
        if not value or str(value).strip() in ("", "null", "None"):
            result[key] = "-"
        else:
            result[key] = str(value).strip()

    return result


def process_pdf(pdf_bytes: bytes) -> tuple[dict, int]:
    """Full pipeline: PDF bytes -> structured dict. Returns (data, total_pages)."""
    text, total_pages = pdf_to_text(pdf_bytes)
    raw_response = call_llm_api(text)
    data = parse_llm_response(raw_response)
    return data, total_pages
