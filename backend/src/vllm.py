#!/usr/bin/env python3
"""
vllm.py

Helpers for running visual OCR through OpenRouter (visual LLM) with a
local pytesseract fallback when an API key or model is not available.

Functions:
- ocr_with_openrouter(path, api_key=None, model=None) -> dict
- ocr_with_tesseract(path) -> dict
- run_visual_ocr(path, api_key=None, model=None) -> dict  # tries OpenRouter then tesseract

This module is intentionally defensive: if OpenRouter calls fail it will
fall back to local OCR if possible.
"""

from __future__ import annotations

import os
import base64
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _read_b64(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def ocr_with_openrouter(path: str, api_key: str | None = None, model: str | None = None) -> dict:
    """Send the image to OpenRouter's chat endpoint and request OCR output.

    The function sends a system prompt describing the expected JSON output
    and includes the image as base64 inside the user message. Note: some
    OpenRouter models may accept image attachments directly; this function
    uses a conservative base64-in-message approach which works with
    chat-style multimodal models that accept raw text input.
    """
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("openai.OpenAI client is required for OpenRouter calls") from e

    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if model is None:
        model = os.environ.get("OPENROUTER_MODEL", "nvidia/llama-nemotron-embed-vl-1b-v2:free")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    b64 = _read_b64(path)

    system_prompt = (
        "You are a visual OCR assistant. The user will provide an image encoded in base64. "
        "Extract all textual content from the image and return a JSON object exactly like: "
        "{" + '"text": "<extracted text>"' + "}. Do not include any other text."
    )

    # Place the base64 payload in the user message separated by a marker.
    user_content = f"DATA:BASE64\n{b64}"

    # ask for JSON response (OpenRouter SDK supports response_format in some SDKs)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        return json.loads(raw)
    except Exception as e:
        logger.exception("OpenRouter OCR request failed: %s", e)
        raise


def ocr_with_tesseract(path: str) -> dict:
    """Perform OCR using local pytesseract (Tesseract must be installed).

    Returns a dict: {"text": "..."}
    """
    try:
        from PIL import Image
        import pytesseract
    except Exception as e:
        raise RuntimeError("pytesseract and Pillow are required for local OCR") from e

    img = Image.open(path)
    text = pytesseract.image_to_string(img)
    return {"text": text}


def run_visual_ocr(path: str, api_key: str | None = None, model: str | None = None) -> dict:
    """Try OpenRouter visual OCR first, fall back to local tesseract if it fails.

    Returns a dict containing at least the `text` key.
    """
    # Try remote OpenRouter visual model first
    try:
        return ocr_with_openrouter(path, api_key=api_key, model=model)
    except Exception:
        logger.info("Falling back to local tesseract OCR for %s", path)
        try:
            return ocr_with_tesseract(path)
        except Exception as e:
            logger.exception("Local OCR failed: %s", e)
            raise RuntimeError("both OpenRouter and local OCR failed") from e


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run visual OCR via OpenRouter (with local fallback)")
    parser.add_argument("file", help="Path to image file")
    parser.add_argument("--model", help="OpenRouter model id", default=None)
    parser.add_argument("--api-key", help="OpenRouter API key", default=None)
    args = parser.parse_args()

    result = run_visual_ocr(args.file, api_key=args.api_key, model=args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
