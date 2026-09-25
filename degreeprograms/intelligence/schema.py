"""Canonical Program Intelligence schema.

Design notes
------------
* Every *scalar* field is represented as a :class:`Fact`, which carries value,
  status, source, evidence text and confidence (matching the project's core
  principle: FIELD -> VALUE -> SOURCE -> EVIDENCE -> CONFIDENCE).
* Repeated structures (intakes, fees, prerequisites, modules, ...) are typed
  records. Each record carries its own ``source_id`` / ``evidence_text`` so a
  reader can always trace a claim back to the page it came from.
* Unknown information is ``UNKNOWN`` (or ``NOT_MENTIONED`` for tests where the
  distinction matters). It is never guessed.
* The full master schema is defined now so that the extraction layer can grow
  into it without a breaking change. The first vertical slice only populates a
  subset; everything else defaults to UNKNOWN/empty.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ValueStatus(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    NOT_MENTIONED = "NOT_MENTIONED"


class TestStatus(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    RECOMMENDED = "RECOMMENDED"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_ACCEPTED = "NOT_ACCEPTED"
    WAIVED = "WAIVED"
    NOT_MENTIONED = "NOT_MENTIONED"
    UNKNOWN = "UNKNOWN"


class SourceType(str, Enum):
    OFFICIAL_UNIVERSITY = "OFFICIAL_UNIVERSITY"
    OFFICIAL_GOVERNMENT = "OFFICIAL_GOVERNMENT"
    AGGREGATOR = "AGGREGATOR"
    OTHER = "OTHER"


class PageType(str, Enum):
    PROGRAM = "PROGRAM"
    ADMISSION_REQUIREMENTS = "ADMISSION_REQUIREMENTS"
    APPLICATION = "APPLICATION"
    FEES = "FEES"
    FUNDING = "FUNDING"
    CURRICULUM = "CURRICULUM"
    HANDBOOK = "HANDBOOK"
    INTERNATIONAL = "INTERNATIONAL"
    CONTACT = "CONTACT"
    OTHER = "OTHER"


class DeliveryMode(str, Enum):
    ON_CAMPUS = "ON_CAMPUS"
    ONLINE = "ONLINE"
    HYBRID = "HYBRID"
    DISTANCE = "DISTANCE"
    PART_TIME = "PART_TIME"
    FULL_TIME = "FULL_TIME"
    EXECUTIVE = "EXECUTIVE"
    UNKNOWN = "UNKNOWN"


class Fact(BaseModel):
    """Atomic extracted value with provenance."""

    model_config = ConfigDict(extra="ignore")

    value: Any = None
    status: ValueStatus = ValueStatus.UNKNOWN
    source_id: Optional[str] = None
    evidence_text: Optional[str] = None
    confidence: Optional[float] = None
    raw: Optional[str] = None
    # For CONFLICTING facts: every competing value is retained.
    values: List[Dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def known(
        cls,
        value: Any,
        source_id: Optional[str] = None,
        evidence_text: Optional[str] = None,
        confidence: Optional[float] = None,
        raw: Optional[str] = None,
    ) -> "Fact":
        if value is None:
            return cls()
        return cls(
            value=value,
            status=ValueStatus.KNOWN,
            source_id=source_id,
            evidence_text=evidence_text,
            confidence=confidence,
            raw=raw,
        )

    @classmethod
    def missing(cls, status: ValueStatus = ValueStatus.UNKNOWN) -> "Fact":
        return cls(status=status)

    def is_known(self) -> bool:
        return self.status == ValueStatus.KNOWN and self.value is not None


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    url: str
    title: Optional[str] = None
    source_type: SourceType = SourceType.OFFICIAL_UNIVERSITY
    page_type: PageType = PageType.OTHER
    retrieved_at: Optional[str] = None
    content_hash: Optional[str] = None
    last_updated: Optional[str] = None
    tier: int = 1
    http_status: Optional[int] = None
    is_pdf: bool = False


# ---------------------------------------------------------------------------
# Value records
# ---------------------------------------------------------------------------


class EvidenceRecord(BaseModel):
    """Base for repeated structures: keeps record-level provenance."""

    model_config = ConfigDict(extra="ignore")

    source_id: Optional[str] = None
    evidence_text: Optional[str] = None
    confidence: Optional[float] = None


class Identity(EvidenceRecord):
    program_name: Fact = Field(default_factory=Fact)
    official_program_name: Fact = Field(default_factory=Fact)
    degree_name: Fact = Field(default_factory=Fact)
    degree_abbreviation: Fact = Field(default_factory=Fact)
    degree_level: Fact = Field(default_factory=Fact)
    degree_type: Fact = Field(default_factory=Fact)
    faculty: Fact = Field(default_factory=Fact)
    school: Fact = Field(default_factory=Fact)
    department: Fact = Field(default_factory=Fact)
    discipline: List[Fact] = Field(default_factory=list)
    specializations: List[Fact] = Field(default_factory=list)
    program_id_official: Fact = Field(default_factory=Fact)


class University(EvidenceRecord):
    name: Fact = Field(default_factory=Fact)
    official_domain: Fact = Field(default_factory=Fact)
    country: Fact = Field(default_factory=Fact)


class Location(EvidenceRecord):
    country: Fact = Field(default_factory=Fact)
    region: Fact = Field(default_factory=Fact)
    city: Fact = Field(default_factory=Fact)
    campus: Fact = Field(default_factory=Fact)
    address: Fact = Field(default_factory=Fact)
    study_locations: List[Fact] = Field(default_factory=list)
    delivery_mode: Fact = Field(default_factory=Fact)
    attendance_required: Fact = Field(default_factory=Fact)


class Classification(EvidenceRecord):
    field: List[Fact] = Field(default_factory=list)
    subfield: List[Fact] = Field(default_factory=list)
    specializations: List[Fact] = Field(default_factory=list)
    research_areas: List[Fact] = Field(default_factory=list)
    program_tags: List[Fact] = Field(default_factory=list)


class Description(EvidenceRecord):
    short_description: Fact = Field(default_factory=Fact)
    full_description: Fact = Field(default_factory=Fact)
    objectives: List[Fact] = Field(default_factory=list)
    learning_outcomes: List[Fact] = Field(default_factory=list)
    program_highlights: List[Fact] = Field(default_factory=list)


class Study(EvidenceRecord):
    study_mode: Fact = Field(default_factory=Fact)
    attendance: Fact = Field(default_factory=Fact)
    delivery: Fact = Field(default_factory=Fact)
    language: Fact = Field(default_factory=Fact)


class Duration(EvidenceRecord):
    value: Fact = Field(default_factory=Fact)
    unit: Fact = Field(default_factory=Fact)
    months: Fact = Field(default_factory=Fact)
    semesters: Fact = Field(default_factory=Fact)
    credits: Fact = Field(default_factory=Fact)


class Credits(EvidenceRecord):
    total: Fact = Field(default_factory=Fact)
    system: Fact = Field(default_factory=Fact)


class Intake(EvidenceRecord):
    intake_name: Optional[str] = None
    term: Optional[str] = None
    start_date: Optional[str] = None
    start_month: Optional[str] = None
    start_year: Optional[int] = None
    application_open_date: Optional[str] = None
    application_deadline: Optional[str] = None
    international_application_deadline: Optional[str] = None
    late_application_deadline: Optional[str] = None
    deposit_deadline: Optional[str] = None
    enrollment_deadline: Optional[str] = None
    academic_year: Optional[str] = None
    raw: Optional[str] = None


class ApplicationWindow(EvidenceRecord):
    opens: Optional[str] = None
    deadline: Optional[str] = None
    international_deadline: Optional[str] = None
    domestic_deadline: Optional[str] = None
    early_deadline: Optional[str] = None
    regular_deadline: Optional[str] = None
    late_deadline: Optional[str] = None
    rolling_admission: Optional[bool] = None
    academic_year: Optional[str] = None
    raw: Optional[str] = None


class DeadlineRecord(EvidenceRecord):
    type: str
    date: Optional[str] = None
    raw: Optional[str] = None
    condition: Optional[str] = None
    academic_year: Optional[str] = None


class ApplicationFee(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    amount: Fact = Field(default_factory=Fact)
    currency: Fact = Field(default_factory=Fact)
    waivable: Fact = Field(default_factory=Fact)
    refundable: Fact = Field(default_factory=Fact)
    notes: Fact = Field(default_factory=Fact)


class Tuition(EvidenceRecord):
    amount: Fact = Field(default_factory=Fact)
    currency: Fact = Field(default_factory=Fact)
    period: Fact = Field(default_factory=Fact)
    per_year: Fact = Field(default_factory=Fact)
    per_semester: Fact = Field(default_factory=Fact)
    per_credit: Fact = Field(default_factory=Fact)
    total_program: Fact = Field(default_factory=Fact)
    eu_fee: Fact = Field(default_factory=Fact)
    international_fee: Fact = Field(default_factory=Fact)
    domestic_fee: Fact = Field(default_factory=Fact)
    fee_status: Fact = Field(default_factory=Fact)


class OtherFee(EvidenceRecord):
    name: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    frequency: Optional[str] = None
    mandatory: Optional[bool] = None
    raw: Optional[str] = None


class TotalCost(EvidenceRecord):
    amount: Fact = Field(default_factory=Fact)
    currency: Fact = Field(default_factory=Fact)
    includes_tuition: Optional[bool] = None
    includes_other_fees: Optional[bool] = None


class Fees(EvidenceRecord):
    application_fee: ApplicationFee = Field(default_factory=ApplicationFee)
    tuition: Tuition = Field(default_factory=Tuition)
    other_fees: List[OtherFee] = Field(default_factory=list)
    estimated_total_program_cost: TotalCost = Field(default_factory=TotalCost)


class Language(EvidenceRecord):
    instruction: List[Fact] = Field(default_factory=list)
    application: List[Fact] = Field(default_factory=list)
    thesis: List[Fact] = Field(default_factory=list)
    required_language: Fact = Field(default_factory=Fact)


class TestScore(EvidenceRecord):
    required: bool = False
    status: TestStatus = TestStatus.NOT_MENTIONED
    minimum_overall: Optional[float] = None
    minimum_total: Optional[float] = None
    minimum_score: Optional[float] = None
    minimum_sections: Dict[str, float] = Field(default_factory=dict)
    academic: Optional[bool] = None
    accepted: Optional[bool] = None
    notes: Optional[str] = None
    raw: Optional[str] = None


class EnglishRequirements(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    ielts: TestScore = Field(default_factory=TestScore)
    toefl: TestScore = Field(default_factory=TestScore)
    pte: TestScore = Field(default_factory=TestScore)
    cambridge: TestScore = Field(default_factory=TestScore)
    duolingo: TestScore = Field(default_factory=TestScore)
    other_tests: List[TestScore] = Field(default_factory=list)
    waivers: List[Fact] = Field(default_factory=list)
    exemptions: List[Fact] = Field(default_factory=list)


class StandardizedTest(EvidenceRecord):
    name: str
    status: TestStatus = TestStatus.NOT_MENTIONED
    minimum_score: Optional[float] = None
    quantitative_minimum: Optional[float] = None
    verbal_minimum: Optional[float] = None
    analytical_minimum: Optional[float] = None
    validity_period: Optional[str] = None
    waiver: Optional[str] = None
    notes: Optional[str] = None
    raw: Optional[str] = None


class SpecialAssessment(EvidenceRecord):
    name: str
    type: str = "OTHER"
    required: Optional[bool] = None
    date: Optional[str] = None
    registration_deadline: Optional[str] = None
    description: Optional[str] = None


class AcademicBackground(EvidenceRecord):
    minimum_degree: Fact = Field(default_factory=Fact)
    accepted_fields: List[Fact] = Field(default_factory=list)
    preferred_fields: List[Fact] = Field(default_factory=list)
    related_fields_allowed: Fact = Field(default_factory=Fact)
    specific_degree_required: Fact = Field(default_factory=Fact)
    specific_institution_required: Fact = Field(default_factory=Fact)


class AcademicPerformance(EvidenceRecord):
    minimum_gpa: Fact = Field(default_factory=Fact)
    gpa_scale: Fact = Field(default_factory=Fact)
    minimum_percentage: Fact = Field(default_factory=Fact)
    minimum_grade: Fact = Field(default_factory=Fact)
    grading_system: Fact = Field(default_factory=Fact)
    equivalent_requirements: List[Fact] = Field(default_factory=list)


class AcademicRequirements(EvidenceRecord):
    background: AcademicBackground = Field(default_factory=AcademicBackground)
    performance: AcademicPerformance = Field(default_factory=AcademicPerformance)


class Prerequisite(EvidenceRecord):
    category: str
    subject: Optional[str] = None
    required: Optional[bool] = True
    credits: Optional[float] = None
    credit_system: Optional[str] = None
    minimum_grade: Optional[str] = None
    raw: Optional[str] = None


class WorkExperience(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    preferred: Fact = Field(default_factory=Fact)
    minimum_years: Fact = Field(default_factory=Fact)
    relevant_fields: List[Fact] = Field(default_factory=list)
    notes: Fact = Field(default_factory=Fact)


class ExecutiveRequirements(EvidenceRecord):
    minimum_experience_years: Fact = Field(default_factory=Fact)
    current_employment_required: Fact = Field(default_factory=Fact)
    managerial_experience_required: Fact = Field(default_factory=Fact)


class ApplicationRequirement(EvidenceRecord):
    item: str
    required: Optional[bool] = None
    notes: Optional[str] = None


class RecommendationLetters(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    number: Fact = Field(default_factory=Fact)
    academic_required: Fact = Field(default_factory=Fact)
    professional_allowed: Fact = Field(default_factory=Fact)
    professional_required: Fact = Field(default_factory=Fact)


class Statement(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    type: Fact = Field(default_factory=Fact)
    word_limit: Fact = Field(default_factory=Fact)
    page_limit: Fact = Field(default_factory=Fact)
    specific_prompts: List[Fact] = Field(default_factory=list)


class Cv(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    maximum_pages: Fact = Field(default_factory=Fact)
    format: Fact = Field(default_factory=Fact)


class Portfolio(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    description: Fact = Field(default_factory=Fact)


class Documents(EvidenceRecord):
    application_requirements: List[ApplicationRequirement] = Field(default_factory=list)
    recommendation_letters: RecommendationLetters = Field(default_factory=RecommendationLetters)
    statement: Statement = Field(default_factory=Statement)
    cv: Cv = Field(default_factory=Cv)
    portfolio: Portfolio = Field(default_factory=Portfolio)


class Module(EvidenceRecord):
    name: str
    credits: Optional[float] = None
    credit_system: Optional[str] = None
    type: str = "OTHER"
    semester: Optional[str] = None


class Specialization(EvidenceRecord):
    name: str
    description: Optional[str] = None
    modules: List[str] = Field(default_factory=list)


class Curriculum(EvidenceRecord):
    core_modules: List[Module] = Field(default_factory=list)
    electives: List[Module] = Field(default_factory=list)
    specializations: List[Specialization] = Field(default_factory=list)
    tracks: List[str] = Field(default_factory=list)
    semesters: List[str] = Field(default_factory=list)
    modules: List[Module] = Field(default_factory=list)


class Thesis(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    optional: Fact = Field(default_factory=Fact)
    duration: Fact = Field(default_factory=Fact)
    credits: Fact = Field(default_factory=Fact)
    semester: Fact = Field(default_factory=Fact)
    industry_thesis: Fact = Field(default_factory=Fact)


class Research(EvidenceRecord):
    research_oriented: Fact = Field(default_factory=Fact)
    research_areas: List[Fact] = Field(default_factory=list)
    research_groups: List[Fact] = Field(default_factory=list)
    labs: List[Fact] = Field(default_factory=list)
    research_centers: List[Fact] = Field(default_factory=list)
    faculty: List[Fact] = Field(default_factory=list)
    thesis: Thesis = Field(default_factory=Thesis)
    research_project: Fact = Field(default_factory=Fact)


class Industry(EvidenceRecord):
    internship_required: Fact = Field(default_factory=Fact)
    internship_optional: Fact = Field(default_factory=Fact)
    internship_duration: Fact = Field(default_factory=Fact)
    industry_project: Fact = Field(default_factory=Fact)
    placement: Fact = Field(default_factory=Fact)
    co_op: Fact = Field(default_factory=Fact)


class Scholarship(EvidenceRecord):
    name: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    coverage: Optional[str] = None
    eligibility: Optional[str] = None
    deadline: Optional[str] = None
    automatic: Optional[bool] = None
    separate_application: Optional[bool] = None
    category: Optional[str] = None
    source_url: Optional[str] = None


class Funding(EvidenceRecord):
    assistantships: List[Fact] = Field(default_factory=list)
    teaching_assistantships: List[Fact] = Field(default_factory=list)
    research_assistantships: List[Fact] = Field(default_factory=list)
    funding_opportunities: List[Fact] = Field(default_factory=list)


class ApplicationPortal(EvidenceRecord):
    url: Fact = Field(default_factory=Fact)
    platform: Fact = Field(default_factory=Fact)
    requires_account: Fact = Field(default_factory=Fact)


class Interview(EvidenceRecord):
    required: Fact = Field(default_factory=Fact)
    type: Fact = Field(default_factory=Fact)
    format: Fact = Field(default_factory=Fact)
    duration: Fact = Field(default_factory=Fact)
    topics: List[Fact] = Field(default_factory=list)


class AdmissionDecision(EvidenceRecord):
    expected_time: Fact = Field(default_factory=Fact)
    rolling: Fact = Field(default_factory=Fact)
    decision_rounds: List[Fact] = Field(default_factory=list)


class Accreditation(EvidenceRecord):
    body: str
    status: Optional[str] = None
    details: Optional[str] = None


class Ranking(EvidenceRecord):
    system: str
    category: Optional[str] = None
    rank: Optional[int] = None
    year: Optional[int] = None


class Career(EvidenceRecord):
    career_paths: List[Fact] = Field(default_factory=list)
    industries: List[Fact] = Field(default_factory=list)
    employment_outcomes: List[Fact] = Field(default_factory=list)
    placement_rate: Fact = Field(default_factory=Fact)
    median_salary: Fact = Field(default_factory=Fact)
    outcome_year: Optional[int] = None
    outcome_population: Optional[int] = None
    outcome_methodology: Optional[str] = None


class Cohort(EvidenceRecord):
    size: Fact = Field(default_factory=Fact)
    international_percentage: Fact = Field(default_factory=Fact)
    countries_represented: Fact = Field(default_factory=Fact)


class FacultyMember(EvidenceRecord):
    name: str
    title: Optional[str] = None
    research_areas: List[str] = Field(default_factory=list)
    profile_url: Optional[str] = None


class ResearchInfrastructure(EvidenceRecord):
    name: str
    type: str = "OTHER"
    description: Optional[str] = None
    url: Optional[str] = None


class Contact(EvidenceRecord):
    type: str = "ADMISSIONS"
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    url: Optional[str] = None


class LivingCost(EvidenceRecord):
    estimate: Fact = Field(default_factory=Fact)
    currency: Fact = Field(default_factory=Fact)
    period: Fact = Field(default_factory=Fact)
    source: Fact = Field(default_factory=Fact)
    university_provided: Optional[bool] = None


class InternationalStudents(EvidenceRecord):
    accepted: Fact = Field(default_factory=Fact)
    separate_application_process: Fact = Field(default_factory=Fact)
    additional_requirements: List[Fact] = Field(default_factory=list)
    visa_required: Fact = Field(default_factory=Fact)


class Completeness(BaseModel):
    model_config = ConfigDict(extra="allow")
    identity: bool = False
    fees: bool = False
    deadlines: bool = False
    requirements: bool = False
    english_tests: bool = False
    gre: bool = False
    gmat: bool = False
    curriculum: bool = False
    research: bool = False


class ProgramIntelligence(BaseModel):
    """Master canonical object (Section 60)."""

    model_config = ConfigDict(extra="ignore")

    identity: Identity = Field(default_factory=Identity)
    university: University = Field(default_factory=University)
    location: Location = Field(default_factory=Location)
    classification: Classification = Field(default_factory=Classification)
    description: Description = Field(default_factory=Description)
    study: Study = Field(default_factory=Study)
    duration: Duration = Field(default_factory=Duration)
    credits: Credits = Field(default_factory=Credits)
    intakes: List[Intake] = Field(default_factory=list)
    application: ApplicationWindow = Field(default_factory=ApplicationWindow)
    deadlines: List[DeadlineRecord] = Field(default_factory=list)
    fees: Fees = Field(default_factory=Fees)
    language: Language = Field(default_factory=Language)
    academic_requirements: AcademicRequirements = Field(default_factory=AcademicRequirements)
    prerequisites: List[Prerequisite] = Field(default_factory=list)
    english_requirements: EnglishRequirements = Field(default_factory=EnglishRequirements)
    gre: StandardizedTest = Field(default_factory=lambda: StandardizedTest(name="GRE"))
    gmat: StandardizedTest = Field(default_factory=lambda: StandardizedTest(name="GMAT"))
    standardized_tests: List[StandardizedTest] = Field(default_factory=list)
    special_admission_assessments: List[SpecialAssessment] = Field(default_factory=list)
    documents: Documents = Field(default_factory=Documents)
    work_experience: WorkExperience = Field(default_factory=WorkExperience)
    executive_requirements: ExecutiveRequirements = Field(default_factory=ExecutiveRequirements)
    curriculum: Curriculum = Field(default_factory=Curriculum)
    specializations: List[Specialization] = Field(default_factory=list)
    thesis: Thesis = Field(default_factory=Thesis)
    research: Research = Field(default_factory=Research)
    industry: Industry = Field(default_factory=Industry)
    scholarships: List[Scholarship] = Field(default_factory=list)
    funding: Funding = Field(default_factory=Funding)
    application_portal: ApplicationPortal = Field(default_factory=ApplicationPortal)
    application_process: List[Fact] = Field(default_factory=list)
    interview: Interview = Field(default_factory=Interview)
    admission_decision: AdmissionDecision = Field(default_factory=AdmissionDecision)
    accreditation: List[Accreditation] = Field(default_factory=list)
    rankings: List[Ranking] = Field(default_factory=list)
    career: Career = Field(default_factory=Career)
    cohort: Cohort = Field(default_factory=Cohort)
    faculty: List[FacultyMember] = Field(default_factory=list)
    research_infrastructure: List[ResearchInfrastructure] = Field(default_factory=list)
    contacts: List[Contact] = Field(default_factory=list)
    living_cost: LivingCost = Field(default_factory=LivingCost)
    international_students: InternationalStudents = Field(default_factory=InternationalStudents)
    sources: List[Source] = Field(default_factory=list)
    completeness: Completeness = Field(default_factory=Completeness)

    # provenance / versioning
    retrieved_at: Optional[str] = None
    crawler_version: Optional[str] = None
    extractor_version: Optional[str] = None
    schema_version: Optional[str] = None
    extraction_status: str = "OK"
    notes: List[str] = Field(default_factory=list)
