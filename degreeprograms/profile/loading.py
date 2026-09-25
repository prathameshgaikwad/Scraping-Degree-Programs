"""Applicant profile loading (YAML or JSON).

Accepts either a bare profile document or one wrapped in a top-level
``applicant:`` key (as in the spec example).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

import yaml

from .models import ApplicantProfile


def load_profile_dict(data: Dict[str, Any]) -> ApplicantProfile:
    if not isinstance(data, dict):
        raise ValueError("Applicant profile must be a mapping")
    if "applicant" in data and isinstance(data["applicant"], dict):
        data = data["applicant"]
    return ApplicantProfile(**data)


def load_profile(path: str) -> ApplicantProfile:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif ext == ".json":
        data = json.loads(text)
    else:
        # Try JSON first, then YAML.
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    return load_profile_dict(data or {})
