"""Map merged intelligence output into the strict requirement schema.

Values, statuses, conflicts and evidence all come from the intelligence layer's
``Fact`` objects. Evidence URLs are looked up from the crawled ``Source`` — if a
fact has no source, it gets no evidence (never a fabricated URL).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..intelligence.schema import (
    Fact,
    ProgramIntelligence,
    Source,
    StandardizedTest,
    TestScore,
    ValueStatus,
)
from .models import (
    AcademicRequirements,
    ApplicationInfo,
    Evidence,
    ExperienceRequirements,
    FieldValue,
    FinancialInfo,
    LanguageRequirements,
    Prerequisite,
    ProgramRequirements,
    RequirementsCompleteness,
    SourceInfo,
    Tests,
)
from .versions import REQUIREMENTS_EXTRACTOR_VERSION

_QUOTE_LIMIT = 320


def _quote(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_QUOTE_LIMIT] if text else None


def _evidence(source_id: Optional[str], quote: Optional[str], sources: Dict[str, Source]) -> List[Evidence]:
    source = sources.get(source_id or "")
    if source is None:
        return []
    return [
        Evidence(
            url=source.url,
            page_title=source.title,
            quote=_quote(quote),
            retrieved_at=source.retrieved_at,
            source_tier=source.tier,
            page_type=source.page_type.value if source.page_type else None,
        )
    ]


def _fv(fact: Optional[Fact], sources: Dict[str, Source]) -> FieldValue:
    if fact is None:
        return FieldValue()
    if fact.status == ValueStatus.CONFLICTING and fact.values:
        evidence: List[Evidence] = []
        for entry in fact.values:
            evidence.extend(_evidence(entry.get("source"), entry.get("evidence"), sources))
        return FieldValue(
            value=fact.value,
            status="CONFLICTING",
            raw=fact.raw,
            confidence=fact.confidence,
            evidence=evidence,
        )
    if not fact.is_known() and fact.status in (ValueStatus.UNKNOWN, ValueStatus.NOT_MENTIONED):
        return FieldValue(status=fact.status.value, raw=fact.raw)
    return FieldValue(
        value=fact.value,
        status=fact.status.value,
        raw=fact.raw,
        confidence=fact.confidence,
        evidence=_evidence(fact.source_id, fact.evidence_text, sources),
    )


def _test_fv(test: Optional[TestScore], sources: Dict[str, Source]) -> FieldValue:
    if test is None or test.status.value in ("NOT_MENTIONED", "UNKNOWN"):
        return FieldValue(status=test.status.value if test else "UNKNOWN")
    value = test.minimum_overall
    if value is None:
        value = test.minimum_total
    if value is None:
        value = test.minimum_score
    if value is None and test.minimum_sections:
        value = test.minimum_sections
    return FieldValue(
        value=value,
        status="KNOWN" if value is not None else "AMBIGUOUS",
        raw=test.raw,
        confidence=test.confidence,
        evidence=_evidence(test.source_id, test.evidence_text, sources),
    )


def _status_fv(test: Optional[StandardizedTest], sources: Dict[str, Source]) -> FieldValue:
    if test is None:
        return FieldValue()
    status = test.status.value
    if status == "NOT_MENTIONED":
        return FieldValue(status="NOT_MENTIONED")
    return FieldValue(
        value=status,
        status="KNOWN",
        raw=test.raw,
        confidence=test.confidence,
        evidence=_evidence(test.source_id, test.evidence_text, sources),
    )


def infer_degree_level(text: Optional[str]) -> Optional[str]:
    """Infer the entry degree level from a phrase.

    Uses the *earliest* degree keyword so that "a bachelor's degree that grants
    eligibility for master's level education" resolves to BACHELOR, not MASTER.
    """
    if not text:
        return None
    low = text.lower()
    candidates = []
    for pattern, level in (
        (r"\bph\s*d\b|doctora|d\s*phil", "DOCTORATE"),
        (r"master|postgraduate", "MASTER"),
        (
            r"bachelor|undergraduate|first degree|honours|honors|"
            r"2:1|2:2|first class|upper second|lower second|third class",
            "BACHELOR",
        ),
    ):
        match = re.search(pattern, low)
        if match:
            candidates.append((match.start(), level))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], 0 if c[1] == "BACHELOR" else 1))
    return candidates[0][1]


def _degree_level_fv(fact: Optional[Fact], sources: Dict[str, Source]) -> FieldValue:
    if fact is None or not fact.is_known():
        return _fv(fact, sources)
    level = infer_degree_level(str(fact.value))
    evidence = _evidence(fact.source_id, fact.evidence_text, sources)
    if level is None:
        return FieldValue(
            value=None,
            status="AMBIGUOUS",
            raw=str(fact.value),
            confidence=fact.confidence,
            evidence=evidence,
        )
    return FieldValue(value=level, status="KNOWN", raw=str(fact.value), confidence=fact.confidence, evidence=evidence)


def _known(fv: FieldValue) -> bool:
    return fv.status == "KNOWN" and fv.value is not None


def build_requirements(
    program_id: str,
    university_id: str,
    merged: ProgramIntelligence,
    sources: Dict[str, Source],
    program_name: Optional[str] = None,
    university_name: Optional[str] = None,
    used_page_ids: Optional[List[str]] = None,
) -> ProgramRequirements:
    intel = merged

    academic = AcademicRequirements(
        minimum_degree_level=_degree_level_fv(intel.academic_requirements.background.minimum_degree, sources),
        accepted_backgrounds=[_fv(f, sources) for f in intel.academic_requirements.background.accepted_fields],
        related_degree_allowed=_fv(intel.academic_requirements.background.related_fields_allowed, sources),
        minimum_gpa=_fv(intel.academic_requirements.performance.minimum_gpa, sources),
        minimum_gpa_scale=_fv(intel.academic_requirements.performance.gpa_scale, sources),
        minimum_percentage=_fv(intel.academic_requirements.performance.minimum_percentage, sources),
        minimum_grade=_fv(intel.academic_requirements.performance.minimum_grade, sources),
    )

    prerequisites = [
        Prerequisite(
            category=p.category,
            requirement=p.subject or p.raw,
            credits=p.credits,
            credit_system=p.credit_system,
            evidence=_evidence(p.source_id, p.evidence_text, sources),
        )
        for p in intel.prerequisites
    ]

    language = LanguageRequirements(
        english_required=_fv(intel.english_requirements.required, sources),
        ielts=_test_fv(intel.english_requirements.ielts, sources),
        toefl=_test_fv(intel.english_requirements.toefl, sources),
        pte=_test_fv(intel.english_requirements.pte, sources),
        duolingo=_test_fv(intel.english_requirements.duolingo, sources),
        cambridge=_test_fv(intel.english_requirements.cambridge, sources),
    )

    tests = Tests(
        gre_required=_status_fv(intel.gre, sources),
        gmat_required=_status_fv(intel.gmat, sources),
    )

    experience = ExperienceRequirements(
        required=_fv(intel.work_experience.required, sources),
        preferred=_fv(intel.work_experience.preferred, sources),
        minimum_years=_fv(intel.work_experience.minimum_years, sources),
    )

    application = ApplicationInfo(
        deadline=_fv(Fact.known(intel.application.deadline, intel.application.source_id, intel.application.evidence_text)
                     if intel.application.deadline else Fact(), sources),
        opens=_fv(Fact.known(intel.application.opens, intel.application.source_id, intel.application.evidence_text)
                  if intel.application.opens else Fact(), sources),
        international_deadline=_fv(
            Fact.known(intel.application.international_deadline, intel.application.source_id, intel.application.evidence_text)
            if intel.application.international_deadline else Fact(), sources),
        application_fee=_fv(intel.fees.application_fee.amount, sources),
        rolling_admission=_fv(Fact.known(True, intel.application.source_id, intel.application.evidence_text)
                              if intel.application.rolling_admission else Fact(), sources),
    )

    financial = FinancialInfo(
        tuition=_fv(intel.fees.tuition.amount, sources),
        currency=_fv(intel.fees.tuition.currency, sources),
        period=_fv(intel.fees.tuition.period, sources),
    )

    completeness = RequirementsCompleteness(
        academic=any(_known(v) for v in (
            academic.minimum_degree_level, academic.minimum_gpa, academic.related_degree_allowed,
        )) or bool(academic.accepted_backgrounds),
        prerequisites=bool(prerequisites),
        language=_known(language.english_required)
        or any(_known(t) for t in (language.ielts, language.toefl, language.pte, language.duolingo, language.cambridge)),
        tests=any(t.status == "KNOWN" for t in (tests.gre_required, tests.gmat_required)),
        experience=any(_known(v) for v in (experience.required, experience.preferred, experience.minimum_years)),
        application=any(_known(v) for v in (application.deadline, application.opens, application.application_fee)),
        financial=_known(financial.tuition) or _known(financial.currency),
    )

    source_infos: List[SourceInfo] = []
    for page_id in (used_page_ids or list(sources.keys())):
        source = sources.get(page_id)
        if source is None:
            continue
        source_infos.append(
            SourceInfo(
                page_id=page_id,
                url=source.url,
                title=source.title,
                page_type=source.page_type.value if source.page_type else None,
                source_tier=source.tier,
                retrieved_at=source.retrieved_at,
                content_hash=source.content_hash,
                is_pdf=source.is_pdf,
            )
        )

    return ProgramRequirements(
        program_id=program_id,
        university_id=university_id,
        program_name=program_name,
        university_name=university_name,
        academic_requirements=academic,
        prerequisites=prerequisites,
        language_requirements=language,
        tests=tests,
        experience=experience,
        application=application,
        financial=financial,
        sources=source_infos,
        completeness=completeness,
        extractor_version=REQUIREMENTS_EXTRACTOR_VERSION,
    )
