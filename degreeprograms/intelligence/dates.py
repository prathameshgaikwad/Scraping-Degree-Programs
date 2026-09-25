"""Date and intake normalization.

Never fabricates a day. If only a month/year is known, ``normalized`` stays
null and month/year are returned separately (Section 56).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Dict, List, Optional

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November",
    12: "December",
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

_NUM_DATE_RE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})\b")
_ISO_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_ISO_MONTH_RE = re.compile(r"\b(\d{4})-(\d{1,2})\b")
_DAY_MONTH_YEAR_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALT})\.?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_MONTH_DAY_YEAR_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(rf"\b({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
_YEAR_MONTH_RE = re.compile(rf"\b(\d{{4}})\s+({_MONTH_ALT})\b", re.IGNORECASE)

TERM_RE = re.compile(
    r"\b(winter|spring|summer|autumn|fall|ws|ss)\s*(?:semester|term|intake|trimester)?\s*"
    r"(\d{4})(?:\s*/\s*(\d{2,4}))?",
    re.IGNORECASE,
)


@dataclass
class ParsedDate:
    raw: str
    normalized: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    term: Optional[str] = None
    precision: str = "UNKNOWN"  # DAY | MONTH | YEAR | TERM | UNKNOWN
    ambiguous: bool = False
    academic_year: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def academic_year_for(year: Optional[int], month: Optional[int]) -> Optional[str]:
    if year is None:
        return None
    if month is not None and month >= 9:
        return f"{year}/{str(year + 1)[-2:]}"
    if month is not None and month <= 8:
        return f"{year - 1}/{str(year)[-2:]}"
    return str(year)


def term_for_month(month: Optional[int]) -> Optional[str]:
    if month is None:
        return None
    if month in (9, 10, 11):
        return "FALL"
    if month in (12, 1, 2):
        return "WINTER"
    if month in (3, 4, 5):
        return "SPRING"
    return "SUMMER"


def _from_iso(y: int, m: int, d: Optional[int], raw: str) -> ParsedDate:
    term = term_for_month(m)
    if d is not None:
        return ParsedDate(
            raw=raw,
            normalized=f"{y:04d}-{m:02d}-{d:02d}",
            year=y,
            month=m,
            day=d,
            term=term,
            precision="DAY",
            academic_year=academic_year_for(y, m),
        )
    return ParsedDate(
        raw=raw,
        year=y,
        month=m,
        term=term,
        precision="MONTH",
        academic_year=academic_year_for(y, m),
    )


def parse_date(raw: str) -> ParsedDate:
    raw = (raw or "").strip()
    parsed = ParsedDate(raw=raw)
    if not raw:
        return parsed

    m = _ISO_RE.search(raw)
    if m:
        return _from_iso(int(m.group(1)), int(m.group(2)), int(m.group(3)), raw)

    m = _DAY_MONTH_YEAR_RE.search(raw)
    if m:
        return _from_iso(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)), raw)

    m = _MONTH_DAY_YEAR_RE.search(raw)
    if m:
        return _from_iso(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)), raw)

    m = _NUM_DATE_RE.search(raw)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        if a > 12 and b <= 12:
            return _from_iso(y, b, a, raw)
        if b > 12 and a <= 12:
            return _from_iso(y, a, b, raw)
        # Ambiguous: do not guess day vs month.
        parsed.ambiguous = True
        parsed.year = y
        parsed.precision = "AMBIGUOUS"
        return parsed

    m = _YEAR_MONTH_RE.search(raw)
    if m:
        return _from_iso(int(m.group(1)), MONTHS[m.group(2).lower()], None, raw)

    m = _MONTH_YEAR_RE.search(raw)
    if m:
        return _from_iso(int(m.group(2)), MONTHS[m.group(1).lower()], None, raw)

    m = _ISO_MONTH_RE.search(raw)
    if m:
        return _from_iso(int(m.group(1)), int(m.group(2)), None, raw)

    m = TERM_RE.search(raw)
    if m:
        token = m.group(1).lower()
        year = int(m.group(2))
        if token in ("autumn", "fall"):
            term, month = "FALL", 9
        elif token == "winter" or token == "ws":
            term, month = "WINTER", 1
        elif token == "spring" or token == "ss":
            term, month = "SPRING", 3
        else:
            term, month = "SUMMER", 6
        # Winter/WS year notation usually refers to the start year (Sep/Oct).
        if term == "WINTER":
            month = 12
        ay = academic_year_for(year, 9 if term == "FALL" else month)
        return ParsedDate(
            raw=raw,
            year=year,
            month=month,
            term=term,
            precision="TERM",
            academic_year=ay,
        )

    m = re.search(r"\b(20\d{2})\b", raw)
    if m:
        year = int(m.group(1))
        return ParsedDate(raw=raw, year=year, precision="YEAR", academic_year=str(year))

    return parsed


_DATE_CANDIDATE_RE = re.compile(
    rf"(\d{{4}}-\d{{1,2}}-\d{{1,2}}"
    rf"|\d{{4}}-\d{{1,2}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTH_ALT})\.?,?\s+\d{{4}}"
    rf"|(?:{_MONTH_ALT})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    rf"|(?:{_MONTH_ALT})\.?,?\s+\d{{4}}"
    rf"|\d{{1,2}}[/.]\d{{1,2}}[/.]\d{{2,4}}"
    rf"|(?:winter|spring|summer|autumn|fall|ws|ss)\s*(?:semester|term|intake|trimester)?\s*\d{{4}}(?:\s*/\s*\d{{2,4}})?"
    rf")",
    re.IGNORECASE,
)


def find_dates(text: str) -> List[ParsedDate]:
    results: List[ParsedDate] = []
    seen = set()
    for match in _DATE_CANDIDATE_RE.finditer(text or ""):
        raw = match.group(1)
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(parse_date(raw))
    return results


def context_window(text: str, start: int, end: int, radius: int = 220) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)].strip()


def sentence_around(text: str, start: int, end: int) -> str:
    """Return the sentence (newline/period bounded) containing [start, end)."""
    left_candidates = [
        text.rfind("\n", 0, start),
        text.rfind(". ", 0, start),
        text.rfind("; ", 0, start),
    ]
    left = max(left_candidates)
    left = left + 1 if left != -1 else 0
    right_candidates = [p for p in (text.find("\n", end), text.find(". ", end)) if p != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return re.sub(r"\s+", " ", text[left:right]).strip()


@dataclass
class DatedMatch:
    parsed: ParsedDate
    context: str
    keyword: str = ""


def find_dates_with_context(
    text: str, keywords: List[str], radius: int = 220
) -> List[DatedMatch]:
    """Find dates whose containing sentence mentions one of ``keywords``."""
    matches: List[DatedMatch] = []
    if not text:
        return matches
    for m in _DATE_CANDIDATE_RE.finditer(text):
        ctx = sentence_around(text, m.start(), m.end())
        ctx_l = ctx.lower()
        hit = next((kw for kw in keywords if kw.lower() in ctx_l), None)
        if hit:
            matches.append(DatedMatch(parsed=parse_date(m.group(1)), context=ctx, keyword=hit))
    return matches
