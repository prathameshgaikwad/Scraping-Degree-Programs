"""Optional LLM reasoning for ambiguous eligibility cases.

Disabled by default. Only used when the deterministic result is ``UNCLEAR``.
The LLM may only choose among the defined states and must give a reason; its
output is validated and never produces a probability.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .models import EligibilityState


class LLMState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: EligibilityState
    reason: str


def is_enabled() -> bool:
    value = os.environ.get("MATCH_LLM_ENABLED") or os.environ.get("INTEL_LLM_ENABLED") or ""
    return value.strip().lower() in {"1", "true", "yes"}


def _config() -> dict:
    return {
        "base_url": (os.environ.get("INTEL_LLM_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/"),
        "api_key": os.environ.get("INTEL_LLM_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or "",
        "model": os.environ.get("INTEL_LLM_MODEL", "claude-3-5-sonnet-latest"),
    }


def _complete(prompt: str) -> Optional[str]:
    cfg = _config()
    if not cfg["api_key"]:
        return None
    try:
        resp = httpx.post(
            f"{cfg['base_url']}/v1/messages",
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": cfg["api_key"],
                "authorization": f"Bearer {cfg['api_key']}",
            },
            json={
                "model": cfg["model"],
                "max_tokens": 500,
                "system": (
                    "You assess whether available evidence indicates an applicant satisfies stated "
                    "Master's admission requirements. Never estimate admission probability. "
                    "Return JSON only: {state, reason}. state in "
                    "ELIGIBLE|LIKELY_ELIGIBLE|PREREQUISITE_GAP|UNCLEAR|NOT_ELIGIBLE."
                ),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    return "\n".join(p.get("text", "") for p in data.get("content", []) if isinstance(p, dict))


def reason_with_llm(profile_summary: str, requirements_summary: str) -> Optional[LLMState]:
    if not is_enabled():
        return None
    prompt = f"APPLICANT:\n{profile_summary}\n\nREQUIREMENTS & DIMENSIONS:\n{requirements_summary}\n\nReturn JSON."
    text = _complete(prompt)
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
        data = json.loads(text[start : end + 1])
        return LLMState(**data)
    except (json.JSONDecodeError, ValidationError):
        return None
