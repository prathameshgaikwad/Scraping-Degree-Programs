"""Models for program relevance classification (Phase 3)."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Relevance(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class ClassificationMethod(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    LLM = "LLM"
    HYBRID = "HYBRID"


class ProgramClassification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: str
    university_id: str
    name: str
    normalized_name: str

    primary_field: str = "UNKNOWN"
    secondary_fields: List[str] = Field(default_factory=list)
    relevance: Relevance = Relevance.UNKNOWN
    confidence: float = 0.0
    reason: str = ""
    evidence: Dict[str, List[str]] = Field(default_factory=dict)
    scores: Dict[str, int] = Field(default_factory=dict)

    basis: str = "TITLE"
    method: ClassificationMethod = ClassificationMethod.DETERMINISTIC
    classifier_version: str = ""
    classified_at: Optional[str] = None


class LLMClassification(BaseModel):
    """Strict schema for LLM fallback output."""

    model_config = ConfigDict(extra="forbid")

    primary_field: str
    secondary_fields: List[str] = Field(default_factory=list)
    relevance: Relevance
    confidence: float
    reason: str


class ClassificationManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    programs_path: str
    programs_sha256: str
    classifier_version: str
    schema_version: str
    generated_at: str
    programs: int
    by_relevance: Dict[str, int] = Field(default_factory=dict)
    by_primary_field: Dict[str, int] = Field(default_factory=dict)
    by_method: Dict[str, int] = Field(default_factory=dict)
    llm_calls: int = 0
    cache_hits: int = 0
