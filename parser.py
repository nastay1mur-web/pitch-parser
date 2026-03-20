import base64
import io
import json
import logging
import re
from typing import Optional

import requests
from pdf2image import convert_from_bytes
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from prompts import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

# JSON keys that must be present in the response
EXPECTED_KEYS = [
    "name", "elevator_pitch", "problem", "market", "solution",
    "technology", "business_model", "traction", "team", "round",
    "competitors", "stage", "contacts", "country", "industry", "pitch_date",
]


def pdf_to_images(pdf_bytes: bytes) -> tuple[list[bytes], int]:
    """Convert PDF bytes to list of JPEG image bytes. Returns (images, total_pages)."""
    pages = convert_from_bytes(
        pdf_bytes,
        dpi=config.IMAGE_DPI,
        fmt="jpeg",
        poppler_path=config.POPPLER_PATH or None,
    )
    total_pages = len(pages)
    if total_pages > config.MAX_PAGES:
        logger.warning(f"PDF has {total_pages} pages, truncating to {config.MAX_PAGES}")
        pages = pages[:config.MAX_PAGES]

    result = []
    for page in pages:
        # Resize: keep aspect ratio, limit long side to IMAGE_MAX_SIDE
        page.thumbnail(
            (config.IMAGE_MAX_SIDE, config.IMAGE_MAX_SIDE),
            Image.LANCZOS,
        )
        buf = io.BytesIO()
        page.save(buf, format="JPEG", optimize=True, quality=config.IMAGE_QUALITY)
        result.append(buf.getvalue())

    return result, total_pages


def _images_to_content(images_bytes: list[bytes]) -> list[dict]:
    """Build OpenRouter message content from image bytes."""
    content = []
    for img_bytes in images_bytes:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
            },
        })
    content.append({"type": "text", "text": USER_PROMPT})
    return content


@retry(
    stop=stop_after_attempt(config.RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=config.RETRY_MIN_WAIT,
        max=config.RETRY_MAX_WAIT,
    ),
    reraise=True,
)
def call_vision_api(images_bytes: list[bytes]) -> str:
    """Send images to OpenRouter vision model. Returns raw text response."""
    payload = {
        "model": config.VISION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _images_to_content(images_bytes)},
        ],
    }
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/parser-pitch",
        "X-Title": "Pitch Parser Bot",
    }

    logger.info(f"Calling OpenRouter API with {len(images_bytes)} images")
    response = requests.post(
        config.OPENROUTER_API_URL,
        json=payload,
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    logger.info("OpenRouter API responded successfully")
    return raw


def _extract_json(raw: str) -> Optional[dict]:
    """Try to extract a JSON object from raw LLM response."""
    # 1. Try to find ```json ... ``` block
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        candidate = match.group(1)
    else:
        # 2. Find first { ... } spanning the whole object
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

    # Ensure all keys exist; fill missing with "-"
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
    images, total_pages = pdf_to_images(pdf_bytes)
    raw_response = call_vision_api(images)
    data = parse_llm_response(raw_response)
    return data, total_pages
