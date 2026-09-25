"""Models for eligibility matching (Sections 16-18).

No fit score, no probability. Each dimension carries an explicit status and a
reason; the assessment carries an explicit eligibility state.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..requirements.models import Evidence


class DimensionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    GAP = "GAP"                    # required prerequisite absent/insufficient
    UNKNOWN = "UNKNOWN"            # applicant information missing
    UNCLEAR = "UNCLEAR"           # requirement ambiguous / not comparable
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EligibilityState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    LIKELY_ELIGIBLE = "LIKELY_ELIGIBLE"
    PREREQUISITE_GAP = "PREREQUISITE_GAP"
    UNCLEAR = "UNCLEAR"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class Dimension(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    status: DimensionStatus
    reason: str = ""
    applicant_value: Any = None
    requirement_value: Any = None
    evidence: List[Evidence] = Field(default_factory=list)


class EligibilityAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: str
    university_id: str
    program_name: Optional[str] = None
    university_name: Optional[str] = None
    applicant_id: str = "default"

    state: EligibilityState = EligibilityState.UNCLEAR
    dimensions: Dict[str, Dimension] = Field(default_factory=dict)
    prerequisite_gaps: List[str] = Field(default_factory=list)
    uncertain: List[str] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)

    method: str = "DETERMINISTIC"
    matcher_version: str = ""
    matched_at: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class MatchManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requirements_path: str
    programs_path: str
    profile_path: str
    matcher_version: str
    schema_version: str
    generated_at: str
    programs: int
    by_state: Dict[str, int] = Field(default_factory=dict)
    cache_hits: int = 0
    llm_calls: int = 0
