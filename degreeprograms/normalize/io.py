"""I/O helpers for the normalization layer.

Raw data is read-only. We hash each raw record and the whole input file so that
normalized output is traceable and reprocessing can be skipped when nothing
changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def raw_record_hash(record: Dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return records


def _dump(model: Any) -> Dict[str, Any]:
    if isinstance(model, BaseModel):
        return model.model_dump(mode="json")
    return model


def write_jsonl(path: str, items: Iterable[Any]) -> int:
    ensure_dir(os.path.dirname(path) or ".")
    count = 0
    with open(path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(_dump(item), ensure_ascii=False) + "\n")
            count += 1
    return count


def write_json(path: str, obj: Any) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_dump(obj), fh, ensure_ascii=False, indent=2)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_alias_registry(path: Optional[str]) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {"aliases": {}, "domains": {}}
    data = read_json(path)
    data.setdefault("aliases", {})
    data.setdefault("domains", {})
    return data


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
