"""Merge per-source extractions into one canonical object.

Implements Section 67 (multi-page merging), Section 68 (never overwrite good
information with UNKNOWN) and Section 58 (retain conflicts).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, get_args

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from .schema import (
    Completeness,
    Fact,
    ProgramIntelligence,
    Source,
    SourceType,
    TestStatus,
    ValueStatus,
)
from .versions import CRAWLER_VERSION, EXTRACTOR_VERSION, SCHEMA_VERSION

# Higher is more program-specific (Section 58 preference order).
PAGE_PRIORITY = {
    "FEES": 3,
    "ADMISSION_REQUIREMENTS": 3,
    "APPLICATION": 3,
    "CURRICULUM": 3,
    "INTERNATIONAL": 2,
    "HANDBOOK": 2,
    "PROGRAM": 1,
    "FUNDING": 2,
    "CONTACT": 1,
    "OTHER": 0,
}


class Merger:
    def __init__(self, sources: Optional[Dict[str, Source]] = None):
        self.sources = sources or {}

    # -- precedence ----------------------------------------------------------
    def _pref(self, source_id: Optional[str], confidence: Optional[float]) -> Tuple:
        src = self.sources.get(source_id or "")
        tier = src.tier if src else 3
        page = PAGE_PRIORITY.get(src.page_type.value if src else "OTHER", 0)
        is_official = 1 if (src and src.source_type == SourceType.OFFICIAL_UNIVERSITY) else 0
        return (is_official, -tier, page, confidence or 0.0)

    def merge(self, base: ProgramIntelligence, incoming: ProgramIntelligence) -> ProgramIntelligence:
        self._merge_model(base, incoming)
        return base

    def _merge_model(self, base: BaseModel, incoming: BaseModel) -> None:
        for name in type(incoming).model_fields:
            inc = getattr(incoming, name)
            cur = getattr(base, name)
            if isinstance(inc, Fact):
                setattr(base, name, self._merge_fact(cur, inc))
            elif isinstance(inc, list):
                setattr(base, name, self._merge_list(cur, inc, type(incoming).model_fields[name]))
            elif isinstance(inc, BaseModel):
                self._merge_model(cur, inc)
            else:
                default = type(base).model_fields[name].default
                if default is not PydanticUndefined and cur == default and inc != default:
                    setattr(base, name, inc)
                elif cur in (None, "", [], False) and inc not in (None, "", [], False):
                    setattr(base, name, inc)

    # -- facts ---------------------------------------------------------------
    def _merge_fact(self, cur: Fact, inc: Fact) -> Fact:
        if cur is None:
            return inc
        if inc.status == ValueStatus.UNKNOWN or inc.status == ValueStatus.NOT_MENTIONED:
            return cur
        if not inc.is_known():
            if inc.status == ValueStatus.CONFLICTING and inc.values:
                return self._combine_conflict(cur, inc)
            return cur
        if not cur.is_known():
            return inc
        if cur.value == inc.value:
            if self._pref(inc.source_id, inc.confidence) > self._pref(cur.source_id, cur.confidence):
                return inc
            return cur
        # Genuine conflict.
        return self._combine_conflict(cur, inc)

    def _combine_conflict(self, cur: Fact, inc: Fact) -> Fact:
        entries: List[Dict[str, Any]] = []
        if cur.status == ValueStatus.CONFLICTING and cur.values:
            entries.extend(cur.values)
        else:
            entries.append({"value": cur.value, "source": cur.source_id, "evidence": cur.evidence_text})
        if inc.status == ValueStatus.CONFLICTING and inc.values:
            entries.extend(inc.values)
        else:
            entries.append({"value": inc.value, "source": inc.source_id, "evidence": inc.evidence_text})
        # De-duplicate identical values.
        uniq: List[Dict[str, Any]] = []
        seen = set()
        for e in entries:
            key = repr(e.get("value"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(e)
        if len(uniq) == 1:
            return cur
        # Prefer the value from the higher-priority source, but keep all.
        best = max(
            uniq,
            key=lambda e: self._pref(e.get("source"), None),
        )
        return Fact(
            value=best.get("value"),
            status=ValueStatus.CONFLICTING,
            source_id=best.get("source"),
            evidence_text=best.get("evidence"),
            confidence=None,
            values=uniq,
        )

    # -- lists ---------------------------------------------------------------
    def _element_type(self, field) -> Optional[type]:
        args = get_args(field.annotation)
        if not args:
            return None
        (arg,) = args
        args2 = get_args(arg)
        return args2[0] if args2 else arg

    def _merge_list(self, cur: list, inc: list, field) -> list:
        if not inc:
            return cur
        elem_type = self._element_type(field)
        if elem_type is None and cur:
            elem_type = type(cur[0])
        if elem_type is not None and issubclass(elem_type, Fact):
            return self._merge_fact_list(cur, inc)
        if elem_type is not None and issubclass(elem_type, BaseModel):
            return self._merge_record_list(cur, inc, elem_type)
        # Scalar list
        out = list(cur)
        for item in inc:
            if item not in out:
                out.append(item)
        return out

    def _merge_fact_list(self, cur: List[Fact], inc: List[Fact]) -> List[Fact]:
        out = list(cur)
        for fact in inc:
            if not fact.is_known():
                continue
            match = next((f for f in out if f.is_known() and f.value == fact.value), None)
            if match is None:
                out.append(fact)
            elif self._pref(fact.source_id, fact.confidence) > self._pref(match.source_id, match.confidence):
                out[out.index(match)] = fact
        return out

    def _merge_record_list(self, cur: list, inc: list, elem_type: type) -> list:
        out = list(cur)
        for record in inc:
            if not isinstance(record, BaseModel):
                continue
            key = self._record_key(record)
            match = next((r for r in out if self._record_key(r) == key), None)
            if match is None:
                out.append(record)
            else:
                self._merge_model(match, record)
        return out

    def _record_key(self, record: BaseModel) -> Tuple:
        if type(record).__name__ == "Intake":
            return ("Intake", record.term, record.start_year, record.start_month)
        for attr in ("name", "item", "category", "body", "system", "url"):
            if hasattr(record, attr):
                value = getattr(record, attr)
                if value:
                    return (type(record).__name__, str(value))
        if hasattr(record, "type"):
            extra = getattr(record, "date", None) or getattr(record, "raw", None)
            return (type(record).__name__, str(getattr(record, "type")), str(extra))
        return (type(record).__name__, repr(record))


# ---------------------------------------------------------------------------
# completeness + finalize
# ---------------------------------------------------------------------------

def _has_value(fact: Fact) -> bool:
    return fact.value is not None or bool(fact.values)


def _model_has_known(model: BaseModel) -> bool:
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, Fact):
            if _has_value(value):
                return True
        elif isinstance(value, BaseModel):
            if _model_has_known(value):
                return True
        elif isinstance(value, list):
            if value:
                return True
        elif value not in (None, "", False):
            return True
    return False


_UNRESOLVED_TEST = {TestStatus.NOT_MENTIONED, TestStatus.UNKNOWN}
_REPORTED_TEST = {
    TestStatus.REQUIRED,
    TestStatus.OPTIONAL,
    TestStatus.RECOMMENDED,
    TestStatus.NOT_REQUIRED,
    TestStatus.WAIVED,
    TestStatus.NOT_ACCEPTED,
}


def compute_completeness(obj: ProgramIntelligence) -> Completeness:
    c = Completeness()
    c.identity = (
        _has_value(obj.identity.program_name)
        or _has_value(obj.identity.official_program_name)
        or _has_value(obj.identity.degree_type)
    )
    c.fees = _has_value(obj.fees.tuition.amount) or _has_value(obj.fees.application_fee.amount)
    c.deadlines = obj.application.deadline is not None or len(obj.deadlines) > 0
    c.requirements = (
        _model_has_known(obj.academic_requirements)
        or bool(obj.prerequisites)
        or _model_has_known(obj.english_requirements)
    )
    c.english_tests = any(
        getattr(obj.english_requirements, k).status in _REPORTED_TEST
        for k in ("ielts", "toefl", "pte", "duolingo", "cambridge")
    )
    c.gre = obj.gre.status not in _UNRESOLVED_TEST
    c.gmat = obj.gmat.status not in _UNRESOLVED_TEST
    c.curriculum = bool(obj.curriculum.modules or obj.curriculum.core_modules)
    c.research = _has_value(obj.research.research_oriented) or bool(obj.research.research_areas)
    return c


def finalize(obj: ProgramIntelligence, retrieved_at: str) -> ProgramIntelligence:
    obj.completeness = compute_completeness(obj)
    obj.retrieved_at = retrieved_at
    obj.crawler_version = CRAWLER_VERSION
    obj.extractor_version = EXTRACTOR_VERSION
    obj.schema_version = SCHEMA_VERSION
    return obj
