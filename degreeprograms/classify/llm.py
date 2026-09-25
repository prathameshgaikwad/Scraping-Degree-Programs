"""Optional LLM fallback for ambiguous program classification.

Disabled by default. Only called for programs the deterministic classifier
marks as ambiguous (LOW, or low-confidence MEDIUM), so the vast majority of the
dataset never reaches an LLM. Output is validated against a strict schema; on
failure the model is asked once to correct itself, then the deterministic result
is kept.

Enable with ``CLASSIFY_LLM_ENABLED=1`` (or ``INTEL_LLM_ENABLED=1``). Reuses the
same env conventions as the intelligence layer.
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Optional

import httpx
from pydantic import ValidationError

from .models import LLMClassification
from .taxonomy import FIELD_ORDER

_ALLOWED = ", ".join(FIELD_ORDER)

_SYSTEM = (
    "You classify university Master's program titles into a fixed taxonomy. "
    "Return JSON only. Do not invent fields. Use relevance in {HIGH, MEDIUM, LOW, NONE}. "
    "Classify by what the program actually teaches, not by the university's prestige."
)


def is_enabled() -> bool:
    value = os.environ.get("CLASSIFY_LLM_ENABLED") or os.environ.get("INTEL_LLM_ENABLED") or ""
    return value.strip().lower() in {"1", "true", "yes"}


def _config() -> dict:
    return {
        "base_url": (
            os.environ.get("INTEL_LLM_BASE_URL")
            or os.environ.get("ANTHROPIC_BASE_URL")
            or "https://api.anthropic.com"
        ).rstrip("/"),
        "api_key": os.environ.get("INTEL_LLM_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or "",
        "model": os.environ.get("INTEL_LLM_MODEL", "claude-3-5-sonnet-latest"),
        "max_tokens": os.environ.get("INTEL_LLM_MAX_TOKENS", "800"),
    }


def _complete(prompt: str) -> Optional[str]:
    cfg = _config()
    if not cfg["api_key"]:
        return None
    url = f"{cfg['base_url']}/v1/messages"
    headers = {
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": cfg["api_key"],
        "authorization": f"Bearer {cfg['api_key']}",
    }
    body = {
        "model": cfg["model"],
        "max_tokens": int(cfg["max_tokens"]),
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    return "\n".join(p.get("text", "") for p in data.get("content", []) if isinstance(p, dict))


def _parse(text: Optional[str]) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def classify_with_llm(name: str, secondary_hint: Optional[List[str]] = None) -> Optional[LLMClassification]:
    if not is_enabled():
        return None
    prompt = (
        f"Program title: {name}\n\n"
        f"Allowed primary_field/secondary_fields values: {_ALLOWED}\n"
        "Return JSON with keys: primary_field, secondary_fields (array), "
        "relevance, confidence (0-1), reason (one sentence)."
    )
    raw = _complete(prompt)
    data = _parse(raw)
    if data is None:
        return None
    try:
        return LLMClassification(**data)
    except ValidationError:
        corrected = _complete(
            "Previous JSON failed validation. Return corrected JSON only with the same keys.\n"
            f"Previous: {raw[:1500] if raw else ''}"
        )
        data2 = _parse(corrected)
        if data2 is None:
            return None
        try:
            return LLMClassification(**data2)
        except ValidationError:
            return None
