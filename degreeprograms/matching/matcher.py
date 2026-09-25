"""Deterministic eligibility matcher (Sections 16-20).

Compares an applicant profile against extracted requirements and returns an
explicit eligibility state with per-dimension results and evidence. It answers
"does the available evidence indicate the applicant satisfies the stated
requirements?" — never "will they be admitted?", and it produces no probability
or fit score.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..profile.models import ApplicantProfile, EducationLevel, infer_field_category
from ..requirements.mapping import infer_degree_level
from ..requirements.models import Evidence, FieldValue, ProgramRequirements
from .models import (
    Dimension,
    DimensionStatus,
    EligibilityAssessment,
    EligibilityState,
)
from .versions import MATCHER_VERSION

_LEVEL_RANK = {
    EducationLevel.UNKNOWN: 0,
    EducationLevel.OTHER: 0,
    EducationLevel.HIGHER_SECONDARY: 1,
    EducationLevel.DIPLOMA: 2,
    EducationLevel.BACHELOR: 3,
    EducationLevel.MASTER: 4,
    EducationLevel.DOCTORATE: 5,
}
_DEGREE_RANK = {"HIGHER_SECONDARY": 1, "DIPLOMA": 2, "BACHELOR": 3, "MASTER": 4, "DOCTORATE": 5}


def _dim(name, status, reason, applicant=None, requirement=None, evidence=None) -> Dimension:
    return Dimension(
        name=name,
        status=status,
        reason=reason,
        applicant_value=applicant,
        requirement_value=requirement,
        evidence=evidence or [],
    )


def _unique_evidence(dimensions: Dict[str, Dimension]) -> List[Evidence]:
    out: List[Evidence] = []
    seen = set()
    for dim in dimensions.values():
        for ev in dim.evidence:
            key = (ev.url, ev.quote)
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    return out


def _degree_level(profile: ApplicantProfile, req: ProgramRequirements) -> Dimension:
    fv = req.academic_requirements.minimum_degree_level
    evidence = list(fv.evidence)
    level = fv.value if fv.status == "KNOWN" else None
    raw = fv.raw
    if level is None:
        # UK-style requirements state "2:1 honours degree" (a grade) rather than a
        # degree level; infer the level from the grade phrase if possible.
        grade_fv = req.academic_requirements.minimum_grade
        if grade_fv.status == "KNOWN" and grade_fv.value:
            inferred = infer_degree_level(str(grade_fv.value))
            if inferred:
                level = inferred
                raw = str(grade_fv.value)
                evidence = list(grade_fv.evidence) + evidence

    if level is None:
        return _dim(
            "degree_level",
            DimensionStatus.UNCLEAR,
            "Minimum degree level is not clearly stated on the source pages.",
            applicant=profile.highest_degree_level.value,
            requirement=fv.raw or fv.value,
            evidence=evidence,
        )
    applicant_level = profile.highest_degree_level
    if applicant_level == EducationLevel.UNKNOWN:
        return _dim(
            "degree_level", DimensionStatus.UNKNOWN, "Applicant education is not on record.",
            requirement=level, evidence=evidence,
        )
    req_rank = _DEGREE_RANK.get(str(level), 0)
    app_rank = _LEVEL_RANK.get(applicant_level, 0)
    if app_rank >= req_rank:
        return _dim(
            "degree_level", DimensionStatus.PASS,
            f"Applicant holds {applicant_level.value}; requirement is {level}.",
            applicant=applicant_level.value, requirement=level, evidence=evidence,
        )
    if str(level) in ("MASTER", "DOCTORATE"):
        # A Master's programme requiring a Master's/Doctorate is unusual; treat as
        # needing verification rather than a hard rejection.
        return _dim(
            "degree_level", DimensionStatus.UNCLEAR,
            f"Source states a {level} entry requirement; this is unusual for a Master's programme and needs verification.",
            applicant=applicant_level.value, requirement=level, evidence=evidence,
        )
    return _dim(
        "degree_level", DimensionStatus.FAIL,
        f"Applicant's highest degree ({applicant_level.value}) is below the required {level}.",
        applicant=applicant_level.value, requirement=level, evidence=evidence,
    )


def _academic_field(profile: ApplicantProfile, req: ProgramRequirements) -> Dimension:
    accepted = [fv for fv in req.academic_requirements.accepted_backgrounds if fv.value]
    related_fv = req.academic_requirements.related_degree_allowed
    related_allowed = related_fv.value if related_fv.status == "KNOWN" else None
    evidence = [e for fv in accepted for e in fv.evidence] + list(related_fv.evidence)

    primary = profile.primary_education
    if primary is None or not primary.field:
        return _dim("academic_field", DimensionStatus.UNKNOWN, "Applicant field of study is not on record.",
                    evidence=evidence)

    if not accepted and related_allowed is None:
        return _dim("academic_field", DimensionStatus.UNCLEAR,
                    "No academic background requirement was extracted.", evidence=evidence)

    applicant_cat = primary.field_category.value if primary.field_category else None
    accepted_cats = set()
    accepted_tokens = set()
    for fv in accepted:
        text = str(fv.value)
        cat = infer_field_category(text)
        if cat:
            accepted_cats.add(cat.value)
        accepted_tokens.update(t for t in text.lower().replace(",", " ").split() if len(t) > 3)

    applicant_tokens = set(t for t in (primary.field or "").lower().split() if len(t) > 3)
    if (applicant_cat and applicant_cat in accepted_cats) or (applicant_tokens & accepted_tokens):
        return _dim("academic_field", DimensionStatus.PASS,
                    f"Applicant background ({primary.field}) matches an accepted background.",
                    applicant=primary.field, requirement="; ".join(str(f.value) for f in accepted) or None,
                    evidence=evidence)
    if related_allowed:
        return _dim("academic_field", DimensionStatus.UNCLEAR,
                    f"Applicant background ({primary.field}) is not an exact match; a 'related field' clause applies and needs verification.",
                    applicant=primary.field, requirement="related field allowed", evidence=evidence)
    if accepted_cats and related_allowed is False:
        return _dim("academic_field", DimensionStatus.FAIL,
                    f"Applicant background ({primary.field}) is not among the stated accepted backgrounds.",
                    applicant=primary.field, requirement="; ".join(str(f.value) for f in accepted),
                    evidence=evidence)
    return _dim("academic_field", DimensionStatus.UNCLEAR,
                "Academic background requirement is ambiguous.", applicant=primary.field, evidence=evidence)


def _gpa(profile: ApplicantProfile, req: ProgramRequirements) -> Dimension:
    gv = req.academic_requirements.minimum_gpa
    if gv.status != "KNOWN" or gv.value is None:
        return _dim("gpa", DimensionStatus.NOT_APPLICABLE, "No minimum GPA is stated.",
                    evidence=gv.evidence)
    primary = profile.primary_education
    if primary is None or primary.cgpa is None:
        return _dim("gpa", DimensionStatus.UNKNOWN, "Applicant GPA is not on record.",
                    requirement=gv.value, evidence=gv.evidence)
    req_scale = req.academic_requirements.minimum_gpa_scale.value
    if primary.cgpa_scale is None or req_scale is None:
        return _dim("gpa", DimensionStatus.UNCLEAR,
                    "Cannot compare GPA without a matching grade scale (no conversion applied).",
                    applicant=primary.cgpa, requirement=gv.value, evidence=gv.evidence)
    if float(primary.cgpa_scale) != float(req_scale):
        return _dim("gpa", DimensionStatus.UNCLEAR,
                    f"Applicant and requirement use different grade scales ({primary.cgpa_scale} vs {req_scale}); no conversion applied.",
                    applicant=primary.cgpa, requirement=gv.value, evidence=gv.evidence)
    if primary.cgpa >= gv.value:
        return _dim("gpa", DimensionStatus.PASS,
                    f"Applicant GPA {primary.cgpa}/{primary.cgpa_scale} meets the required {gv.value}/{req_scale}.",
                    applicant=primary.cgpa, requirement=gv.value, evidence=gv.evidence)
    return _dim("gpa", DimensionStatus.FAIL,
                f"Applicant GPA {primary.cgpa}/{primary.cgpa_scale} is below the required {gv.value}/{req_scale}.",
                applicant=primary.cgpa, requirement=gv.value, evidence=gv.evidence)


def _english(profile: ApplicantProfile, req: ProgramRequirements) -> Dimension:
    lr = req.language_requirements
    listed = {
        "ielts": lr.ielts,
        "toefl": lr.toefl,
        "pte": lr.pte,
        "duolingo": lr.duolingo,
    }
    with_min = {k: fv for k, fv in listed.items() if fv.status == "KNOWN" and isinstance(fv.value, (int, float))}
    evidence = [e for fv in listed.values() for e in fv.evidence] + list(lr.english_required.evidence)
    eng_required = lr.english_required.value if lr.english_required.status == "KNOWN" else None

    if eng_required is False and not with_min:
        return _dim("english", DimensionStatus.NOT_APPLICABLE, "English proficiency is not required.",
                    evidence=evidence)
    if not with_min:
        if eng_required:
            return _dim("english", DimensionStatus.UNKNOWN,
                        "English is required but no minimum score was extracted.", evidence=evidence)
        return _dim("english", DimensionStatus.UNCLEAR, "English requirement is not clearly extracted.",
                    evidence=evidence)

    satisfied: List[str] = []
    below: List[str] = []
    for name, fv in with_min.items():
        score = getattr(profile.testing, name)
        if score is None:
            continue
        if score >= fv.value:
            satisfied.append(f"{name.upper()} {score} >= {fv.value}")
        else:
            below.append(f"{name.upper()} {score} < {fv.value}")

    if satisfied:
        return _dim("english", DimensionStatus.PASS, "Applicant meets: " + "; ".join(satisfied),
                    applicant=f"ielts={profile.testing.ielts}, toefl={profile.testing.toefl}",
                    requirement="; ".join(f"{k.upper()} {v.value}" for k, v in with_min.items()),
                    evidence=evidence)
    if below:
        return _dim("english", DimensionStatus.FAIL, "Applicant test scores are below the requirement: " + "; ".join(below),
                    applicant=f"ielts={profile.testing.ielts}, toefl={profile.testing.toefl}",
                    requirement="; ".join(f"{k.upper()} {v.value}" for k, v in with_min.items()),
                    evidence=evidence)
    return _dim("english", DimensionStatus.UNKNOWN,
                "No English test score is on record.", requirement="; ".join(f"{k.upper()} {v.value}" for k, v in with_min.items()),
                evidence=evidence)


def _work_experience(profile: ApplicantProfile, req: ProgramRequirements) -> Dimension:
    we = req.experience
    required = we.required.value if we.required.status == "KNOWN" else None
    minimum_years = we.minimum_years.value
    evidence = list(we.required.evidence) + list(we.minimum_years.evidence)
    if required is False:
        return _dim("work_experience", DimensionStatus.NOT_APPLICABLE, "Work experience is not required.",
                    evidence=evidence)
    if required is None:
        preferred = we.preferred.value if we.preferred.status == "KNOWN" else None
        if preferred:
            return _dim("work_experience", DimensionStatus.NOT_APPLICABLE,
                        "Work experience is preferred but not required.", evidence=evidence)
        return _dim("work_experience", DimensionStatus.NOT_APPLICABLE,
                    "No work-experience requirement is stated.", evidence=evidence)

    years = profile.total_experience_years
    if minimum_years is not None:
        if years >= minimum_years:
            return _dim("work_experience", DimensionStatus.PASS,
                        f"Applicant has {years} years; requirement is {minimum_years} years.",
                        applicant=years, requirement=minimum_years, evidence=evidence)
        return _dim("work_experience", DimensionStatus.FAIL,
                    f"Applicant has {years} years; requirement is {minimum_years} years.",
                    applicant=years, requirement=minimum_years, evidence=evidence)
    if years > 0:
        return _dim("work_experience", DimensionStatus.PASS,
                    f"Applicant has {years} years of experience; amount unspecified.",
                    applicant=years, evidence=evidence)
    return _dim("work_experience", DimensionStatus.UNCLEAR,
                "Work experience is required but the amount is unspecified, and the applicant has none on record.",
                evidence=evidence)


def _prerequisites(profile: ApplicantProfile, req: ProgramRequirements) -> Dict[str, Dimension]:
    dims: Dict[str, Dimension] = {}
    by_category: Dict[str, list] = {}
    for prereq in req.prerequisites:
        by_category.setdefault(prereq.category, []).append(prereq)

    for category, prereqs in by_category.items():
        name = category.lower()
        evidence = [e for p in prereqs for e in p.evidence]
        required_credits = next((p.credits for p in prereqs if p.credits), None)
        requirement_text = prereqs[0].requirement
        if not profile.coursework:
            dims[name] = _dim(name, DimensionStatus.UNKNOWN,
                              "No coursework supplied by the applicant; cannot verify.",
                              requirement=requirement_text, evidence=evidence)
            continue
        courses = [c for c in profile.coursework if c.category and c.category.value == category]
        if not courses:
            # Professional experience is tracked separately and does NOT satisfy
            # an academic prerequisite (Section 20).
            dims[name] = _dim(name, DimensionStatus.GAP,
                              f"No documented {category} coursework on the applicant's record.",
                              requirement=requirement_text, evidence=evidence)
            continue
        credits = sum(c.credits or 0 for c in courses)
        if required_credits and credits < required_credits:
            dims[name] = _dim(name, DimensionStatus.GAP,
                              f"Documented {category} credits ({credits}) are below the required {required_credits}.",
                              applicant=credits, requirement=required_credits, evidence=evidence)
        else:
            dims[name] = _dim(name, DimensionStatus.PASS,
                              f"Applicant has documented {category} coursework.",
                              applicant=credits or None, requirement=required_credits, evidence=evidence)
    return dims


def _overall(requirements: ProgramRequirements, dimensions: Dict[str, Dimension]) -> EligibilityState:
    prereq_names = [n for n in dimensions if n not in {"degree_level", "academic_field", "gpa", "english", "work_experience"}]
    hard = ["degree_level", "gpa", "english", "work_experience"]
    if any(dimensions[n].status == DimensionStatus.FAIL for n in hard if n in dimensions):
        return EligibilityState.NOT_ELIGIBLE
    if any(dimensions[n].status == DimensionStatus.GAP for n in prereq_names):
        return EligibilityState.PREREQUISITE_GAP
    if dimensions.get("degree_level") and dimensions["degree_level"].status == DimensionStatus.UNCLEAR:
        return EligibilityState.UNCLEAR
    mandatory = hard + prereq_names + ["academic_field"]
    if any(dimensions[n].status in (DimensionStatus.UNKNOWN, DimensionStatus.UNCLEAR) for n in mandatory if n in dimensions):
        return EligibilityState.LIKELY_ELIGIBLE
    return EligibilityState.ELIGIBLE


def match(
    profile: ApplicantProfile,
    requirements: ProgramRequirements,
    program_name: Optional[str] = None,
    university_name: Optional[str] = None,
) -> EligibilityAssessment:
    dimensions: Dict[str, Dimension] = {
        "degree_level": _degree_level(profile, requirements),
        "academic_field": _academic_field(profile, requirements),
        "gpa": _gpa(profile, requirements),
        "english": _english(profile, requirements),
        "work_experience": _work_experience(profile, requirements),
    }
    dimensions.update(_prerequisites(profile, requirements))

    state = _overall(requirements, dimensions)
    gaps = [n for n, d in dimensions.items() if d.status == DimensionStatus.GAP]
    uncertain = [n for n, d in dimensions.items() if d.status in (DimensionStatus.UNKNOWN, DimensionStatus.UNCLEAR)]
    failed = [n for n, d in dimensions.items() if d.status == DimensionStatus.FAIL]

    reasons = [f"{state.value}: {_summary_line(state, failed, gaps, uncertain)}"]
    for name, dim in dimensions.items():
        reasons.append(f"{name}: {dim.status.value} - {dim.reason}")

    return EligibilityAssessment(
        program_id=requirements.program_id,
        university_id=requirements.university_id,
        program_name=program_name,
        university_name=university_name,
        applicant_id=profile.applicant_id,
        state=state,
        dimensions=dimensions,
        prerequisite_gaps=gaps,
        uncertain=uncertain,
        failed=failed,
        reasons=reasons,
        evidence=_unique_evidence(dimensions),
        matcher_version=MATCHER_VERSION,
    )


def _summary_line(state: EligibilityState, failed: List[str], gaps: List[str], uncertain: List[str]) -> str:
    if state == EligibilityState.NOT_ELIGIBLE:
        return "explicit requirement not met: " + ", ".join(failed)
    if state == EligibilityState.PREREQUISITE_GAP:
        return "missing/insufficient prerequisites: " + ", ".join(gaps)
    if state == EligibilityState.ELIGIBLE:
        return "all known mandatory requirements appear satisfied"
    if state == EligibilityState.LIKELY_ELIGIBLE:
        return "no failures, but items need verification: " + ", ".join(uncertain)
    return "requirements insufficiently extracted to determine"
