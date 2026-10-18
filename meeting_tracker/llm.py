"""LLM access: any OpenAI-compatible endpoint, or None for offline heuristic mode."""
from __future__ import annotations

import json
import os
import re


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY")) and os.getenv("MT_OFFLINE") != "1"


def complete_json(system: str, user: str) -> dict:
    """Call the chat model and parse a JSON object from the reply."""
    from openai import OpenAI

    client = OpenAI(base_url=os.getenv("OPENAI_BASE_URL") or None)
    resp = client.chat.completions.create(
        model=os.getenv("MT_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system + "\nRespond with a single JSON object only."},
            {"role": "user", "content": user},
        ],
    )
    text = resp.choices[0].message.content or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}
