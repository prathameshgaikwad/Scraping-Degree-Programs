"""Persistence helpers for Program Intelligence objects."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from .schema import ProgramIntelligence


def slugify(value: str, max_len: int = 80) -> str:
    value = (value or "program").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:max_len] or "program"


def resolve_path(out_dir: str, filename: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)


def save_intelligence(
    obj: ProgramIntelligence,
    out_dir: str,
    identifier: Optional[str] = None,
) -> str:
    if not identifier:
        name = obj.identity.program_name.value or obj.identity.official_program_name.value or "program"
        uni = obj.university.name.value or "university"
        identifier = f"{slugify(uni)}__{slugify(str(name))}"
    path = resolve_path(out_dir, f"{identifier}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj.model_dump(mode="json"), fh, ensure_ascii=False, indent=2)
    return path


def save_completeness_summary(objects, out_dir: str, filename: str = "_completeness.json") -> str:
    rows = []
    for obj in objects:
        rows.append(
            {
                "program": obj.identity.official_program_name.value
                or obj.identity.program_name.value,
                "university": obj.university.name.value,
                "completeness": obj.completeness.model_dump(mode="json"),
                "extraction_status": obj.extraction_status,
                "sources": len(obj.sources),
            }
        )
    path = resolve_path(out_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    return path
