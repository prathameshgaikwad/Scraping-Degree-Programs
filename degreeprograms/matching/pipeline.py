"""Phase 7 pipeline: match an applicant against extracted requirements.

Deterministic first; the optional LLM is only consulted for ``UNCLEAR`` results.
Results are cached by (profile, requirement content, matcher version) so re-runs
and profile edits are incremental.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..normalize.io import ensure_dir, read_json, read_jsonl, utcnow, write_json, write_jsonl
from ..profile.loading import load_profile
from ..requirements.models import ProgramRequirements
from .llm import is_enabled, reason_with_llm
from .matcher import match
from .models import EligibilityAssessment, EligibilityState, MatchManifest
from .versions import MATCHER_VERSION, MATCH_SCHEMA_VERSION


@dataclass
class MatchConfig:
    profile_path: str = "degreeprograms/profile/testdata/applicant.example.yaml"
    requirements_path: str = "data/enriched/requirements/requirements.jsonl"
    programs_path: str = "data/normalized/programs.jsonl"
    universities_path: str = "data/normalized/universities.jsonl"
    out_dir: str = "data/matching/eligibility"
    use_llm: bool = True
    force: bool = False
    limit: int = 0


class MatchPipeline:
    def __init__(self, config: Optional[MatchConfig] = None) -> None:
        self.config = config or MatchConfig()

    def run(self) -> MatchManifest:
        cfg = self.config
        ensure_dir(cfg.out_dir)
        cache_path = os.path.join(cfg.out_dir, "cache.json")
        cache = self._load_cache(cache_path)

        profile = load_profile(cfg.profile_path)
        profile_hash = self._hash(profile.model_dump(mode="json"))
        programs = {p["program_id"]: p for p in read_jsonl(cfg.programs_path)}
        universities = {u["university_id"]: u for u in read_jsonl(cfg.universities_path)}
        requirements = [ProgramRequirements(**row) for row in read_jsonl(cfg.requirements_path)]
        if cfg.limit:
            requirements = requirements[: cfg.limit]

        llm_enabled = cfg.use_llm and is_enabled()
        results: List[EligibilityAssessment] = []
        cache_hits = 0
        llm_calls = 0

        for req in requirements:
            req_hash = self._hash(req.model_dump(mode="json"))
            key = self._cache_key(profile_hash, req_hash)
            if not cfg.force and key in cache:
                results.append(EligibilityAssessment(**cache[key]))
                cache_hits += 1
                continue

            program = programs.get(req.program_id, {})
            university = universities.get(program.get("university_id", ""), {})
            assessment = match(
                profile,
                req,
                program_name=req.program_name or program.get("name"),
                university_name=req.university_name or university.get("canonical_name"),
            )

            if llm_enabled and assessment.state == EligibilityState.UNCLEAR:
                llm_state = reason_with_llm(
                    self._profile_summary(profile),
                    "; ".join(assessment.reasons[:12]),
                )
                if llm_state is not None:
                    llm_calls += 1
                    assessment.state = llm_state.state
                    assessment.method = "HYBRID"
                    assessment.reasons.insert(0, f"LLM: {llm_state.reason}")

            assessment.matched_at = utcnow()
            cache[key] = assessment.model_dump(mode="json")
            results.append(assessment)

        results.sort(key=lambda a: a.program_id)
        write_jsonl(os.path.join(cfg.out_dir, "eligibility.jsonl"), results)
        write_json(cache_path, {"version": MATCHER_VERSION, "entries": cache})
        manifest = self._manifest(cfg, results, cache_hits, llm_calls)
        write_json(os.path.join(cfg.out_dir, "manifest.json"), manifest)
        return manifest

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _hash(obj) -> str:
        payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _cache_key(profile_hash: str, req_hash: str) -> str:
        return hashlib.sha1(f"{MATCHER_VERSION}|{profile_hash}|{req_hash}".encode("utf-8")).hexdigest()

    @staticmethod
    def _load_cache(path: str) -> Dict[str, dict]:
        if not os.path.exists(path):
            return {}
        try:
            data = read_json(path)
            if data.get("version") == MATCHER_VERSION:
                return data.get("entries", {})
        except Exception:
            pass
        return {}

    @staticmethod
    def _profile_summary(profile) -> str:
        primary = profile.primary_education
        return json.dumps(
            {
                "highest_degree": profile.highest_degree_level.value,
                "field": primary.field if primary else None,
                "cgpa": primary.cgpa if primary else None,
                "cgpa_scale": primary.cgpa_scale if primary else None,
                "experience_years": profile.total_experience_years,
                "coursework": [c.name for c in profile.coursework],
                "testing": profile.testing.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _manifest(cfg: MatchConfig, results, cache_hits: int, llm_calls: int) -> MatchManifest:
        by_state = Counter(a.state.value for a in results)
        return MatchManifest(
            requirements_path=cfg.requirements_path,
            programs_path=cfg.programs_path,
            profile_path=cfg.profile_path,
            matcher_version=MATCHER_VERSION,
            schema_version=MATCH_SCHEMA_VERSION,
            generated_at=utcnow(),
            programs=len(results),
            by_state=dict(by_state.most_common()),
            cache_hits=cache_hits,
            llm_calls=llm_calls,
        )
