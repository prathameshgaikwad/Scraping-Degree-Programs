"""Optional LLM extraction pass.

Disabled by default. Enable with ``INTEL_LLM_ENABLED=1``. The client speaks the
Anthropic Messages API shape, but the base URL / auth are configurable so it can
point at a proxy. Output is validated against the pydantic schema; on validation
failure the model is asked once to correct itself. Malformed output is never
silently accepted.

The deterministic rule-based extractor remains the primary engine. This pass can
add or corroborate fields; merged results still flow through the same
conflict-resolution logic.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import httpx
from pydantic import ValidationError

from .schema import Fact, ProgramIntelligence, Source

_TEMPLATE = {
    "identity": {
        "official_program_name": None,
        "degree_type": None,
        "degree_abbreviation": None,
        "faculty": None,
        "department": None,
    },
    "location": {"city": None, "country": None, "delivery_mode": None},
    "duration": {"value": None, "unit": None, "months": None},
    "credits": {"total": None, "system": None},
    "intakes": [],
    "application": {"opens": None, "deadline": None, "international_deadline": None, "rolling_admission": None},
    "fees": {
        "application_fee": {"required": None, "amount": None, "currency": None},
        "tuition": {"amount": None, "currency": None, "period": None, "international_fee": None},
    },
    "english_requirements": {
        "ielts": {"required": None, "minimum_overall": None},
        "toefl": {"required": None, "minimum_total": None},
        "pte": {"minimum_score": None},
        "duolingo": {"minimum_score": None},
    },
    "gre": {"status": None, "minimum_score": None},
    "gmat": {"status": None, "minimum_score": None},
    "academic_requirements": {
        "background": {"minimum_degree": None},
        "performance": {"minimum_gpa": None, "minimum_grade": None},
    },
    "prerequisites": [],
}

_SYSTEM = (
    "You extract structured facts about a university Master's program from raw "
    "official web page text. Extract ONLY information explicitly supported by the "
    "provided content. Do not infer or guess. Use null for anything not present. "
    "For every non-null scalar field also return an object with keys: value, "
    "evidence_text (exact supporting snippet), confidence (0-1). Distinguish "
    "REQUIRED, OPTIONAL, RECOMMENDED, NOT_REQUIRED; never collapse 'not mentioned' "
    "into 'not required'. Never convert currencies or credit systems. Return JSON only."
)


def is_enabled() -> bool:
    return os.environ.get("INTEL_LLM_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _config() -> Dict[str, str]:
    return {
        "base_url": (
            os.environ.get("INTEL_LLM_BASE_URL")
            or os.environ.get("ANTHROPIC_BASE_URL")
            or "https://api.anthropic.com"
        ).rstrip("/"),
        "api_key": os.environ.get("INTEL_LLM_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or "",
        "model": os.environ.get("INTEL_LLM_MODEL", "claude-3-5-sonnet-latest"),
        "max_tokens": os.environ.get("INTEL_LLM_MAX_TOKENS", "4000"),
    }


class LLMClient:
    def __init__(self) -> None:
        self.cfg = _config()

    def complete(self, content: str) -> str:
        url = f"{self.cfg['base_url']}/v1/messages"
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": self.cfg["api_key"],
            "authorization": f"Bearer {self.cfg['api_key']}",
        }
        body = {
            "model": self.cfg["model"],
            "max_tokens": int(self.cfg["max_tokens"]),
            "system": _SYSTEM,
            "messages": [{"role": "user", "content": content}],
        }
        resp = httpx.post(url, headers=headers, json=body, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        parts = data.get("content", [])
        return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict))


def _strip_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _stamp_sources(model: ProgramIntelligence, source_id: str, page_url: str) -> None:
    for name in type(model).model_fields:
        value = getattr(model, name)
        _stamp_value(value, source_id, page_url)


def _stamp_value(value: Any, source_id: str, page_url: str) -> None:
    from pydantic import BaseModel

    if isinstance(value, Fact):
        if value.is_known() and not value.source_id:
            value.source_id = source_id
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            _stamp_value(getattr(value, name), source_id, page_url)
    elif isinstance(value, list):
        for item in value:
            _stamp_value(item, source_id, page_url)


def extract_with_llm(
    page_text: str,
    source: Source,
    hints: Dict[str, Any],
    max_chars: int = 40000,
) -> Optional[ProgramIntelligence]:
    if not is_enabled():
        return None
    client = LLMClient()
    clipped = (page_text or "")[:max_chars]
    prompt = (
        f"PROGRAM: {hints.get('program_name')}\n"
        f"UNIVERSITY: {hints.get('university')}\n"
        f"COUNTRY: {hints.get('country')}\n"
        f"SOURCE URL: {source.url}\n\n"
        "Return a JSON object with exactly this shape (replace nulls / arrays with "
        "extracted values; omit fields you cannot support):\n"
        f"{json.dumps(_TEMPLATE, indent=2)}\n\n"
        "PAGE TEXT:\n" + clipped
    )
    try:
        raw = client.complete(prompt)
    except Exception:
        return None
    data = _strip_json(raw)
    if data is None:
        return None
    try:
        model = ProgramIntelligence.model_validate(data)
    except ValidationError:
        try:
            correction = (
                "Your previous JSON failed schema validation. Return corrected JSON "
                "only, using the same shape.\nPrevious output:\n" + raw[:4000]
            )
            raw2 = client.complete(correction)
            data2 = _strip_json(raw2)
            if data2 is None:
                return None
            model = ProgramIntelligence.model_validate(data2)
        except Exception:
            return None
    _stamp_sources(model, source.id, source.url)
    return model
