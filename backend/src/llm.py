#!/usr/bin/env python3
"""
Read invoice.txt and use OpenRouter to extract the total amount due.
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

SYSTEM_PROMPT = (
    "You are an expert accountant. "
    "The user will provide the text content of an invoice. "
    "Extract and return the total amount due (the final amount the customer must pay). "
    "Reply with a single JSON object in the form: "
    '{{"total": "<amount with currency symbol>", "currency": "<ISO 4217 code>", "notes": "<brief explanation>"}}. '
    "Do not include any other text."
)


def extract_total(invoice_text: str, *, api_key: str, model: str) -> dict:
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": invoice_text},
        ],
        response_format={"type": "json_object"},
    )

    import json
    raw = response.choices[0].message.content
    return json.loads(raw)


def run_prompt(prompt: str, text: str, *, api_key: str | None = None, model: str | None = None) -> str:
    """Run a free-form prompt against `text` using OpenRouter/OpenAI client.

    Returns the raw assistant content as a string.
    """
    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if model is None:
        model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
    )

    return response.choices[0].message.content


def run_prompt_stream(prompt: str, text: str, *, api_key: str | None = None, model: str | None = None):
    """Stream LLM output for the given prompt+text.

    Yields partial text chunks as they arrive from the OpenRouter/OpenAI streaming API.
    """
    if api_key is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    if model is None:
        model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # request streaming completion
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        stream=True,
    )

    # Iterate events and yield only text fragments when present.
    for event in stream:
        try:
            # Helper to extract content from a single choice (dict or object)
            def _choice_contents(choice):
                contents = []
                # dict-like
                if isinstance(choice, dict):
                    delta = choice.get("delta") or {}
                    if isinstance(delta, dict) and "content" in delta:
                        contents.append(delta.get("content"))
                    # sometimes the full message comes in 'message'
                    msg = choice.get("message")
                    if isinstance(msg, dict):
                        c = msg.get("content")
                        if isinstance(c, str):
                            contents.append(c)
                else:
                    # object-like
                    delta = getattr(choice, "delta", None)
                    if delta is not None:
                        # delta may be dict-like or object with attribute 'content'
                        if isinstance(delta, dict):
                            if "content" in delta:
                                contents.append(delta.get("content"))
                        else:
                            c = getattr(delta, "content", None)
                            if c:
                                contents.append(c)
                    msg = getattr(choice, "message", None)
                    if msg is not None:
                        c = getattr(msg, "content", None)
                        if isinstance(c, str):
                            contents.append(c)
                return contents

            # extract choices list (dict or object)
            choices = []
            if isinstance(event, dict):
                choices = event.get("choices", []) or []
            else:
                choices = getattr(event, "choices", []) or []

            emitted = False
            for ch in choices:
                for piece in _choice_contents(ch):
                    if piece:
                        yield piece
                        emitted = True

            # Some SDKs may return plain message content at top-level
            if not emitted:
                # try top-level message/content
                if isinstance(event, dict):
                    msg = event.get("message") or {}
                    if isinstance(msg, dict):
                        c = msg.get("content")
                        if isinstance(c, str):
                            yield c
                else:
                    msg = getattr(event, "message", None)
                    if msg is not None:
                        c = getattr(msg, "content", None)
                        if isinstance(c, str):
                            yield c
        except Exception:
            # ignore malformed pieces
            continue


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Extract total amount from an invoice using OpenRouter")
    parser.add_argument("file", nargs="?", default="invoice.txt", help="Path to invoice text file (default: invoice.txt)")
    parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"), help="OpenRouter model ID")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("error: OPENROUTER_API_KEY is not set. Add it to .env or export it.", file=sys.stderr)
        sys.exit(1)

    try:
        invoice_text = open(args.file, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    print(f"Sending {args.file!r} to {args.model} via OpenRouter…")
    result = extract_total(invoice_text, api_key=api_key, model=args.model)

    print(f"\nTotal due : {result.get('total')}")
    print(f"Currency  : {result.get('currency')}")
    if result.get("notes"):
        print(f"Notes     : {result.get('notes')}")


if __name__ == "__main__":
    main()
