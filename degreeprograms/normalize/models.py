"""Canonical models for the normalization layer (Phase 2).

These are the NORMALIZED representations. Raw QS records are never mutated and
never overwritten; normalized entities keep ``source_refs`` back to the raw
records so every alias/merge is traceable.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DegreeLevel(str, Enum):
    MASTER = "MASTER"
    POSTGRADUATE_DIPLOMA = "POSTGRADUATE_DIPLOMA"
    POSTGRADUATE_CERTIFICATE = "POSTGRADUATE_CERTIFICATE"
    UNKNOWN = "UNKNOWN"


class DegreeType(str, Enum):
    MSC = "MSC"
    MS = "MS"
    MA = "MA"
    MENG = "MENG"
    MBA = "MBA"
    MPHIL = "MPHIL"
    MRES = "MRES"
    LLM = "LLM"
    MPH = "MPH"
    MED = "MED"
    MARCH = "MARCH"
    MMATH = "MMATH"
    MPHYS = "MPHYS"
    MFIN = "MFIN"
    MPA = "MPA"
    MPP = "MPP"
    MFA = "MFA"
    PGDIP = "PGDIP"
    PGCERT = "PGCERT"
    MASTER = "MASTER"
    UNKNOWN = "UNKNOWN"


class ProgramFormat(str, Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    EXECUTIVE = "EXECUTIVE"
    ONLINE = "ONLINE"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class ResolutionMethod(str, Enum):
    QS_BASE_SLUG = "QS_BASE_SLUG"          # grouped by parent slug from QS URL
    ALIAS_REGISTRY = "ALIAS_REGISTRY"      # curated alias -> canonical
    EXACT_NAME = "EXACT_NAME"              # exact normalized-name match
    FUZZY_NAME = "FUZZY_NAME"              # fuzzy match across slugs
    FALLBACK_SLUG = "FALLBACK_SLUG"        # no QS slug; derived from name
    UNRESOLVED = "UNRESOLVED"


class DedupConfidence(str, Enum):
    HIGH = "HIGH"        # same base university + same normalized name + same degree
    MEDIUM = "MEDIUM"    # same base university + same normalized name
    LOW = "LOW"          # fuzzy


class Ranking(BaseModel):
    model_config = ConfigDict(extra="ignore")

    system: str = "QS"
    university_rank: Optional[int] = None
    rank_display: Optional[str] = None
    rank_low: Optional[int] = None
    rank_high: Optional[int] = None
    tied: bool = False
    is_range: bool = False
    is_plus: bool = False
    ranking_year: Optional[int] = None
    source_url: Optional[str] = None


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "QS"
    raw_index: int
    raw_record_hash: str
    program_url: Optional[str] = None
    university_url: Optional[str] = None
    source_search_url: Optional[str] = None


class UniversityAlias(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alias: str
    normalized: str
    kind: str = "RAW_UNIVERSITY_NAME"  # RAW_UNIVERSITY_NAME | ORG_UNIT | CAMPUS | KNOWN | URL_SLUG
    source: str = "QS"                 # QS | curated
    confidence: float = 0.8


class CanonicalUniversity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    university_id: str
    canonical_name: str
    aliases: List[UniversityAlias] = Field(default_factory=list)
    country: Optional[str] = None
    city: Optional[str] = None
    official_domain: Optional[str] = None
    qs: Ranking = Field(default_factory=Ranking)
    resolution_method: ResolutionMethod = ResolutionMethod.QS_BASE_SLUG
    confidence: float = 0.9
    needs_review: bool = False
    review_reasons: List[str] = Field(default_factory=list)
    source_refs: List[SourceRef] = Field(default_factory=list)


class ProgramLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    campus: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None


class CanonicalProgram(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: str
    university_id: str
    name: str
    normalized_name: str
    degree_level: DegreeLevel = DegreeLevel.MASTER
    degree_type: DegreeType = DegreeType.UNKNOWN
    degree_tokens: List[str] = Field(default_factory=list)
    program_format: ProgramFormat = ProgramFormat.UNKNOWN
    location: ProgramLocation = Field(default_factory=ProgramLocation)
    source: SourceRef
    ranking: Ranking = Field(default_factory=Ranking)

    # deduplication
    dedup_group_id: str
    dedup_confidence: DedupConfidence = DedupConfidence.HIGH
    is_primary: bool = True
    duplicate_of: Optional[str] = None
    merged_sources: List[SourceRef] = Field(default_factory=list)

    raw_name: Optional[str] = None


class NormalizationManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input_path: str
    input_sha256: str
    alias_registry_sha256: str = ""
    input_rows: int
    normalizer_version: str
    schema_version: str
    generated_at: str
    universities: int
    programs: int
    programs_deduplicated: int
    universities_needing_review: int
    programs_by_degree: dict = Field(default_factory=dict)
    programs_by_format: dict = Field(default_factory=dict)
    programs_by_country: dict = Field(default_factory=dict)
