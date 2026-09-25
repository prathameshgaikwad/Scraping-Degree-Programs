"""Models for the official-site crawl layer (Phase 5)."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PageType(str, Enum):
    PROGRAM_PAGE = "PROGRAM_PAGE"
    ADMISSION_PAGE = "ADMISSION_PAGE"
    REQUIREMENTS_PAGE = "REQUIREMENTS_PAGE"
    TUITION_PAGE = "TUITION_PAGE"
    APPLICATION_PAGE = "APPLICATION_PAGE"
    CURRICULUM_PAGE = "CURRICULUM_PAGE"
    INTERNATIONAL_STUDENTS_PAGE = "INTERNATIONAL_STUDENTS_PAGE"
    SCHOLARSHIP_PAGE = "SCHOLARSHIP_PAGE"
    IRRELEVANT = "IRRELEVANT"
    UNKNOWN = "UNKNOWN"


class CrawlStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    IN_PROGRESS = "IN_PROGRESS"
    UNKNOWN = "UNKNOWN"


class SourceTier(str, Enum):
    """Section 15 source priority (lower number = higher priority)."""

    PROGRAM_PAGE = "TIER_1_PROGRAM"
    ADMISSIONS = "TIER_2_ADMISSIONS"
    INTERNATIONAL = "TIER_3_INTERNATIONAL"
    REGULATIONS = "TIER_4_REGULATIONS"
    NATIONAL_DB = "TIER_5_NATIONAL_DB"
    AGGREGATOR = "TIER_6_AGGREGATOR"
    SNIPPET = "TIER_7_SNIPPET"
    UNKNOWN = "UNKNOWN"


class CrawlTarget(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: str
    university_id: str
    program_name: str
    university_name: Optional[str] = None
    relevance: Optional[str] = None
    target_field_codes: List[str] = Field(default_factory=list)
    official_domain: Optional[str] = None
    qs_program_url: Optional[str] = None


class PageLink(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    text: str = ""
    score: float = 0.0
    page_type: PageType = PageType.UNKNOWN


class CrawledPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_id: str
    program_id: str
    university_id: str
    program_ids: List[str] = Field(default_factory=list)
    url: str
    final_url: str
    title: Optional[str] = None
    page_type: PageType = PageType.UNKNOWN
    source_tier: SourceTier = SourceTier.UNKNOWN
    http_status: Optional[int] = None
    content_hash: Optional[str] = None
    is_pdf: bool = False
    depth: int = 0
    text: str = ""
    headings: List[str] = Field(default_factory=list)
    tables: int = 0
    pdf_links: List[str] = Field(default_factory=list)
    links: List[PageLink] = Field(default_factory=list)
    last_updated: Optional[str] = None
    retrieved_at: Optional[str] = None
    crawl_status: CrawlStatus = CrawlStatus.UNKNOWN
    error: Optional[str] = None
    from_cache: bool = False
    rendered: bool = False


class CrawlJobRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: str
    university_id: str
    status: CrawlStatus = CrawlStatus.UNKNOWN
    reason: Optional[str] = None
    start_url: Optional[str] = None
    pages_crawled: int = 0
    pdfs_crawled: int = 0
    requests_made: int = 0
    attempts: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    parser_version: str = ""
    crawler_version: str = ""


class CrawlManifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    classifications_path: str
    programs_path: str
    universities_path: str
    crawler_version: str
    parser_version: str
    schema_version: str
    generated_at: str
    candidates: int
    jobs_success: int = 0
    jobs_failed: int = 0
    jobs_skipped: int = 0
    jobs_resumed_skipped: int = 0
    jobs_blocked: int = 0
    jobs_timed_out: int = 0
    blocked_domains: List[str] = Field(default_factory=list)
    programs_processed: int = 0
    stopped_early: bool = False
    remaining: int = 0
    pages: int = 0
    pdfs: int = 0
    pages_by_type: Dict[str, int] = Field(default_factory=dict)
    domains_resolved: int = 0
    domains_missing: int = 0
