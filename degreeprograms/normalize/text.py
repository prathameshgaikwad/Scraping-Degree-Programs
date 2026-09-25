"""Normalization helpers for messy QS source data.

The QS dataset contains:
* multi-valued fields serialized as ``"Europe, Europe, Europe"`` (repeated values
  joined with ``", "``)
* organizational units in the university name (e.g. ``"WMG - Warwick
  Manufacturing Group"``) that belong to a parent university
* ranking strings such as ``"=314"``, ``"601-650"``, ``"1401+"``
* non-ASCII names (``Universität``, ``Łódź``)

Everything here is deterministic and side-effect free.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

# Characters that do not decompose under NFKD but have a conventional ASCII form.
_TRANSLITERATE = {
    "ß": "ss", "ẞ": "SS", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th",
    "Þ": "TH", "ł": "l", "Ł": "L", "ħ": "h", "Ħ": "H", "ı": "i", "İ": "I",
    "ŋ": "n", "Ŋ": "N", "ſ": "s", "ĸ": "k", "ƒ": "f",
    "“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "−": "-",
}

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")


def clean_unicode(value: Optional[str]) -> str:
    """Normalize unicode, strip zero-width characters, collapse whitespace."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    value = _ZERO_WIDTH_RE.sub("", value)
    value = value.replace("\xa0", " ")
    return _WS_RE.sub(" ", value).strip()


def ascii_fold(value: str) -> str:
    """Best-effort transliteration of a string to ASCII."""
    value = clean_unicode(value)
    for src, dst in _TRANSLITERATE.items():
        value = value.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slugify(value: str, max_len: int = 120) -> str:
    value = ascii_fold(value).lower()
    value = _NON_ALNUM_RE.sub("-", value).strip("-")
    return value[:max_len].strip("-") or "unknown"


def normalize_name(value: str) -> str:
    """Normalized form used for dedup keys and matching (not for display)."""
    value = ascii_fold(value).lower()
    value = _NON_ALNUM_RE.sub(" ", value)
    return _WS_RE.sub(" ", value).strip()


def split_multi(value: Optional[str]) -> List[str]:
    """Split a comma-joined multi-value field, de-duplicate, preserve order."""
    if not value:
        return []
    parts = [clean_unicode(p) for p in str(value).split(",")]
    seen = set()
    out: List[str] = []
    for part in parts:
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


def first_multi(value: Optional[str]) -> Optional[str]:
    parts = split_multi(value)
    return parts[0] if parts else None


# ---------------------------------------------------------------------------
# Degree type
# ---------------------------------------------------------------------------

# Longest/most specific patterns first.
_DEGREE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bexecutive\s+master\s+of\s+business\s+administration\b", "MBA"),
    (r"\bmaster\s+of\s+business\s+administration\b", "MBA"),
    (r"\bmaster\s+of\s+science\b", "MSC"),
    (r"\bmaster\s+of\s+arts\b", "MA"),
    (r"\bmaster\s+of\s+engineering\b", "MENG"),
    (r"\bmaster\s+of\s+research\b", "MRES"),
    (r"\bmaster\s+of\s+philosophy\b", "MPHIL"),
    (r"\bmaster\s+of\s+laws\b", "LLM"),
    (r"\bmaster\s+of\s+public\s+health\b", "MPH"),
    (r"\bmaster\s+of\s+education\b", "MED"),
    (r"\bmaster\s+of\s+architecture\b", "MARCH"),
    (r"\bpostgraduate\s+diploma\b", "PGDIP"),
    (r"\bpostgraduate\s+certificate\b", "PGCERT"),
    (r"\bm\.?sc\b", "MSC"),
    (r"\bm\.?res\b", "MRES"),
    (r"\bm\.?phil\b", "MPHIL"),
    (r"\bm\.?eng\b", "MENG"),
    (r"\bm\.?math\b", "MMATH"),
    (r"\bm\.?phys\b", "MPHYS"),
    (r"\bm\.?ed\b", "MED"),
    (r"\bm\.?fin\b", "MFIN"),
    (r"\bmba\b", "MBA"),
    (r"\bllm\b", "LLM"),
    (r"\bmpa\b", "MPA"),
    (r"\bmpp\b", "MPP"),
    (r"\bmph\b", "MPH"),
    (r"\bmfa\b", "MFA"),
    (r"\bpgdip\b", "PGDIP"),
    (r"\bpgcert\b", "PGCERT"),
    (r"\bms\b", "MS"),
    (r"\bma\b", "MA"),
    (r"\bmres\b", "MRES"),
]


def parse_degree_type(value: str) -> str:
    """Return a canonical degree type token, or ``UNKNOWN``."""
    text = clean_unicode(value)
    for pattern, code in _DEGREE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return code
    if re.search(r"\bmaster'?s?\b", text, re.IGNORECASE):
        return "MASTER"
    return "UNKNOWN"


def extract_degree_tokens(value: str) -> List[str]:
    """Return every distinct degree token found, most specific first."""
    text = clean_unicode(value)
    found: List[str] = []
    for pattern, code in _DEGREE_PATTERNS:
        if code in found:
            continue
        if re.search(pattern, text, re.IGNORECASE):
            found.append(code)
    return found


# ---------------------------------------------------------------------------
# Program format
# ---------------------------------------------------------------------------

_FORMAT_RULES: List[Tuple[str, List[str]]] = [
    ("EXECUTIVE", [r"\bexecutive\b"]),
    ("ONLINE", [r"\bonline\b", r"\bdistance\s+learning\b", r"\be-?learning\b", r"\bremote\b"]),
    ("HYBRID", [r"\bhybrid\b", r"\bblended\b"]),
    ("PART_TIME", [r"\bpart[- ]time\b", r"\bweekend\b", r"\bevening\b"]),
    ("FULL_TIME", [r"\bfull[- ]time\b"]),
]


def parse_program_format(value: str) -> str:
    """Infer the delivery format from a title/description, else ``UNKNOWN``."""
    text = clean_unicode(value)
    for code, patterns in _FORMAT_RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return code
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

_RANGE_RE = re.compile(r"^(\d{1,4})\s*[-–]\s*(\d{1,4})$")
_PLUS_RE = re.compile(r"^(\d{1,4})\s*\+$")
_INT_RE = re.compile(r"^=?\s*(\d{1,4})$")


def parse_ranking(raw: Optional[str]) -> dict:
    """Parse a QS ranking string into structured fields.

    Returns a dict with ``university_rank`` (int or None), ``rank_display``,
    ``rank_low``, ``rank_high``, ``tied``, ``is_range``, ``is_plus``.
    Never guesses a precise rank for ranges.
    """
    value = clean_unicode(raw)
    result = {
        "university_rank": None,
        "rank_display": value or None,
        "rank_low": None,
        "rank_high": None,
        "tied": False,
        "is_range": False,
        "is_plus": False,
    }
    if not value:
        return result

    m = _RANGE_RE.match(value)
    if m:
        result["rank_low"] = int(m.group(1))
        result["rank_high"] = int(m.group(2))
        result["is_range"] = True
        return result

    m = _PLUS_RE.match(value)
    if m:
        result["rank_low"] = int(m.group(1))
        result["is_plus"] = True
        return result

    if value.startswith("="):
        result["tied"] = True

    m = _INT_RE.match(value)
    if m:
        result["university_rank"] = int(m.group(1))
    return result


# ---------------------------------------------------------------------------
# QS URL parsing
# ---------------------------------------------------------------------------

def qs_path_segments(url: Optional[str]) -> List[str]:
    if not url:
        return []
    from urllib.parse import urlparse

    path = urlparse(str(url)).path
    return [seg for seg in path.strip("/").split("/") if seg]


def base_university_slug(university_url: Optional[str]) -> Optional[str]:
    """Extract the parent QS university slug from a university/program URL.

    ``/universities/university-warwick/wmg-warwick-manufacturing-group``
    -> ``university-warwick``
    """
    segments = qs_path_segments(university_url)
    if len(segments) >= 2 and segments[0] == "universities":
        return segments[1]
    return None
