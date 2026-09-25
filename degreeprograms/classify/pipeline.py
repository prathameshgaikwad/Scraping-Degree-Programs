"""Phase 3 pipeline: classify canonical programs.

Reads ``data/normalized/programs.jsonl`` and writes
``data/enriched/program_classifications/``. Deterministic first; the optional
LLM fallback only runs for ambiguous titles. Results are cached by program name
+ classifier version so re-runs and version bumps are incremental.
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..normalize.io import (
    ensure_dir,
    file_sha256,
    read_json,
    read_jsonl,
    utcnow,
    write_json,
    write_jsonl,
)
from .classifier import DeterministicClassifier, needs_llm_review
from .llm import classify_with_llm, is_enabled
from .models import (
    ClassificationManifest,
    ClassificationMethod,
    ProgramClassification,
)
from .versions import CLASSIFIER_VERSION, CLASSIFY_SCHEMA_VERSION


@dataclass
class ClassifyConfig:
    programs_path: str = "data/normalized/programs.jsonl"
    out_dir: str = "data/enriched/program_classifications"
    force: bool = False
    use_llm: bool = True  # only effective if the LLM env is enabled


class ClassificationPipeline:
    def __init__(self, config: Optional[ClassifyConfig] = None) -> None:
        self.config = config or ClassifyConfig()
        self.classifier = DeterministicClassifier()

    def run(self) -> ClassificationManifest:
        cfg = self.config
        ensure_dir(cfg.out_dir)
        manifest_path = os.path.join(cfg.out_dir, "manifest.json")
        programs_hash = file_sha256(cfg.programs_path)

        if not cfg.force and os.path.exists(manifest_path):
            try:
                previous = ClassificationManifest(**read_json(manifest_path))
                if (
                    previous.programs_sha256 == programs_hash
                    and previous.classifier_version == CLASSIFIER_VERSION
                ):
                    return previous
            except Exception:
                pass

        programs = read_jsonl(cfg.programs_path)
        cache_path = os.path.join(cfg.out_dir, "cache.json")
        cache = self._load_cache(cache_path)
        llm_enabled = cfg.use_llm and is_enabled()

        results: List[ProgramClassification] = []
        cache_hits = 0
        llm_calls = 0
        for program in programs:
            key = self._cache_key(program.get("normalized_name") or program.get("name") or "")
            if not cfg.force and key in cache:
                cached = dict(cache[key])
                cached.update(
                    program_id=program.get("program_id", ""),
                    university_id=program.get("university_id", ""),
                    name=program.get("name", ""),
                    normalized_name=program.get("normalized_name") or program.get("name", ""),
                )
                results.append(ProgramClassification(**cached))
                cache_hits += 1
                continue

            classification = self.classifier.classify(
                program_id=program.get("program_id", ""),
                university_id=program.get("university_id", ""),
                name=program.get("name", ""),
            )
            if llm_enabled and needs_llm_review(classification):
                llm_result = classify_with_llm(program.get("name", ""))
                if llm_result is not None:
                    llm_calls += 1
                    classification = self._apply_llm(classification, llm_result)

            classification.classified_at = utcnow()
            cache[key] = classification.model_dump(mode="json")
            results.append(classification)

        results.sort(key=lambda c: c.program_id)
        self._write(cfg.out_dir, results, cache)
        manifest = self._manifest(cfg, programs_hash, results, cache_hits, llm_calls)
        write_json(manifest_path, manifest)
        return manifest

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _cache_key(normalized_name: str) -> str:
        payload = f"{CLASSIFIER_VERSION}|{normalized_name}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _load_cache(path: str) -> Dict[str, dict]:
        if not os.path.exists(path):
            return {}
        try:
            data = read_json(path)
            if data.get("version") == CLASSIFIER_VERSION:
                return data.get("entries", {})
        except Exception:
            pass
        return {}

    @staticmethod
    def _apply_llm(classification: ProgramClassification, llm_result) -> ProgramClassification:
        classification.primary_field = llm_result.primary_field
        classification.secondary_fields = list(llm_result.secondary_fields)
        classification.relevance = llm_result.relevance
        classification.confidence = llm_result.confidence
        classification.reason = f"LLM: {llm_result.reason}"
        classification.method = ClassificationMethod.HYBRID
        return classification

    @staticmethod
    def _write(out_dir: str, results: List[ProgramClassification], cache: Dict[str, dict]) -> None:
        write_jsonl(os.path.join(out_dir, "classifications.jsonl"), results)
        write_json(
            os.path.join(out_dir, "cache.json"),
            {"version": CLASSIFIER_VERSION, "entries": cache},
        )

    @staticmethod
    def _manifest(
        cfg: ClassifyConfig,
        programs_hash: str,
        results: List[ProgramClassification],
        cache_hits: int,
        llm_calls: int,
    ) -> ClassificationManifest:
        by_relevance = Counter(c.relevance.value for c in results)
        by_field = Counter(c.primary_field for c in results)
        by_method = Counter(c.method.value for c in results)
        return ClassificationManifest(
            programs_path=cfg.programs_path,
            programs_sha256=programs_hash,
            classifier_version=CLASSIFIER_VERSION,
            schema_version=CLASSIFY_SCHEMA_VERSION,
            generated_at=utcnow(),
            programs=len(results),
            by_relevance=dict(by_relevance.most_common()),
            by_primary_field=dict(by_field.most_common()),
            by_method=dict(by_method.most_common()),
            llm_calls=llm_calls,
            cache_hits=cache_hits,
        )
