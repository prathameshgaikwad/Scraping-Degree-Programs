"""Strict requirement schema (Section 13) with first-class evidence (Section 14).

Every value carries a status; missing information is ``UNKNOWN`` and never
guessed. Evidence is only ever taken from a page we actually crawled — a URL is
never generated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    page_title: Optional[str] = None
    quote: Optional[str] = None
    retrieved_at: Optional[str] = None
    source_tier: Optional[int] = None
    page_type: Optional[str] = None


class FieldValue(BaseModel):
    """A single extracted requirement value with provenance."""

    model_config = ConfigDict(extra="ignore")

    value: Any = None
    status: str = "UNKNOWN"  # KNOWN | UNKNOWN | NOT_APPLICABLE | AMBIGUOUS | CONFLICTING | NOT_MENTIONED
    raw: Optional[str] = None
    confidence: Optional[float] = None
    evidence: List[Evidence] = Field(default_factory=list)


class AcademicRequirements(BaseModel):
    model_config = ConfigDict(extra="ignore")

    minimum_degree_level: FieldValue = Field(default_factory=FieldValue)
    accepted_backgrounds: List[FieldValue] = Field(default_factory=list)
    related_degree_allowed: FieldValue = Field(default_factory=FieldValue)
    minimum_gpa: FieldValue = Field(default_factory=FieldValue)
    minimum_gpa_scale: FieldValue = Field(default_factory=FieldValue)
    minimum_percentage: FieldValue = Field(default_factory=FieldValue)
    minimum_grade: FieldValue = Field(default_factory=FieldValue)


class Prerequisite(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str
    requirement: Optional[str] = None
    credits: Optional[float] = None
    credit_system: Optional[str] = None
    evidence: List[Evidence] = Field(default_factory=list)


class LanguageRequirements(BaseModel):
    model_config = ConfigDict(extra="ignore")

    english_required: FieldValue = Field(default_factory=FieldValue)
    ielts: FieldValue = Field(default_factory=FieldValue)
    toefl: FieldValue = Field(default_factory=FieldValue)
    pte: FieldValue = Field(default_factory=FieldValue)
    duolingo: FieldValue = Field(default_factory=FieldValue)
    cambridge: FieldValue = Field(default_factory=FieldValue)


class Tests(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gre_required: FieldValue = Field(default_factory=FieldValue)
    gmat_required: FieldValue = Field(default_factory=FieldValue)


class ExperienceRequirements(BaseModel):
    model_config = ConfigDict(extra="ignore")

    required: FieldValue = Field(default_factory=FieldValue)
    preferred: FieldValue = Field(default_factory=FieldValue)
    minimum_years: FieldValue = Field(default_factory=FieldValue)


class ApplicationInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    deadline: FieldValue = Field(default_factory=FieldValue)
    opens: FieldValue = Field(default_factory=FieldValue)
    international_deadline: FieldValue = Field(default_factory=FieldValue)
    application_fee: FieldValue = Field(default_factory=FieldValue)
    rolling_admission: FieldValue = Field(default_factory=FieldValue)


class FinancialInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tuition: FieldValue = Field(default_factory=FieldValue)
    currency: FieldValue = Field(default_factory=FieldValue)
    period: FieldValue = Field(default_factory=FieldValue)


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_id: str
    url: str
    title: Optional[str] = None
    page_type: Optional[str] = None
    source_tier: Optional[int] = None
    retrieved_at: Optional[str] = None
    content_hash: Optional[str] = None
    is_pdf: bool = False


class RequirementsCompleteness(BaseModel):
    model_config = ConfigDict(extra="ignore")

    academic: bool = False
    prerequisites: bool = False
    language: bool = False
    tests: bool = False
    experience: bool = False
    application: bool = False
    financial: bool = False


class ProgramRequirements(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: str
    university_id: str
    program_name: Optional[str] = None
    university_name: Optional[str] = None

    academic_requirements: AcademicRequirements = Field(default_factory=AcademicRequirements)
    prerequisites: List[Prerequisite] = Field(default_factory=list)
    language_requirements: LanguageRequirements = Field(default_factory=LanguageRequirements)
    tests: Tests = Field(default_factory=Tests)
    experience: ExperienceRequirements = Field(default_factory=ExperienceRequirements)
    application: ApplicationInfo = Field(default_factory=ApplicationInfo)
    financial: FinancialInfo = Field(default_factory=FinancialInfo)

    sources: List[SourceInfo] = Field(default_factory=list)
    completeness: RequirementsCompleteness = Field(default_factory=RequirementsCompleteness)

    extractor_version: str = ""
    extracted_at: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class RequirementsManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages_path: str
    programs_path: str
    extractor_version: str
    schema_version: str
    generated_at: str
    programs: int
    pages_considered: int
    pages_extracted: int
    cache_hits: int
    by_completeness: Dict[str, int] = Field(default_factory=dict)
    programs_with_evidence: int = 0
