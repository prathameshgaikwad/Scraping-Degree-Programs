"""Evaluation runners: compare pipeline outputs against the gold datasets.

Each evaluator returns an :class:`EvaluationMetric`. Value-level metrics
(classification, eligibility) are kept separate from source-level metrics
(page classification, evidence) so a correct value with a wrong source is
visible as a data-quality problem.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from ..intelligence.extract import PageExtractor
from ..intelligence.html_text import CleanPage
from ..intelligence.schema import PageType, Source, SourceType
from ..matching.matcher import match
from ..normalize.io import read_jsonl
from ..normalize.text import normalize_name
from ..profile.models import ApplicantProfile
from ..requirements.mapping import build_requirements
from ..requirements.models import (
    AcademicRequirements,
    ExperienceRequirements,
    FieldValue,
    LanguageRequirements,
    Prerequisite,
    ProgramRequirements,
    Tests,
)
from .metrics import compute_metric
from .models import EvaluationMetric

_DATASETS = os.path.join(os.path.dirname(__file__), "datasets")


def dataset_path(name: str) -> str:
    return os.path.join(_DATASETS, name)


def _norm(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def evaluate_classification(classifications_path: str, gold_path: str = None) -> EvaluationMetric:
    gold_path = gold_path or dataset_path("classification_gold.jsonl")
    rows = {normalize_name(r.get("normalized_name") or r.get("name", "")): r for r in read_jsonl(classifications_path)}
    primary_pairs: List[Tuple[str, str]] = []
    relevance_pairs: List[Tuple[str, str]] = []
    primary_errors: List[str] = []
    relevance_errors: List[str] = []
    for item in read_jsonl(gold_path):
        predicted = rows.get(normalize_name(item["name"]))
        p_field = predicted.get("primary_field", "MISSING") if predicted else "MISSING"
        p_rel = predicted.get("relevance", "MISSING") if predicted else "MISSING"
        primary_pairs.append((item["expected_primary"], p_field))
        relevance_pairs.append((item["expected_relevance"], p_rel))
        if p_field != item["expected_primary"]:
            primary_errors.append(f"{item['name']!r}: primary {p_field} != {item['expected_primary']}")
        if p_rel != item["expected_relevance"]:
            relevance_errors.append(f"{item['name']!r}: relevance {p_rel} != {item['expected_relevance']}")

    primary = compute_metric("classification.primary_field", primary_pairs, primary_errors)
    relevance = compute_metric("classification.relevance", relevance_pairs, relevance_errors)
    # Aggregate both label sets into one headline metric.
    combined = compute_metric("classification.combined", primary_pairs + relevance_pairs, primary_errors + relevance_errors)
    combined.per_class = {**primary.per_class, **relevance.per_class}
    combined.confusion = {**primary.confusion, **relevance.confusion}
    return combined


def evaluate_universities(universities_path: str, gold_path: str = None) -> EvaluationMetric:
    gold_path = gold_path or dataset_path("university_gold.jsonl")
    alias_to_canonical: Dict[str, str] = {}
    for row in read_jsonl(universities_path):
        canonical = row.get("canonical_name", "")
        alias_to_canonical[normalize_name(canonical)] = canonical
        for alias in row.get("aliases", []) or []:
            alias_to_canonical[normalize_name(alias.get("alias", ""))] = canonical

    pairs: List[Tuple[str, str]] = []
    errors: List[str] = []
    for item in read_jsonl(gold_path):
        predicted = alias_to_canonical.get(normalize_name(item["raw"]), "MISSING")
        pairs.append((item["expected_canonical"], predicted))
        if predicted != item["expected_canonical"]:
            errors.append(f"{item['raw']!r}: got {predicted!r}, expected {item['expected_canonical']!r}")
    return compute_metric("university.normalization", pairs, errors)


def _norm_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse((url or "").strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def evaluate_page_classification(pages_path: str, gold_path: str = None) -> EvaluationMetric:
    gold_path = gold_path or dataset_path("page_classification_gold.jsonl")
    by_url = {_norm_url(row.get("url", "")): row.get("page_type", "MISSING") for row in read_jsonl(pages_path)}
    pairs: List[Tuple[str, str]] = []
    errors: List[str] = []
    for item in read_jsonl(gold_path):
        predicted = by_url.get(_norm_url(item["url"]), "MISSING")
        pairs.append((item["expected"], predicted))
        if predicted != item["expected"]:
            errors.append(f"{item['url']}: got {predicted}, expected {item['expected']}")
    return compute_metric("page.classification", pairs, errors)


# -- requirements -----------------------------------------------------------

def _fv(value, known: bool, status_unknown: str = "UNKNOWN") -> FieldValue:
    if known:
        return FieldValue(value=value, status="KNOWN")
    return FieldValue(value=None, status=status_unknown)


def _build_requirements(spec: Dict[str, Any]) -> ProgramRequirements:
    prereqs = [Prerequisite(category=c, requirement=c, credits=cr) for c, cr in spec.get("prereqs", [])]
    return ProgramRequirements(
        program_id="gold",
        university_id="gold",
        academic_requirements=AcademicRequirements(
            minimum_degree_level=_fv(spec.get("degree_level"), spec.get("degree_level") is not None, "UNKNOWN"),
            accepted_backgrounds=[_fv(a, True) for a in spec.get("accepted", [])],
            related_degree_allowed=_fv(spec["related"], True, "UNKNOWN") if "related" in spec else FieldValue(),
            minimum_gpa=_fv(spec.get("gpa"), spec.get("gpa") is not None),
            minimum_gpa_scale=_fv(spec.get("gpa_scale"), spec.get("gpa_scale") is not None),
        ),
        prerequisites=prereqs,
        language_requirements=LanguageRequirements(
            english_required=_fv(spec.get("english_required", True), True),
            ielts=_fv(spec.get("ielts"), spec.get("ielts") is not None, "NOT_MENTIONED"),
        ),
        tests=Tests(),
        experience=ExperienceRequirements(
            required=_fv(spec.get("exp_required"), "exp_required" in spec, "NOT_MENTIONED"),
            minimum_years=_fv(spec.get("exp_years"), spec.get("exp_years") is not None),
        ),
    )


def evaluate_eligibility(gold_path: str = None) -> EvaluationMetric:
    gold_path = gold_path or dataset_path("eligibility_gold.jsonl")
    pairs: List[Tuple[str, str]] = []
    errors: List[str] = []
    for item in read_jsonl(gold_path):
        profile = ApplicantProfile(**item["profile"])
        requirements = _build_requirements(item["requirements"])
        assessment = match(profile, requirements)
        pairs.append((item["expected_state"], assessment.state.value))
        if assessment.state.value != item["expected_state"]:
            errors.append(
                f"{item['id']}: got {assessment.state.value}, expected {item['expected_state']} "
                f"({assessment.reasons[0] if assessment.reasons else ''})"
            )
    return compute_metric("eligibility.state", pairs, errors)


def evaluate_requirements(gold_path: str = None) -> EvaluationMetric:
    gold_path = gold_path or dataset_path("requirements_gold.jsonl")
    source = Source(id="gold", url="https://example.edu/requirements", source_type=SourceType.OFFICIAL_UNIVERSITY,
                    page_type=PageType.ADMISSION_REQUIREMENTS, tier=1)
    extractor = PageExtractor(source, country_hint="United Kingdom")

    all_pairs: List[Tuple[str, str]] = []
    per_field: Dict[str, List[Tuple[str, str]]] = {}
    errors: List[str] = []
    for item in read_jsonl(gold_path):
        page = CleanPage(url=source.url, title="Requirements", text=item["text"])
        intel = extractor.extract(page, {"program_name": item["id"], "country": "United Kingdom"})
        req = build_requirements("gold", "gold", intel, {"gold": source})

        predicted = {
            "degree_level": req.academic_requirements.minimum_degree_level.value,
            "gpa": req.academic_requirements.minimum_gpa.value,
            "ielts": req.language_requirements.ielts.value,
            "toefl": req.language_requirements.toefl.value,
            "gre": req.tests.gre_required.value,
            "gmat": req.tests.gmat_required.value,
            "deadline": req.application.deadline.value,
            "tuition": req.financial.tuition.value,
        }
        for field, expected in item["expected"].items():
            pair = (_norm(expected), _norm(predicted.get(field)))
            all_pairs.append(pair)
            per_field.setdefault(field, []).append(pair)
            if pair[0] != pair[1]:
                errors.append(f"{item['id']}.{field}: got {pair[1]}, expected {pair[0]}")

    metric = compute_metric("requirements.fields", all_pairs, errors)
    return metric


def run_all(paths: Dict[str, str]) -> Dict[str, EvaluationMetric]:
    metrics: List[EvaluationMetric] = []
    if paths.get("classifications"):
        metrics.append(evaluate_classification(paths["classifications"]))
    if paths.get("universities"):
        metrics.append(evaluate_universities(paths["universities"]))
    if paths.get("pages"):
        metrics.append(evaluate_page_classification(paths["pages"]))
    metrics.append(evaluate_requirements())
    metrics.append(evaluate_eligibility())
    return {m.name: m for m in metrics}
