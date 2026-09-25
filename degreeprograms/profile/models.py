"""Applicant profile schema (Phase 4).

The applicant is configuration, never hardcoded into the matching engine: any
other applicant can be substituted by pointing the pipeline at a different
profile file. Missing information stays ``None``/empty — nothing is invented.

Coursework is only populated when the applicant supplies it. Professional
experience is a separate dimension from academic coursework (see Section 20).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..normalize.text import normalize_name


class EducationLevel(str, Enum):
    HIGHER_SECONDARY = "HIGHER_SECONDARY"
    DIPLOMA = "DIPLOMA"
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    DOCTORATE = "DOCTORATE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class CourseworkCategory(str, Enum):
    PROGRAMMING = "PROGRAMMING"
    COMPUTER_SCIENCE = "COMPUTER_SCIENCE"
    ALGORITHMS = "ALGORITHMS"
    DATA_STRUCTURES = "DATA_STRUCTURES"
    MATHEMATICS = "MATHEMATICS"
    LINEAR_ALGEBRA = "LINEAR_ALGEBRA"
    CALCULUS = "CALCULUS"
    PROBABILITY = "PROBABILITY"
    STATISTICS = "STATISTICS"
    DATABASES = "DATABASES"
    OPERATING_SYSTEMS = "OPERATING_SYSTEMS"
    NETWORKS = "NETWORKS"
    MACHINE_LEARNING = "MACHINE_LEARNING"
    ARTIFICIAL_INTELLIGENCE = "ARTIFICIAL_INTELLIGENCE"
    DATA_SCIENCE = "DATA_SCIENCE"
    PHYSICS = "PHYSICS"
    ENGINEERING = "ENGINEERING"
    ECONOMICS = "ECONOMICS"
    OTHER = "OTHER"


# Target field (free text) -> classification taxonomy code.
TARGET_FIELD_MAP: Dict[str, str] = {
    "artificial intelligence": "ARTIFICIAL_INTELLIGENCE",
    "ai": "ARTIFICIAL_INTELLIGENCE",
    "machine learning": "MACHINE_LEARNING",
    "ml": "MACHINE_LEARNING",
    "deep learning": "MACHINE_LEARNING",
    "computer science": "COMPUTER_SCIENCE",
    "computing": "COMPUTER_SCIENCE",
    "software engineering": "COMPUTER_SCIENCE",
    "data science": "DATA_SCIENCE",
    "data analytics": "DATA_ANALYTICS",
    "analytics": "DATA_ANALYTICS",
    "robotics": "ROBOTICS",
    "computer vision": "COMPUTER_VISION",
    "natural language processing": "NLP",
    "nlp": "NLP",
    "intelligent systems": "INTELLIGENT_SYSTEMS",
    "computational science": "COMPUTATIONAL_SCIENCE",
}

_LEVEL_ORDER = {
    EducationLevel.UNKNOWN: 0,
    EducationLevel.HIGHER_SECONDARY: 1,
    EducationLevel.DIPLOMA: 2,
    EducationLevel.BACHELOR: 3,
    EducationLevel.MASTER: 4,
    EducationLevel.DOCTORATE: 5,
    EducationLevel.OTHER: 0,
}

_DEGREE_LEVEL_PATTERNS = [
    (r"\bph\s*d\b|\bdoctora|\bd\s*phil", EducationLevel.DOCTORATE),
    (r"\bm\s*tech\b|\bm\s*sc\b|\bm\s*a\b|\bmba\b|\bmaster|\bm\s*eng\b|\bm\s*s\b", EducationLevel.MASTER),
    (r"\bb\s*tech\b|\bb\s*e\b|\bb\s*sc\b|\bb\s*a\b|\bb\s*com\b|\bbachelor|\bb\s*s\b", EducationLevel.BACHELOR),
    (r"\bdiploma\b", EducationLevel.DIPLOMA),
    (r"higher secondary|senior secondary|\bhsc\b|\b12th\b", EducationLevel.HIGHER_SECONDARY),
]

_FIELD_CATEGORY_PATTERNS = [
    (r"computer|software|information technology|\bit\b", CourseworkCategory.COMPUTER_SCIENCE),
    (r"machine learning", CourseworkCategory.MACHINE_LEARNING),
    (r"artificial intelligence", CourseworkCategory.ARTIFICIAL_INTELLIGENCE),
    (r"data", CourseworkCategory.DATA_SCIENCE),
    (r"statistic", CourseworkCategory.STATISTICS),
    (r"probabilit", CourseworkCategory.PROBABILITY),
    (r"linear algebra", CourseworkCategory.LINEAR_ALGEBRA),
    (r"calculus|analysis", CourseworkCategory.CALCULUS),
    (r"mathematic|maths", CourseworkCategory.MATHEMATICS),
    (r"algorithm", CourseworkCategory.ALGORITHMS),
    (r"data structure", CourseworkCategory.DATA_STRUCTURES),
    (r"database|\bsql\b", CourseworkCategory.DATABASES),
    (r"operating system", CourseworkCategory.OPERATING_SYSTEMS),
    (r"network", CourseworkCategory.NETWORKS),
    (r"physic", CourseworkCategory.PHYSICS),
    (r"economic|econometr", CourseworkCategory.ECONOMICS),
    (r"metallurg|material|mechanical|civil|electrical|chemical|engineering", CourseworkCategory.ENGINEERING),
]


def infer_education_level(degree: Optional[str]) -> EducationLevel:
    text = normalize_name(degree or "")
    if not text:
        return EducationLevel.UNKNOWN
    for pattern, level in _DEGREE_LEVEL_PATTERNS:
        if re.search(pattern, text):
            return level
    return EducationLevel.UNKNOWN


def infer_field_category(field: Optional[str]) -> Optional[CourseworkCategory]:
    text = normalize_name(field or "")
    if not text:
        return None
    for pattern, category in _FIELD_CATEGORY_PATTERNS:
        if re.search(pattern, text):
            return category
    return CourseworkCategory.OTHER


class Education(BaseModel):
    model_config = ConfigDict(extra="ignore")

    degree: str
    degree_level: Optional[EducationLevel] = None
    field: Optional[str] = None
    field_category: Optional[CourseworkCategory] = None
    institution: Optional[str] = None
    country: Optional[str] = None
    cgpa: Optional[float] = None
    cgpa_scale: Optional[float] = None
    percentage: Optional[float] = None
    graduation_year: Optional[int] = None
    transcript_available: Optional[bool] = None

    @model_validator(mode="after")
    def _derive(self) -> "Education":
        if self.degree_level is None:
            self.degree_level = infer_education_level(self.degree)
        if self.field_category is None:
            self.field_category = infer_field_category(self.field)
        return self

    @field_validator("cgpa")
    @classmethod
    def _cgpa_non_negative(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("cgpa must be >= 0")
        return value

    @model_validator(mode="after")
    def _cgpa_within_scale(self) -> "Education":
        if self.cgpa is not None and self.cgpa_scale is not None and self.cgpa > self.cgpa_scale:
            raise ValueError(f"cgpa {self.cgpa} exceeds cgpa_scale {self.cgpa_scale}")
        return self


class Experience(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    years: float
    field: Optional[str] = None
    domain: Optional[str] = None
    description: Optional[str] = None
    current: Optional[bool] = None

    @field_validator("years")
    @classmethod
    def _years_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("years must be >= 0")
        return value


class Preferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    english_taught: Optional[bool] = None
    full_time: Optional[bool] = None
    preferred_countries: List[str] = Field(default_factory=list)
    excluded_countries: List[str] = Field(default_factory=list)
    maximum_tuition: Optional[float] = None
    maximum_tuition_currency: Optional[str] = None
    maximum_duration_months: Optional[int] = None
    scholarship_required: Optional[bool] = None


class Testing(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ielts: Optional[float] = None
    toefl: Optional[float] = None
    pte: Optional[float] = None
    duolingo: Optional[float] = None
    gre: Optional[float] = None
    gmat: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("ielts")
    @classmethod
    def _ielts_range(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not (0 <= value <= 9.5):
            raise ValueError("ielts must be between 0 and 9.5")
        return value

    @field_validator("toefl")
    @classmethod
    def _toefl_range(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not (0 <= value <= 120):
            raise ValueError("toefl must be between 0 and 120")
        return value


class Coursework(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    category: Optional[CourseworkCategory] = None
    credits: Optional[float] = None
    credit_system: Optional[str] = None
    grade: Optional[str] = None

    @model_validator(mode="after")
    def _derive_category(self) -> "Coursework":
        if self.category is None:
            self.category = infer_field_category(self.name)
        return self

    @field_validator("credits")
    @classmethod
    def _credits_non_negative(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("credits must be >= 0")
        return value


class ApplicantProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    applicant_id: str = "default"
    name: Optional[str] = None
    education: List[Education] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    target_fields: List[str] = Field(default_factory=list)
    target_field_codes: List[str] = Field(default_factory=list)
    technical_background: List[str] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    testing: Testing = Field(default_factory=Testing)
    coursework: List[Coursework] = Field(default_factory=list)
    notes: Optional[str] = None
    metadata: Dict[str, object] = Field(default_factory=dict)

    @field_validator("education", mode="before")
    @classmethod
    def _wrap_single_education(cls, value):
        if isinstance(value, dict):
            return [value]
        return value

    @model_validator(mode="after")
    def _derive_target_codes(self) -> "ApplicantProfile":
        codes: List[str] = []
        for field in self.target_fields:
            code = TARGET_FIELD_MAP.get(normalize_name(field))
            if code and code not in codes:
                codes.append(code)
        self.target_field_codes = codes
        return self

    # -- derived helpers -----------------------------------------------------
    @property
    def primary_education(self) -> Optional[Education]:
        return self.education[0] if self.education else None

    @property
    def highest_degree_level(self) -> EducationLevel:
        if not self.education:
            return EducationLevel.UNKNOWN
        return max(
            (e.degree_level or EducationLevel.UNKNOWN for e in self.education),
            key=lambda level: _LEVEL_ORDER.get(level, 0),
        )

    @property
    def total_experience_years(self) -> float:
        return round(sum(e.years for e in self.experience), 2)

    def coursework_by_category(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for course in self.coursework:
            key = (course.category or CourseworkCategory.OTHER).value
            result.setdefault(key, []).append(course.name)
        return result
