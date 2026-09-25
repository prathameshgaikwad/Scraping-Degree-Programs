"""Deterministic program relevance classifier.

Cheap, auditable, and applied to every program before any LLM is considered
(cost control, Section 22). Matches explicit taxonomy terms against the
normalized title and returns a structured, evidence-backed result.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..normalize.text import normalize_name
from .models import ClassificationMethod, ProgramClassification, Relevance
from .taxonomy import (
    CORE_FIELDS,
    FIELD_LABELS,
    STRONG,
    TAXONOMY,
    FieldSpec,
    field_priority,
)
from .versions import CLASSIFIER_VERSION

_HIGH_THRESHOLD = 7
_MEDIUM_THRESHOLD = 4
_LOW_THRESHOLD = 1


def _compile(spec: FieldSpec) -> re.Pattern:
    terms = sorted((re.escape(t) for t, _ in spec.keywords), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(terms) + r")\b")


class DeterministicClassifier:
    def __init__(self) -> None:
        self._regexes = {spec.code: _compile(spec) for spec in TAXONOMY}
        self._weights = {
            spec.code: {term: weight for term, weight in spec.keywords} for spec in TAXONOMY
        }

    def classify(self, program_id: str, university_id: str, name: str) -> ProgramClassification:
        normalized = normalize_name(name or "")
        scores: Dict[str, int] = {}
        evidence: Dict[str, List[str]] = {}

        strong_flags: Dict[str, bool] = {}
        for spec in TAXONOMY:
            matched: List[str] = []
            for term, _weight in spec.keywords:
                if re.search(r"\b" + re.escape(term) + r"\b", normalized):
                    matched.append(term)
            if not matched:
                continue
            weights = {term: weight for term, weight in spec.keywords}
            strong = [t for t in matched if weights[t] == STRONG]
            # If a strong term matched, weaker terms are redundant for scoring
            # (but stay in evidence). Then drop terms subsumed by a longer match.
            scoring = strong if strong else matched
            scoring = [t for t in scoring if not any(t != o and t in o for o in scoring)]
            scores[spec.code] = sum(weights[t] for t in scoring)
            strong_flags[spec.code] = bool(strong)
            evidence[spec.code] = matched

        if not scores:
            return ProgramClassification(
                program_id=program_id,
                university_id=university_id,
                name=name,
                normalized_name=normalized,
                primary_field="UNKNOWN",
                relevance=Relevance.NONE,
                confidence=0.8,
                reason="No taxonomy terms matched the title.",
                evidence={},
                scores={},
                method=ClassificationMethod.DETERMINISTIC,
                classifier_version=CLASSIFIER_VERSION,
            )

        primary = max(scores.items(), key=lambda kv: (kv[1], -field_priority(kv[0])))[0]
        raw = scores[primary]
        adjusted = raw + (2 if primary in CORE_FIELDS else 0) + (1 if strong_flags.get(primary) else 0)
        relevance = self._relevance(adjusted)

        secondary = [
            code
            for code, score in sorted(
                scores.items(), key=lambda kv: (-kv[1], field_priority(kv[0]))
            )
            if code != primary and score >= 2
        ][:3]

        sorted_scores = dict(
            sorted(scores.items(), key=lambda kv: (-kv[1], field_priority(kv[0])))
        )
        second_raw = next((s for c, s in sorted_scores.items() if c != primary), 0)
        confidence = self._confidence(adjusted, raw - second_raw, relevance)
        reason = self._reason(primary, evidence[primary], secondary, evidence)

        return ProgramClassification(
            program_id=program_id,
            university_id=university_id,
            name=name,
            normalized_name=normalized,
            primary_field=primary,
            secondary_fields=secondary,
            relevance=relevance,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            scores=sorted_scores,
            method=ClassificationMethod.DETERMINISTIC,
            classifier_version=CLASSIFIER_VERSION,
        )

    @staticmethod
    def _relevance(adjusted: int) -> Relevance:
        if adjusted >= _HIGH_THRESHOLD:
            return Relevance.HIGH
        if adjusted >= _MEDIUM_THRESHOLD:
            return Relevance.MEDIUM
        if adjusted >= _LOW_THRESHOLD:
            return Relevance.LOW
        return Relevance.NONE

    @staticmethod
    def _confidence(adjusted: int, margin: int, relevance: Relevance) -> float:
        if relevance == Relevance.NONE:
            return 0.8
        confidence = 0.5 + 0.06 * adjusted
        if margin >= 3:
            confidence += 0.08
        elif margin == 0:
            confidence -= 0.05
        return round(min(0.97, max(0.3, confidence)), 2)

    @staticmethod
    def _reason(
        primary: str,
        primary_terms: List[str],
        secondary: List[str],
        evidence: Dict[str, List[str]],
    ) -> str:
        parts = [f"Primary {FIELD_LABELS.get(primary, primary)} (matched: {', '.join(primary_terms)})."]
        if secondary:
            parts.append(
                "Secondary: "
                + "; ".join(
                    f"{FIELD_LABELS.get(code, code)} ({', '.join(evidence.get(code, []))})"
                    for code in secondary
                )
                + "."
            )
        return " ".join(parts)


TAXONOMY_BY_CODE = {spec.code: spec for spec in TAXONOMY}


def needs_llm_review(classification: ProgramClassification) -> bool:
    """Whether an ambiguous result warrants the (optional) LLM fallback."""
    if classification.relevance == Relevance.LOW:
        return True
    if classification.relevance == Relevance.MEDIUM and classification.confidence < 0.6:
        return True
    return False
