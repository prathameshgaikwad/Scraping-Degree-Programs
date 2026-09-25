"""Read-only program intelligence service backing the UI/API.

Merges the pipeline artifacts (normalized programs, classifications,
requirements, eligibility, universities) and the applicant profile into a
single queryable index. Pure functions, no web framework — easy to test.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ..normalize.io import read_jsonl

_RELEVANCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3, "UNKNOWN": 4}
_STATE_ORDER = {
    "ELIGIBLE": 0,
    "LIKELY_ELIGIBLE": 1,
    "UNCLEAR": 2,
    "PREREQUISITE_GAP": 3,
    "NOT_ELIGIBLE": 4,
    "UNKNOWN": 5,
}


def _load_by(path: str, key: str = "program_id") -> Dict[str, dict]:
    if not path or not os.path.exists(path):
        return {}
    out: Dict[str, dict] = {}
    for row in read_jsonl(path):
        if key in row:
            out[row[key]] = row
    return out


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [str(v).strip() for v in value if str(v).strip()]


def _field_value(field) -> Any:
    if isinstance(field, dict):
        return field.get("value")
    return None


class ProgramsService:
    def __init__(
        self,
        programs_path: str = "data/normalized/programs.jsonl",
        classifications_path: str = "data/enriched/program_classifications/classifications.jsonl",
        requirements_path: str = "data/enriched/requirements/requirements.jsonl",
        eligibility_path: str = "data/matching/eligibility/eligibility.jsonl",
        universities_path: str = "data/normalized/universities.jsonl",
        profile_path: str = "degreeprograms/profile/testdata/applicant.example.yaml",
    ) -> None:
        self.programs = _load_by(programs_path)
        self.classifications = _load_by(classifications_path)
        self.requirements = _load_by(requirements_path)
        self.eligibility = _load_by(eligibility_path)
        self.universities = _load_by(universities_path, key="university_id")
        self.profile = self._load_profile(profile_path)
        self._profile_doc: dict = dict(self.profile or {})
        self._index = [self._summary(pid) for pid in self.programs]

    @staticmethod
    def _load_profile(path: str) -> Optional[dict]:
        if not path or not os.path.exists(path):
            return None
        try:
            from ..profile.loading import load_profile

            return load_profile(path).model_dump(mode="json")
        except Exception:
            return None

    # -- summaries -----------------------------------------------------------
    def _summary(self, pid: str) -> dict:
        program = self.programs[pid]
        classification = self.classifications.get(pid, {})
        eligibility = self.eligibility.get(pid, {})
        requirements = self.requirements.get(pid, {})
        university = self.universities.get(program.get("university_id", ""), {})
        location = program.get("location") or {}
        ranking = program.get("ranking") or {}

        financial = requirements.get("financial") or {}
        application = requirements.get("application") or {}
        primary_field = classification.get("primary_field")
        return {
            "program_id": pid,
            "name": program.get("name"),
            "university_id": program.get("university_id"),
            "university_name": university.get("canonical_name"),
            "country": location.get("country"),
            "city": location.get("city"),
            "region": location.get("region"),
            "degree_type": program.get("degree_type"),
            "program_format": program.get("program_format"),
            "primary_field": primary_field,
            "secondary_fields": classification.get("secondary_fields") or [],
            "relevance": classification.get("relevance"),
            "confidence": classification.get("confidence"),
            "eligibility_state": eligibility.get("state"),
            "analysed": bool(eligibility),
            "qs_rank": ranking.get("university_rank"),
            "qs_rank_display": ranking.get("rank_display"),
            "official_domain": university.get("official_domain"),
            "tuition_amount": _field_value(financial.get("tuition")),
            "tuition_currency": _field_value(financial.get("currency")),
            "tuition_period": _field_value(financial.get("period")),
            "deadline": _field_value(application.get("deadline")),
            "application_fee": _field_value(application.get("application_fee")),
            "evidence_count": len(requirements.get("sources") or []),
        }

    # -- API -----------------------------------------------------------------
    def meta(self) -> dict:
        def facet(key: str) -> List[dict]:
            counts: Dict[str, int] = {}
            for item in self._index:
                value = item.get(key)
                if isinstance(value, list):
                    continue
                value = value or "UNKNOWN"
                counts[value] = counts.get(value, 0) + 1
            return [
                {"value": k, "count": v}
                for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ]

        return {
            "total_programs": len(self._index),
            "analyzed": sum(1 for i in self._index if i["analysed"]),
            "facets": {
                "country": facet("country"),
                "primary_field": facet("primary_field"),
                "relevance": facet("relevance"),
                "eligibility_state": facet("eligibility_state"),
                "program_format": facet("program_format"),
                "degree_type": facet("degree_type"),
            },
        }

    def search(
        self,
        q: Optional[str] = None,
        field: Any = None,
        country: Any = None,
        relevance: Any = None,
        state: Any = None,
        program_format: Any = None,
        degree_type: Any = None,
        analysed: Optional[bool] = None,
        max_rank: Optional[int] = None,
        sort: str = "rank",
        limit: int = 2000,
        offset: int = 0,
    ) -> dict:
        q_lower = (q or "").strip().lower()
        fields = _as_list(field)
        countries = _as_list(country)
        relevances = _as_list(relevance)
        states = _as_list(state)
        formats = _as_list(program_format)
        degrees = _as_list(degree_type)

        def matches(item: dict) -> bool:
            if fields and item.get("primary_field") not in fields:
                return False
            if countries and item.get("country") not in countries:
                return False
            if relevances and item.get("relevance") not in relevances:
                return False
            if states and item.get("eligibility_state") not in states:
                return False
            if formats and item.get("program_format") not in formats:
                return False
            if degrees and item.get("degree_type") not in degrees:
                return False
            if analysed is True and not item.get("analysed"):
                return False
            if analysed is False and item.get("analysed"):
                return False
            if max_rank is not None:
                rank = item.get("qs_rank")
                if rank is None or rank > max_rank:
                    return False
            if q_lower:
                haystack = f"{item.get('name') or ''} {item.get('university_name') or ''}".lower()
                if q_lower not in haystack:
                    return False
            return True

        filtered = [item for item in self._index if matches(item)]
        filtered.sort(key=self._sort_key(sort))
        total = len(filtered)
        window = filtered[offset : offset + limit] if limit else filtered
        return {"total": total, "limit": limit, "offset": offset, "results": window}

    @staticmethod
    def _sort_key(sort: str):
        if sort == "name":
            return lambda i: (i.get("name") or "").lower()
        if sort == "relevance":
            return lambda i: (_RELEVANCE_ORDER.get(i.get("relevance"), 9), i.get("qs_rank") or 9999)
        if sort == "state":
            return lambda i: (_STATE_ORDER.get(i.get("eligibility_state") or "UNKNOWN", 9), i.get("qs_rank") or 9999)
        if sort == "tuition":
            return lambda i: (i.get("tuition_amount") is None, i.get("tuition_amount") or 0)
        if sort == "deadline":
            return lambda i: (i.get("deadline") is None, i.get("deadline") or "")
        # rank (default)
        return lambda i: (i.get("qs_rank") is None, i.get("qs_rank") or 0, (i.get("name") or "").lower())

    def program(self, pid: str) -> Optional[dict]:
        if pid not in self.programs:
            return None
        program = self.programs[pid]
        university = self.universities.get(program.get("university_id", ""), {})
        return {
            "program": program,
            "summary": self._summary(pid),
            "university": {
                "university_id": university.get("university_id"),
                "canonical_name": university.get("canonical_name"),
                "country": university.get("country"),
                "city": university.get("city"),
                "official_domain": university.get("official_domain"),
                "qs": university.get("qs"),
                "aliases": [a.get("alias") for a in (university.get("aliases") or [])],
            },
            "classification": self.classifications.get(pid),
            "requirements": self.requirements.get(pid),
            "eligibility": self.eligibility.get(pid),
        }

    def profile_summary(self) -> Optional[dict]:
        if not self.profile:
            return None
        education = self.profile.get("education") or []
        primary = education[0] if education else {}
        return {
            "applicant_id": self.profile.get("applicant_id"),
            "education": primary,
            "experience": self.profile.get("experience") or [],
            "target_fields": self.profile.get("target_fields") or [],
            "technical_background": self.profile.get("technical_background") or [],
            "testing": self.profile.get("testing") or {},
            "coursework": self.profile.get("coursework") or [],
        }

    # -- mutable applicant profile (in-memory; UI-editable) -------------------
    def get_profile(self) -> dict:
        """Full, editable profile document (defaults to the loaded profile)."""
        return dict(self._profile_doc)

    def set_profile(self, data: dict) -> dict:
        """Validate and store an edited profile. Raises ValueError on invalid input."""
        from ..profile.loading import load_profile_dict

        profile = load_profile_dict(data or {})  # pydantic validation
        doc = profile.model_dump(mode="json")
        self._profile_doc = doc
        self.profile = doc
        self._recompute_matches()
        return doc

    def _recompute_matches(self) -> None:
        """Re-run eligibility for analysed programs with the current profile.

        Keeps the matched states in sync with the applicant's edits so the UI
        re-ranks without a separate pipeline run. Programs without extracted
        requirements keep their previous state.
        """
        try:
            from ..matching.matcher import match
            from ..profile.loading import load_profile_dict
            from ..requirements.models import ProgramRequirements
        except Exception:
            return
        try:
            profile = load_profile_dict(self._profile_doc)
        except Exception:
            return
        programs = {p["program_id"]: p for p in self.programs.values()}
        for pid, req_row in self.requirements.items():
            try:
                requirements = ProgramRequirements(**req_row)
            except Exception:
                continue
            program = programs.get(pid, {})
            assessment = match(
                profile,
                requirements,
                program_name=program.get("name"),
                university_name=self.universities.get(program.get("university_id", ""), {}).get("canonical_name"),
            )
            self.eligibility[pid] = assessment.model_dump(mode="json")
        self._index = [self._summary(pid) for pid in self.programs]
