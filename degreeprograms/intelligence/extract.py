"""Rule-based fact extraction with evidence attachment.

The extractor is deliberately conservative: every value requires an explicit
keyword-anchored match in the source text, and every value carries the source
id plus the surrounding evidence span. Anything not matched stays UNKNOWN.

This is the deterministic core. An optional LLM pass (see ``llm.py``) can add
or corroborate facts afterwards, but the pipeline works without it.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .dates import (
    MONTH_NAMES,
    academic_year_for,
    find_dates_with_context,
    parse_date,
    term_for_month,
)
from .html_text import CleanPage
from .schema import (
    AcademicBackground,
    AcademicPerformance,
    AcademicRequirements,
    ApplicationFee,
    Credits,
    DeadlineRecord,
    Duration,
    EnglishRequirements,
    Fact,
    Intake,
    PageType,
    Prerequisite,
    ProgramIntelligence,
    Source,
    SourceType,
    StandardizedTest,
    Study,
    TestScore,
    TestStatus,
    Tuition,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

CURRENCY_CODES = {
    "eur": "EUR", "gbp": "GBP", "usd": "USD", "chf": "CHF", "sek": "SEK",
    "nok": "NOK", "dkk": "DKK", "cad": "CAD", "aud": "AUD", "nzd": "NZD",
    "sgd": "SGD", "hkd": "HKD", "jpy": "JPY", "inr": "INR", "cny": "CNY",
    "rmb": "CNY", "krw": "KRW", "zar": "ZAR", "brl": "BRL", "mxn": "MXN",
}
SYMBOL_TO_CODE = {"€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}

# When only a "$" symbol is present, infer the dollar variant from the country.
DOLLAR_BY_COUNTRY = {
    "canada": "CAD", "australia": "AUD", "new zealand": "NZD",
    "singapore": "SGD", "hong kong": "HKD", "united states": "USD",
    "usa": "USD", "us": "USD", "united states of america": "USD",
}

# Plausible score ranges used to reject section scores / stray numbers.
TEST_BOUNDS = {
    "IELTS": (4.0, 9.5),
    "TOEFL": (32.0, 120.0),
    "PTE": (30.0, 90.0),
    "Duolingo": (50.0, 160.0),
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CODE_ALT = "EUR|GBP|USD|CHF|SEK|NOK|DKK|CAD|AUD|NZD|SGD|HKD|JPY|INR|CNY|RMB|KRW|ZAR|BRL|MXN"
_MONEY_RE = re.compile(
    rf"(?:(?P<pre_code>{_CODE_ALT})\s*)?"
    r"(?P<sym>€|£|\$|¥|₹)?\s*"
    r"(?P<amt>\d[\d.,]*)\s*"
    rf"(?P<code>{_CODE_ALT})?",
    re.IGNORECASE,
)


def evidence_span(text: str, start: int, end: int, radius: int = 200) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = text[left:right].strip()
    return re.sub(r"\s+", " ", snippet)


def keyword_span(text: str, keyword: str, radius: int = 220) -> Tuple[int, int]:
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return -1, -1
    return idx, idx + len(keyword)


def sentence_at(text: str, index: int) -> str:
    if index < 0:
        return ""
    start = text.rfind("\n", 0, index)
    start2 = max(text.rfind(". ", 0, index), text.rfind("; ", 0, index))
    start = max(start, start2) + 1
    ends = [e for e in (text.find("\n", index), text.find(". ", index)) if e != -1]
    end = min(ends) + 1 if ends else len(text)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def sentence_block(text: str, index: int, count: int = 2, cap: int = 500) -> str:
    """Return the sentence containing ``index`` plus up to ``count-1`` following."""
    if index < 0:
        return ""
    start = max(text.rfind("\n", 0, index), text.rfind(". ", 0, index), text.rfind("; ", 0, index))
    start = start + 1 if start != -1 else 0
    segment = text[start : start + cap]
    parts = re.split(r"(?<=[.!?])\s+|\n+", segment)
    return " ".join(p.strip() for p in parts[:count] if p.strip())


def parse_amount(raw: str) -> Optional[float]:
    if not raw:
        return None
    s = raw.strip()
    # Remove spaces (thin spaces etc).
    s = re.sub(r"\s", "", s)
    if "." in s and "," in s:
        # Last separator is the decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 3 and len(parts) > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 and len(parts) > 1 and len(parts[0]) <= 3:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def detect_currency(text: str, match: "re.Match[str]", country: Optional[str]) -> Optional[str]:
    code = match.groupdict().get("pre_code") or match.groupdict().get("code")
    if code:
        return CURRENCY_CODES.get(code.lower(), code.upper())
    sym = match.group("sym")
    if not sym:
        return None
    if sym in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[sym]
    if sym == "$":
        code = DOLLAR_BY_COUNTRY.get((country or "").strip().lower())
        return code or "USD"
    return sym


_NAME_STOPWORDS = {
    "master", "masters", "of", "in", "the", "and", "a", "an", "msc", "ms", "ma",
    "mba", "meng", "mphil", "llm", "science", "sciences", "arts", "studies",
    "programme", "program", "degree", "postgraduate", "graduate",
}


def _tokens(value: str) -> List[str]:
    return [
        t
        for t in re.split(r"[^a-z0-9]+", (value or "").lower())
        if t and t not in _NAME_STOPWORDS
    ]


def _known(value, source_id, evidence, confidence=0.8, raw=None) -> Fact:
    return Fact.known(
        value=value,
        source_id=source_id,
        evidence_text=evidence,
        confidence=confidence,
        raw=raw,
    )


def _has_currency_marker(match: "re.Match[str]") -> bool:
    d = match.groupdict()
    return bool(d.get("sym") or d.get("pre_code") or d.get("code"))


def _money_matches(text: str) -> List[Tuple[int, int, float, Optional[str], str]]:
    out = []
    for m in _MONEY_RE.finditer(text):
        if not _has_currency_marker(m) and "." not in m.group("amt"):
            # bare integer without currency marker -> too weak
            continue
        amount = parse_amount(m.group("amt"))
        if amount is None:
            continue
        out.append((m.start(), m.end(), amount, None, m.group(0)))
    return out


# ---------------------------------------------------------------------------
# extractor
# ---------------------------------------------------------------------------

DEGREE_MAP = {
    "msc": "MSc", "m.sc": "MSc", "ms": "MS", "m.s": "MS", "ma": "MA",
    "m.a": "MA", "meng": "MEng", "m.eng": "MEng", "mba": "MBA",
    "mphil": "MPhil", "llm": "LLM", "mres": "MRes", "mmath": "MMath",
    "mphys": "MPhys", "mfin": "MFin", "macc": "MAcc", "mph": "MPH",
    "med": "MEd", "march": "MArch", "meng.": "MEng",
}

DEGREE_PHRASES = {
    "master of science": "MSc",
    "master of arts": "MA",
    "master of engineering": "MEng",
    "master of business administration": "MBA",
    "master of philosophy": "MPhil",
    "master of research": "MRes",
    "master of laws": "LLM",
    "master of public health": "MPH",
    "master of education": "MEd",
    "executive master of business administration": "Executive MBA",
}

PREREQ_CATEGORIES: Dict[str, List[str]] = {
    "PROGRAMMING": ["programming", "coding", "software development", "object-oriented", "python", "java", "c++"],
    "COMPUTER_SCIENCE": ["computer science", "informatics", "computer engineering"],
    "ALGORITHMS": ["algorithms", "algorithm design"],
    "DATA_STRUCTURES": ["data structures"],
    "MATHEMATICS": ["mathematics", "maths", "mathematical"],
    "LINEAR_ALGEBRA": ["linear algebra"],
    "CALCULUS": ["calculus", "real analysis"],
    "PROBABILITY": ["probability", "probability theory"],
    "STATISTICS": ["statistics", "statistical"],
    "DATABASES": ["database", "databases", "sql"],
    "OPERATING_SYSTEMS": ["operating systems"],
    "NETWORKS": ["computer networks", "networking"],
    "MACHINE_LEARNING": ["machine learning"],
    "ARTIFICIAL_INTELLIGENCE": ["artificial intelligence"],
    "PHYSICS": ["physics"],
    "ENGINEERING": ["engineering"],
    "ECONOMICS": ["economics", "econometrics"],
}

INTAKE_TERMS = [
    "september", "october", "january", "february", "march", "april", "may",
    "june", "july", "august", "november", "december",
    "fall", "autumn", "spring", "summer", "winter", "ws", "ss",
]

OPEN_KEYWORDS = [
    "applications open", "application opens", "application opening",
    "open from", "opening date", "portal opens",
    "applications are open", "opens on",
]
DEADLINE_KEYWORDS = [
    "application deadline", "deadline", "apply by", "applications close",
    "closing date", "last date to apply", "last day to apply", "applications close on",
    "submit your application by", "latest by",
]
LATE_KEYWORDS = ["late application", "late deadline", "late round"]
INTL_KEYWORDS = ["international", "non-eu", "overseas", "visa"]
SCHOLARSHIP_DEADLINE_KEYWORDS = ["scholarship deadline", "funding deadline", "scholarship applications"]
DEPOSIT_KEYWORDS = ["deposit deadline", "deposit due", "pay the deposit", "tuition deposit"]
ENROLLMENT_KEYWORDS = ["enrollment deadline", "enrolment deadline", "accept your offer by"]


class PageExtractor:
    def __init__(self, source: Source, country_hint: Optional[str] = None):
        self.source = source
        self.country_hint = country_hint
        self.sid = source.id

    # -- public --------------------------------------------------------------
    def extract(
        self,
        page: CleanPage,
        hints: Optional[Dict] = None,
        is_program_page: bool = False,
    ) -> ProgramIntelligence:
        hints = hints or {}
        obj = ProgramIntelligence()
        text = page.text or ""
        tables_text = "\n".join(t.as_text() for t in page.tables)

        self._identity(obj, page, text, hints, is_program_page)
        self._location(obj, text, hints)
        self._study(obj, text)
        self._duration(obj, text)
        self._intakes(obj, text)
        self._application(obj, text)
        self._fees(obj, text, tables_text)
        self._english(obj, text)
        self._standardized_tests(obj, text)
        self._academic(obj, text)
        self._prerequisites(obj, text)
        return obj

    # -- identity ------------------------------------------------------------
    def _identity(
        self,
        obj: ProgramIntelligence,
        page: CleanPage,
        text: str,
        hints: Dict,
        is_program_page: bool,
    ) -> None:
        name = hints.get("program_name")
        if name:
            obj.identity.program_name = _known(name, "input", "QS program record", 0.7)
        if is_program_page:
            official = None
            if page.title:
                official = page.title.split("|")[0].split(" - ")[0].strip()
            if not official:
                first_lines = [l for l in text.split("\n")[:20] if 5 < len(l) < 120]
                official = first_lines[0] if first_lines else None
            if official:
                hint_name = hints.get("program_name") or ""
                hint_tokens = set(_tokens(hint_name))
                official_tokens = set(_tokens(official))
                looks_generic = not re.search(
                    r"master|msc|m\.sc|\bms\b|\bma\b|mba|meng|mphil|llm|mres",
                    official,
                    re.IGNORECASE,
                )
                if hint_tokens and not (hint_tokens & official_tokens) and looks_generic:
                    official = None
            if official:
                obj.identity.official_program_name = _known(
                    official, self.sid, sentence_at(text, 0) or official, 0.75
                )

        deg_abbr, deg_phrase, evidence = self._degree_type(page.title + "\n" + text[:5000])
        if deg_abbr:
            obj.identity.degree_abbreviation = _known(deg_abbr, self.sid, evidence, 0.85, raw=deg_phrase)
            obj.identity.degree_type = _known(deg_abbr, self.sid, evidence, 0.85, raw=deg_phrase)
        if re.search(r"master", (page.title + text[:3000]), re.IGNORECASE):
            obj.identity.degree_level = _known("MASTER", self.sid, evidence or "Master", 0.8)
        if re.search(r"postgraduate diploma|pgdip|pgd", text[:5000], re.IGNORECASE):
            obj.identity.degree_level = _known("POSTGRADUATE_DIPLOMA", self.sid, "postgraduate diploma", 0.7)

        university = hints.get("university")
        if university:
            obj.university.name = _known(university, "input", "QS program record", 0.7)
        if hints.get("university_domain"):
            obj.university.official_domain = _known(
                hints["university_domain"], "input", "QS program record", 0.6
            )

    def _degree_type(self, text: str) -> Tuple[Optional[str], Optional[str], str]:
        lowered = text.lower()
        for phrase, abbr in DEGREE_PHRASES.items():
            idx = lowered.find(phrase)
            if idx != -1:
                return abbr, text[idx : idx + len(phrase)], sentence_at(text, idx)
        m = re.search(
            r"\b(MSc|M\.Sc\.|MS|M\.S\.|MA|M\.A\.|MEng|M\.Eng\.|MBA|MPhil|LLM|MRes|MMath|MPhys|MFin|MAcc|MPH|MEd|MArch)\b",
            text,
        )
        if m:
            key = m.group(1).lower().rstrip(".")
            abbr = DEGREE_MAP.get(key) or DEGREE_MAP.get(key.replace(".", ""))
            return abbr, m.group(1), sentence_at(text, m.start())
        return None, None, ""

    # -- location ------------------------------------------------------------
    def _location(self, obj: ProgramIntelligence, text: str, hints: Dict) -> None:
        if hints.get("city"):
            obj.location.city = _known(hints["city"], "input", "QS program record", 0.6)
        if hints.get("country") or self.country_hint:
            country = hints.get("country") or self.country_hint
            obj.location.country = _known(country, "input", "QS program record", 0.6)
        if re.search(r"\bon[- ]campus\b|campus-based", text, re.IGNORECASE):
            obj.location.delivery_mode = _known("ON_CAMPUS", self.sid, sentence_at(text, text.lower().find("campus")), 0.6)
        elif re.search(r"\bonline\b", text, re.IGNORECASE):
            idx = text.lower().find("online")
            obj.location.delivery_mode = _known("ONLINE", self.sid, sentence_at(text, idx), 0.5)

    # -- study mode ----------------------------------------------------------
    def _study(self, obj: ProgramIntelligence, text: str) -> None:
        lowered = text.lower()
        if "full-time" in lowered or "full time" in lowered:
            obj.study.study_mode = _known("FULL_TIME", self.sid, sentence_at(text, lowered.find("full-time") if "full-time" in lowered else lowered.find("full time")), 0.6)
        if re.search(r"part[- ]time", text, re.IGNORECASE):
            m = re.search(r"part[- ]time", text, re.IGNORECASE)
            if obj.study.study_mode.value is None:
                obj.study.study_mode = _known("PART_TIME", self.sid, sentence_at(text, m.start()), 0.6)
        if re.search(r"hybrid", text, re.IGNORECASE):
            m = re.search(r"hybrid", text, re.IGNORECASE)
            obj.study.delivery = _known("HYBRID", self.sid, sentence_at(text, m.start()), 0.6)
        if re.search(r"distance learning", text, re.IGNORECASE):
            m = re.search(r"distance learning", text, re.IGNORECASE)
            obj.study.delivery = _known("DISTANCE", self.sid, sentence_at(text, m.start()), 0.6)
        if re.search(r"executive", text, re.IGNORECASE) and re.search(r"executive master|executive mba|executive programme", text, re.IGNORECASE):
            m = re.search(r"executive", text, re.IGNORECASE)
            obj.study.study_mode = _known("EXECUTIVE", self.sid, sentence_at(text, m.start()), 0.6)

    # -- duration / credits --------------------------------------------------
    def _duration(self, obj: ProgramIntelligence, text: str) -> None:
        word_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "half": 0.5}
        pattern = re.compile(
            r"\b(one|two|three|four|five|six|\d{1,2}(?:\.\d)?)\s*[- ]?\s*"
            r"(?:to\s+\w{1,6}\s*[- ]?)?"
            r"(years?|yrs?|months?|semesters?|terms?)\b",
            re.IGNORECASE,
        )
        positive = ["duration", "period of study", "program length", "programme length",
                    "takes", "lasts", "full-time", "full time", "fulltime", "study program",
                    "programme runs", "standard period"]
        negative = ["waiver", "tuition", "fee", "scholarship", "per semester", "each semester",
                    "semester fee", "before the", "already enrolled", "student information",
                    "at most", "more than", "up to", "within at most", "nominal duration",
                    "maximum of", "within"]
        best = None
        best_score = -999
        for m in pattern.finditer(text):
            token = m.group(1).lower()
            value = word_num.get(token)
            if value is None:
                try:
                    value = float(token)
                except ValueError:
                    continue
            ctx = sentence_at(text, m.start())
            if len(ctx) < 15:
                ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 120) : m.end() + 120]).strip()
            low = ctx.lower()
            score = 0
            score += 3 * sum(1 for kw in positive if kw in low)
            score -= 5 * sum(1 for kw in negative if kw in low)
            if score > best_score:
                best_score = score
                best = (value, m.group(2).lower().rstrip("s"), ctx, m.group(0))
        if best and best_score > 0:
            value, unit, ctx, raw = best
            obj.duration.value = _known(value, self.sid, ctx, 0.75, raw=raw)
            obj.duration.unit = _known(unit, self.sid, ctx, 0.75)
            if unit.startswith("year"):
                obj.duration.months = _known(round(value * 12), self.sid, ctx, 0.6)
            elif unit.startswith("month"):
                obj.duration.months = _known(round(value), self.sid, ctx, 0.7)
            elif unit.startswith("semester"):
                obj.duration.semesters = _known(round(value), self.sid, ctx, 0.7)
        m = re.search(r"\b(\d{2,3})\s*(ECTS|ECTS credits|credits|credit points|CP)\b", text, re.IGNORECASE)
        if m:
            obj.credits.total = _known(float(m.group(1)), self.sid, sentence_at(text, m.start()), 0.8)
            system = "ECTS" if "ects" in m.group(2).lower() else "CREDITS"
            obj.credits.system = _known(system, self.sid, sentence_at(text, m.start()), 0.8)

    # -- intakes -------------------------------------------------------------
    def _intakes(self, obj: ProgramIntelligence, text: str) -> None:
        found: List[Intake] = []
        seen = set()
        positive = re.compile(
            r"intake|start|begins?|commenc|admission|apply|application|enroll|entry",
            re.IGNORECASE,
        )
        negative = re.compile(
            r"\bfee\b|scholarship|waiver|student information|before the|already enrolled|"
            r"available on|semester ticket|tuition",
            re.IGNORECASE,
        )
        for m in re.finditer(
            r"\b(" + "|".join(INTAKE_TERMS) + r")\s*(?:semester|term|intake|trimester)?\s*\(?(20\d{2})\)?"
            r"(?:\s*/\s*(\d{2,4}))?",
            text,
            re.IGNORECASE,
        ):
            raw = m.group(0)
            ctx = sentence_at(text, m.start())
            if negative.search(ctx) or not positive.search(ctx):
                continue
            parsed = parse_date(raw)
            if parsed.year and parsed.year < datetime.now().year - 1:
                continue  # past intake cycle
            key = (parsed.term, parsed.year, parsed.month)
            if key in seen:
                continue
            seen.add(key)
            intake = Intake(
                intake_name=m.group(1).title(),
                term=parsed.term or term_for_month(parsed.month),
                start_date=parsed.normalized,
                start_month=MONTH_NAMES.get(parsed.month) if parsed.month else None,
                start_year=parsed.year,
                academic_year=parsed.academic_year,
                raw=raw,
                source_id=self.sid,
                evidence_text=ctx,
                confidence=0.7,
            )
            found.append(intake)
        # Term-only intakes without a year, e.g. "both winter and summer semester".
        term_only_positive = re.compile(
            r"intake|start of degree|admission|application period|enrol|possible for", re.IGNORECASE
        )
        for m in re.finditer(
            r"\b(winter|summer|spring|fall|autumn)\s+(semester|intake|term)\b",
            text,
            re.IGNORECASE,
        ):
            ctx = sentence_at(text, m.start())
            if negative.search(ctx) or not term_only_positive.search(ctx):
                continue
            token = m.group(1).lower()
            term = {"winter": "WINTER", "summer": "SUMMER", "spring": "SPRING",
                    "fall": "FALL", "autumn": "FALL"}[token]
            key = (term, None, None)
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Intake(
                    intake_name=m.group(1).title(),
                    term=term,
                    raw=m.group(0),
                    source_id=self.sid,
                    evidence_text=ctx,
                    confidence=0.6,
                )
            )
        periods = self._application_periods(text, seen)
        for period in periods:
            existing = next(
                (i for i in found if i.term == period.term and not i.application_deadline),
                None,
            )
            if existing is not None:
                existing.application_open_date = period.application_open_date
                existing.application_deadline = period.application_deadline
                if not existing.raw:
                    existing.raw = period.raw
            else:
                found.append(period)
        obj.intakes = found

    def _application_periods(self, text: str, seen: set) -> List[Intake]:
        """Capture recurring application windows like 'Winter semester: 01.02.-31.05.'."""
        results: List[Intake] = []
        block_idx = text.lower().find("application period")
        if block_idx == -1:
            return results
        block = text[block_idx : block_idx + 400]
        period_re = re.compile(
            r"(\d{1,2})\.(\d{1,2})\.?\s*[\u2013\u2014-]\s*(\d{1,2})\.(\d{1,2})\.?"
        )
        term_re = re.compile(r"\b(winter|summer|spring|fall|autumn)\b", re.IGNORECASE)
        for m in period_re.finditer(block):
            abs_start = block_idx + m.start()
            prefix = text[max(0, abs_start - 90) : abs_start].lower()
            terms = term_re.findall(prefix)
            term = None
            if terms:
                token = terms[-1].lower()
                term = {"winter": "WINTER", "summer": "SUMMER", "spring": "SPRING",
                        "fall": "FALL", "autumn": "FALL"}[token]
            raw = m.group(0)
            key = (term, None, ("window", raw))
            if key in seen:
                continue
            seen.add(key)
            open_raw = f"{int(m.group(1)):02d}.{int(m.group(2)):02d}."
            close_raw = f"{int(m.group(3)):02d}.{int(m.group(4)):02d}."
            results.append(
                Intake(
                    intake_name=term.title() if term else None,
                    term=term,
                    application_open_date=open_raw,
                    application_deadline=close_raw,
                    raw=raw,
                    source_id=self.sid,
                    evidence_text=sentence_at(text, abs_start),
                    confidence=0.7,
                )
            )
        return results

    # -- application window / deadlines -------------------------------------
    def _application(self, obj: ProgramIntelligence, text: str) -> None:
        deadlines: List[DeadlineRecord] = []

        def add(dtype: str, matches, source_priority: int = 0):
            for match in matches:
                deadlines.append(
                    DeadlineRecord(
                        type=dtype,
                        date=match.parsed.normalized,
                        raw=match.parsed.raw,
                        condition=match.context if "international" in match.context.lower() else None,
                        academic_year=match.parsed.academic_year,
                        source_id=self.sid,
                        evidence_text=match.context,
                        confidence=0.8,
                    )
                )

        open_matches = find_dates_with_context(text, OPEN_KEYWORDS)
        deadline_matches = find_dates_with_context(text, DEADLINE_KEYWORDS)
        late_matches = find_dates_with_context(text, LATE_KEYWORDS)
        intl_matches = find_dates_with_context(text, DEADLINE_KEYWORDS)
        deposit_matches = find_dates_with_context(text, DEPOSIT_KEYWORDS)
        enrollment_matches = find_dates_with_context(text, ENROLLMENT_KEYWORDS)
        scholarship_matches = find_dates_with_context(text, SCHOLARSHIP_DEADLINE_KEYWORDS)

        add("APPLICATION_OPEN", open_matches)
        add("APPLICATION", deadline_matches)
        add("LATE_APPLICATION", late_matches)
        add("INTERNATIONAL_APPLICATION", [m for m in intl_matches if "international" in m.context.lower()])
        add("DEPOSIT", deposit_matches)
        add("ENROLLMENT", enrollment_matches)
        add("SCHOLARSHIP", scholarship_matches)

        # Deduplicate identical (type, raw).
        deduped: List[DeadlineRecord] = []
        keys = set()
        for d in deadlines:
            key = (d.type, d.raw or "")
            if key in keys:
                continue
            keys.add(key)
            deduped.append(d)
        obj.deadlines = deduped

        def first_of(dtype: str) -> Optional[DeadlineRecord]:
            return next((d for d in deduped if d.type == dtype), None)

        open_rec = first_of("APPLICATION_OPEN")
        if open_rec:
            obj.application.opens = open_rec.date or open_rec.raw
            obj.application.source_id = self.sid
            obj.application.evidence_text = open_rec.evidence_text
            obj.application.raw = open_rec.raw
        deadline_rec = first_of("APPLICATION")
        if deadline_rec:
            obj.application.deadline = deadline_rec.date or deadline_rec.raw
            obj.application.academic_year = deadline_rec.academic_year
            obj.application.source_id = self.sid
            obj.application.evidence_text = deadline_rec.evidence_text
            obj.application.raw = deadline_rec.raw
        intl_rec = first_of("INTERNATIONAL_APPLICATION")
        if intl_rec:
            obj.application.international_deadline = intl_rec.date or intl_rec.raw
        # Fall back to recurring application windows captured on intakes.
        if obj.application.opens is None:
            intake_open = next((i for i in obj.intakes if i.application_open_date), None)
            if intake_open:
                obj.application.opens = intake_open.application_open_date
                obj.application.source_id = obj.application.source_id or self.sid
                obj.application.evidence_text = obj.application.evidence_text or intake_open.evidence_text
                obj.application.raw = obj.application.raw or intake_open.raw
        if obj.application.deadline is None:
            intake_close = next((i for i in obj.intakes if i.application_deadline), None)
            if intake_close:
                obj.application.deadline = intake_close.application_deadline
                obj.application.source_id = obj.application.source_id or self.sid
                obj.application.evidence_text = obj.application.evidence_text or intake_close.evidence_text
                obj.application.raw = obj.application.raw or intake_close.raw
        if re.search(r"rolling (?:admissions?|basis|intake)|applications? (?:are )?(?:reviewed|accepted) on a rolling", text, re.IGNORECASE):
            m = re.search(r"rolling[^.\n]{0,60}", text, re.IGNORECASE)
            obj.application.rolling_admission = True
            obj.application.source_id = obj.application.source_id or self.sid
            obj.application.evidence_text = obj.application.evidence_text or sentence_at(text, m.start())

    # -- fees ----------------------------------------------------------------
    def _fees(self, obj: ProgramIntelligence, text: str, tables_text: str) -> None:
        blob = text + "\n" + tables_text

        # Application fee
        af = ApplicationFee()
        m = re.search(r"(application|processing|admission)\s+fee[^.\n]{0,120}", blob, re.IGNORECASE)
        if m:
            ev = sentence_at(blob, m.start())
            if re.search(r"no\s+(?:application|processing|admission)\s+fee|fee\s+is\s+waived|no\s+fee", ev, re.IGNORECASE):
                af.required = _known(False, self.sid, ev, 0.85)
                af.amount = _known(0, self.sid, ev, 0.8)
            else:
                money = _MONEY_RE.search(ev)
                if money:
                    amount = parse_amount(money.group("amt"))
                    af.required = _known(True, self.sid, ev, 0.85)
                    af.amount = _known(amount, self.sid, ev, 0.85, raw=money.group(0))
                    cur = detect_currency(ev, money, self.country_hint)
                    if cur:
                        af.currency = _known(cur, self.sid, ev, 0.8)
                else:
                    af.required = _known(True, self.sid, ev, 0.6)
            af.source_id = self.sid
            af.evidence_text = ev
            af.confidence = 0.8
        obj.fees.application_fee = af

        # Tuition
        tuition = Tuition()
        tu_matches = self._tuition_matches(blob)
        if tu_matches:
            best = tu_matches[0]
            amount, currency, period, ev, raw = best
            tuition.amount = _known(amount, self.sid, ev, 0.85, raw=raw)
            if currency:
                tuition.currency = _known(currency, self.sid, ev, 0.85)
            if period:
                tuition.period = _known(period, self.sid, ev, 0.8)
            if period == "per_year":
                tuition.per_year = _known(amount, self.sid, ev, 0.8)
            elif period == "per_semester":
                tuition.per_semester = _known(amount, self.sid, ev, 0.8)
            tuition.source_id = self.sid
            tuition.evidence_text = ev
            tuition.confidence = 0.8
        if re.search(r"no tuition fees?|tuition[- ]free|no tuition", blob, re.IGNORECASE):
            m = re.search(r"no tuition fees?|tuition[- ]free|no tuition", blob, re.IGNORECASE)
            ev = sentence_at(blob, m.start())
            tuition.amount = _known(0, self.sid, ev, 0.8)
            tuition.source_id = self.sid
            tuition.evidence_text = ev
        obj.fees.tuition = tuition

    def _tuition_matches(self, text: str):
        results = []
        seen = set()
        period_kw = [
            ("per_year", ["per year", "per annum", "annually", "a year", "/year", "per academic year"]),
            ("per_semester", ["per semester", "each semester", "/semester", "per term"]),
            ("per_credit", ["per credit", "credit hour", "per ects", "per credit point"]),
            ("total", ["total", "entire programme", "entire program", "whole programme"]),
        ]
        tuition_kw = ["tuition fee", "tuition fees", "tuition", "programme fee", "program fee",
                      "course fee", "study fee", "cost of study", "fees for this"]
        for kw in tuition_kw:
            start = 0
            while True:
                idx = text.lower().find(kw, start)
                if idx == -1:
                    break
                start = idx + len(kw)
                window = sentence_block(text, idx, count=2, cap=420)
                ctx = sentence_at(text, idx)
                low = ctx.lower()
                if "bachelor" in low and "master" not in low and "postgraduate" not in low:
                    continue
                if re.search(r"application fee|application fees", low) and "tuition" not in low:
                    continue
                money = next(
                    (m for m in _MONEY_RE.finditer(window) if _has_currency_marker(m)
                     and (parse_amount(m.group("amt")) or 0) >= 100),
                    None,
                )
                if not money:
                    continue
                amount = parse_amount(money.group("amt"))
                if amount is None:
                    continue
                period = None
                for pname, kws in period_kw:
                    if any(k in low for k in kws):
                        period = pname
                        break
                if period is None:
                    # Look just past the amount for a period hint.
                    tail = window[money.end() : money.end() + 80].lower()
                    for pname, kws in period_kw:
                        if any(k in tail for k in kws):
                            period = pname
                            break
                currency = detect_currency(ctx + " " + window, money, self.country_hint)
                key = (amount, currency, period)
                if key in seen:
                    continue
                seen.add(key)
                ev = ctx if len(ctx) > 20 else window.strip()
                results.append((amount, currency, period, ev, money.group(0)))
        results.sort(key=lambda r: (r[2] is not None, r[1] is not None), reverse=True)
        return results

    # -- english -------------------------------------------------------------
    def _english(self, obj: ProgramIntelligence, text: str) -> None:
        er = EnglishRequirements()

        ielts = self._test_score(text, "IELTS", r"IELTS[^.\n]{0,80}?(\d(?:\.\d)?)")
        if ielts:
            er.ielts = ielts
        toefl = self._test_score(text, "TOEFL", r"(?:TOEFL(?:\s+iBT)?|internet[- ]based)[^.\n]{0,80}?(\d{2,3})")
        if toefl:
            er.toefl = toefl
        pte = self._test_score(text, "PTE", r"\bPTE[^.\n]{0,80}?(\d{2,3})")
        if pte:
            er.pte = pte
        duo = self._test_score(text, "Duolingo", r"Duolingo[^.\n]{0,80}?(\d{2,3})")
        if duo:
            er.duolingo = duo
        camb = self._test_score(text, "Cambridge", r"Cambridge[^.\n]{0,80}?([A-C]\b|C[12]\b|\d{2,3})", bounded=False)
        if camb:
            er.cambridge = camb

        if any(getattr(er, k).status != TestStatus.NOT_MENTIONED for k in ("ielts", "toefl", "pte", "duolingo", "cambridge")):
            er.required = _known(True, self.sid, "English language proficiency requirements listed", 0.8)

        for m in re.finditer(r"(waiv\w+|exempt\w+)[^.\n]{0,140}", text, re.IGNORECASE):
            ev = sentence_at(text, m.start())
            if re.search(r"english|language|ielts|toefl", ev, re.IGNORECASE):
                er.waivers.append(_known(ev, self.sid, ev, 0.6))
        obj.english_requirements = er

    def _test_score(
        self,
        text: str,
        name: str,
        score_regex: str,
        bounded: bool = True,
    ) -> Optional[TestScore]:
        bounds = TEST_BOUNDS.get(name) if bounded else None
        chosen = None
        for m in re.finditer(score_regex, text, re.IGNORECASE):
            try:
                score_val = float(m.group(1))
            except ValueError:
                continue
            if bounds and not (bounds[0] <= score_val <= bounds[1]):
                continue
            chosen = (m, score_val)
            break
        if chosen is None:
            return None
        m, score_val = chosen
        ev = sentence_at(text, m.start())
        ts = TestScore(
            required=True,
            status=TestStatus.REQUIRED,
            source_id=self.sid,
            evidence_text=ev,
            confidence=0.85,
            raw=m.group(0),
        )
        ts.minimum_overall = score_val
        ts.minimum_total = score_val
        ts.minimum_score = score_val
        # Section minimums, e.g. "no less than 6.0 in each"
        sec = re.search(r"(?:no (?:less|lower) than|minimum of|at least|each)[^.\n]{0,40}?(\d(?:\.\d)?)", ev, re.IGNORECASE)
        if sec:
            try:
                ts.minimum_sections = {"each": float(sec.group(1))}
            except ValueError:
                pass
        return ts

    # -- GRE / GMAT ----------------------------------------------------------
    def _standardized_tests(self, obj: ProgramIntelligence, text: str) -> None:
        obj.gre = self._test_status(text, "GRE", r"\bGRE\b|Graduate Record Exam\w*")
        obj.gmat = self._test_status(text, "GMAT", r"\bGMAT\b|Graduate Management Admission Test")

    def _test_status(self, text: str, name: str, name_regex: str) -> StandardizedTest:
        test = StandardizedTest(name=name)
        windows: List[Tuple[int, str]] = []
        for m in re.finditer(name_regex, text, re.IGNORECASE):
            windows.append((m.start(), sentence_at(text, m.start())))
        if not windows:
            test.status = TestStatus.NOT_MENTIONED
            return test

        for idx, ev in windows:
            low = ev.lower()
            if re.search(r"not required|not necessary|no (?:gre|gmat)|not mandated|not needed", low):
                test.status = TestStatus.NOT_REQUIRED
                test.source_id = self.sid
                test.evidence_text = ev
                test.confidence = 0.85
                return test
            if re.search(r"\bwaiv", low):
                test.status = TestStatus.WAIVED
                test.source_id = self.sid
                test.evidence_text = ev
                test.confidence = 0.75
                return test
            if re.search(r"\boptional\b", low):
                test.status = TestStatus.OPTIONAL
                test.source_id = self.sid
                test.evidence_text = ev
                test.confidence = 0.8
                return test
            if re.search(r"\brecommended\b|\bsubmi(?:t|ssion) is encouraged\b", low):
                test.status = TestStatus.RECOMMENDED
                test.source_id = self.sid
                test.evidence_text = ev
                test.confidence = 0.75
                return test
            if re.search(r"\brequired\b|must (?:submit|provide|take)|is mandatory", low):
                test.status = TestStatus.REQUIRED
                test.source_id = self.sid
                test.evidence_text = ev
                test.confidence = 0.85
                score = re.search(r"\b(1[3-7]\d)\b", ev)
                if score:
                    test.minimum_score = float(score.group(1))
                return test

        # Mentioned but no status keyword -> ambiguous, not "not required".
        idx, ev = windows[0]
        test.status = TestStatus.UNKNOWN
        test.source_id = self.sid
        test.evidence_text = ev
        test.notes = "Mentioned without explicit required/optional status"
        return test

    # -- academic background / performance ----------------------------------
    def _academic(self, obj: ProgramIntelligence, text: str) -> None:
        ac = AcademicRequirements()
        bg = AcademicBackground()
        perf = AcademicPerformance()

        # Only treat a degree phrase as a requirement on admissions-style pages;
        # fees/other pages mention "master's degree" in unrelated contexts.
        requirement_pages = {
            PageType.ADMISSION_REQUIREMENTS,
            PageType.INTERNATIONAL,
            PageType.PROGRAM,
            PageType.APPLICATION,
            PageType.HANDBOOK,
        }
        m = None
        if self.source.page_type in requirement_pages and not (
            self.source.is_pdf and self.source.page_type != PageType.ADMISSION_REQUIREMENTS
        ):
            m = re.search(
                r"((?:a\s+)?(?:bachelor'?s|undergraduate|first|honours|honors|four[- ]year|master'?s)\s+degree[^.,;\n]{0,90})",
                text,
                re.IGNORECASE,
            )
        if m:
            ev = sentence_at(text, m.start())
            cue = re.search(
                r"requir|must|hold|holds|holding|minimum|entry|entrance|admission|admitted|"
                r"applicant|possess|obtain|equivalent|normally",
                ev,
                re.IGNORECASE,
            )
            negative = re.search(
                r"\bfee\b|statutory|tuition|scholarship|subsidy|air travel|mature[- ]age|entry scheme",
                ev,
                re.IGNORECASE,
            )
            if not negative and (cue or len(ev) <= 90):
                bg.minimum_degree = _known(m.group(1).strip(), self.sid, ev, 0.8)
                bg.source_id = self.sid
                bg.evidence_text = ev

        field_phrase = re.search(
            r"(?:degree|background|qualification)\s+in\s+([A-Za-z][A-Za-z ,/&\-]{2,80})",
            text,
            re.IGNORECASE,
        )
        if field_phrase:
            fields = [
                f.strip()
                for f in re.split(r",| or | and ", field_phrase.group(1))
                if 2 < len(f.strip()) < 60
            ]
            ev = sentence_at(text, field_phrase.start())
            for f in fields:
                bg.accepted_fields.append(_known(f, self.sid, ev, 0.7))
        if re.search(r"(?:related|relevant|cognate)\s+(?:field|discipline|subject|area)", text, re.IGNORECASE):
            m2 = re.search(r"(?:related|relevant|cognate)\s+(?:field|discipline|subject|area)[^.\n]{0,40}", text, re.IGNORECASE)
            bg.related_fields_allowed = _known(True, self.sid, sentence_at(text, m2.start()), 0.7)

        # GPA / grade
        gpa = re.search(r"(?:minimum\s+)?(?:CGPA|GPA)\s*(?:of|:)?\s*(\d(?:\.\d{1,2})?)", text, re.IGNORECASE)
        if gpa:
            gpa_value = float(gpa.group(1))
            if 0.0 <= gpa_value <= 10.0:
                ev = sentence_at(text, gpa.start())
                perf.minimum_gpa = _known(gpa_value, self.sid, ev, 0.8)
                scale = re.search(r"(?:out of|/|on)\s*(4(?:\.0)?|10(?:\.0)?|100)\b", ev)
                if scale:
                    perf.gpa_scale = _known(scale.group(1), self.sid, ev, 0.7)
        pct = re.search(r"(?:minimum|at least|overall)\s*(?:average|score)?\s*(?:of\s*)?(\d{2}(?:\.\d)?)\s*%", text, re.IGNORECASE)
        if pct:
            perf.minimum_percentage = _known(float(pct.group(1)), self.sid, sentence_at(text, pct.start()), 0.75)
        grade_ok = self.source.page_type in requirement_pages and not (
            self.source.is_pdf and self.source.page_type != PageType.ADMISSION_REQUIREMENTS
        )
        for grade in ["upper second", "2:1", "first class", "second class", "lower second", "2:2"]:
            idx = text.lower().find(grade)
            if idx == -1:
                continue
            ctx = sentence_at(text, idx)
            if grade_ok and re.search(r"degree|honou?r|classification|grade", ctx, re.IGNORECASE):
                perf.minimum_grade = _known(grade, self.sid, ctx, 0.75)
                break
        if not perf.grading_system.is_known():
            for system in ["ECTS", "GPA", "percentage", "UK honours"]:
                idx = text.lower().find(system.lower())
                if idx != -1:
                    perf.grading_system = _known(system, self.sid, sentence_at(text, idx), 0.5)
                    break
        ac.background = bg
        ac.performance = perf
        obj.academic_requirements = ac

    # -- prerequisites -------------------------------------------------------
    def _prerequisites(self, obj: ProgramIntelligence, text: str) -> None:
        prereqs: List[Prerequisite] = []
        seen = set()

        # Explicit credit requirements mapped to a subject category.
        for m in re.finditer(
            r"(\d{1,3})\s*(ECTS|credits?|credit points|CP)\s*(?:in|of|within)\s+([A-Za-z][A-Za-z ,/&\-]{2,60})",
            text,
            re.IGNORECASE,
        ):
            credits = float(m.group(1))
            system = "ECTS" if "ects" in m.group(2).lower() else "CREDITS"
            subject = m.group(3).strip()
            subject_l = subject.lower()
            category = "OTHER"
            for cat, kws in PREREQ_CATEGORIES.items():
                if any(kw in subject_l for kw in kws):
                    category = cat
                    break
            key = (category, subject_l)
            if key in seen:
                continue
            seen.add(key)
            prereqs.append(
                Prerequisite(
                    category=category,
                    subject=subject,
                    required=True,
                    credits=credits,
                    credit_system=system,
                    source_id=self.sid,
                    evidence_text=sentence_at(text, m.start()),
                    confidence=0.85,
                )
            )

        # Keyword-only prerequisites (required coursework mentions).
        lowered = text.lower()
        for cat, kws in PREREQ_CATEGORIES.items():
            for kw in kws:
                idx = lowered.find(kw)
                if idx == -1:
                    continue
                ctx = sentence_at(text, idx)
                if not re.search(
                    r"prerequisit|prior|required|background|knowledge|coursework|subject|degree in|proficiency|foundation|experience (?:in|with)|training",
                    ctx,
                    re.IGNORECASE,
                ):
                    continue
                key = (cat, "")
                if key in seen:
                    break
                seen.add(key)
                prereqs.append(
                    Prerequisite(
                        category=cat,
                        subject=kw,
                        required=True,
                        source_id=self.sid,
                        evidence_text=ctx,
                        confidence=0.6,
                    )
                )
                break
        obj.prerequisites = prereqs


def make_input_source(hints: Dict) -> Source:
    from datetime import datetime, timezone

    return Source(
        id="input",
        url=hints.get("program_url") or hints.get("source_url") or "",
        title="QS program record",
        source_type=SourceType.AGGREGATOR,
        page_type=PageType.OTHER,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        tier=3,
    )
