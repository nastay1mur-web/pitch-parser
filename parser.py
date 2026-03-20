import base64
import io
import json
import logging
import re
from typing import Optional

import google.generativeai as genai
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

genai.configure(api_key=config.GEMINI_API_KEY)


def pdf_to_images(pdf_bytes: bytes) -> tuple[list, int]:
    """Convert PDF bytes to list of PIL Image objects. Returns (images, total_pages)."""
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
        page.thumbnail(
            (config.IMAGE_MAX_SIDE, config.IMAGE_MAX_SIDE),
            Image.LANCZOS,
        )
        result.append(page)

    return result, total_pages


@retry(
    stop=stop_after_attempt(config.RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=1,
        min=config.RETRY_MIN_WAIT,
        max=config.RETRY_MAX_WAIT,
    ),
    reraise=True,
)
def call_vision_api(images: list) -> str:
    """Send images to Gemini vision model. Returns raw text response."""
    model = genai.GenerativeModel(
        model_name=config.VISION_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    # Build content: all images + prompt text
    content = images + [USER_PROMPT]

    logger.info(f"Calling Gemini API with {len(images)} images")
    response = model.generate_content(content)
    logger.info("Gemini API responded successfully")
    return response.text


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
    images, total_pages = pdf_to_images(pdf_bytes)
    raw_response = call_vision_api(images)
    data = parse_llm_response(raw_response)
    return data, total_pages
