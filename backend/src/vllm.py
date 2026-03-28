#!/usr/bin/env python3
"""
vllm.py

Helpers for running visual OCR through OpenRouter (visual LLM).

Functions:
- ocr_with_openrouter(path, api_key=None, model=None) -> dict
- run_visual_ocr(path, api_key=None, model=None) -> dict
"""

from __future__ import annotations

import os
import base64
import json
import logging
import mimetypes
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _read_b64(path: str) -> tuple[str, str]:
    """Return (base64_string, mime_type) for the given file."""
    mime_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return b64, mime_type


# Default visual model — must support image_url content parts via OpenRouter.
# Override with VLLM_MODEL environment variable.
_DEFAULT_VLLM_MODEL = "google/gemini-3-flash-preview"

# also: VLLM_MODEL=anthropic/claude-3-haiku

def ocr_with_openrouter(path: str, api_key: str | None = None, model: str | None = None) -> dict:
    """Send the image to an OpenRouter vision model using the standard image_url API.

    The image is encoded as a base64 data URL and embedded in the user message
    content array, which is the format expected by all OpenAI-compatible vision models.
    """
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("openai.OpenAI client is required for OpenRouter calls") from e

    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if model is None:
        model = os.environ.get("VLLM_MODEL", _DEFAULT_VLLM_MODEL)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    b64, mime_type = _read_b64(path)
    data_url = f"data:{mime_type};base64,{b64}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all textual content from the image and format it as Markdown. "
                                "Use headings, bullet lists, tables, bold/italic, and code blocks where appropriate to reflect the visual structure. "
                                "Preserve the original reading order. "
                                "Return only the Markdown — no preamble, no commentary, no code fences around the whole output."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
        )

        text = response.choices[0].message.content or ""
        return {"text": text}
    except Exception as e:
        logger.exception("OpenRouter OCR request failed: %s", e)
        raise


def ocr_with_openrouter_stream(path: str, api_key: str | None = None, model: str | None = None):
    """Stream visual OCR output from an OpenRouter vision model.

    Yields partial text chunks as they arrive.
    """
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("openai.OpenAI client is required for OpenRouter calls") from e

    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if model is None:
        model = os.environ.get("VLLM_MODEL", _DEFAULT_VLLM_MODEL)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    b64, mime_type = _read_b64(path)
    data_url = f"data:{mime_type};base64,{b64}"

    stream = client.chat.completions.create(
        model=model,
        stream=True,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all textual content from the image and format it as Markdown. "
                            "Use headings, bullet lists, tables, bold/italic, and code blocks where appropriate to reflect the visual structure. "
                            "Preserve the original reading order. "
                            "Return only the Markdown — no preamble, no commentary, no code fences around the whole output."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
    )

    for event in stream:
        try:
            choices = getattr(event, "choices", []) or []
            for choice in choices:
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    c = getattr(delta, "content", None)
                    if c:
                        yield c
        except Exception:
            continue


def run_visual_ocr(path: str, api_key: str | None = None, model: str | None = None) -> dict:
    """Try OpenRouter visual OCR.

    Returns a dict containing at least the `text` key.
    """
    # Run OpenRouter visual OCR (no local fallback)
    return ocr_with_openrouter(path, api_key=api_key, model=model)


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
