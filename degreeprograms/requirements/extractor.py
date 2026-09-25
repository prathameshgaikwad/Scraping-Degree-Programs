"""Per-page requirement extraction, reusing the intelligence ``PageExtractor``.

Extraction is cached per (page_id, content_hash, extractor_version) so shared
pages are processed once and unchanged pages are never re-extracted (Section 24).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

from ..crawl.models import CrawledPage, PageType as CrawlPageType
from ..intelligence.extract import PageExtractor
from ..intelligence.html_text import CleanPage
from ..intelligence.schema import (
    PageType as IntelPageType,
    ProgramIntelligence,
    Source,
    SourceType,
)
from .versions import REQUIREMENTS_EXTRACTOR_VERSION

_PAGE_TYPE_MAP = {
    CrawlPageType.PROGRAM_PAGE: IntelPageType.PROGRAM,
    CrawlPageType.ADMISSION_PAGE: IntelPageType.ADMISSION_REQUIREMENTS,
    CrawlPageType.REQUIREMENTS_PAGE: IntelPageType.ADMISSION_REQUIREMENTS,
    CrawlPageType.TUITION_PAGE: IntelPageType.FEES,
    CrawlPageType.APPLICATION_PAGE: IntelPageType.APPLICATION,
    CrawlPageType.INTERNATIONAL_STUDENTS_PAGE: IntelPageType.INTERNATIONAL,
    CrawlPageType.CURRICULUM_PAGE: IntelPageType.CURRICULUM,
    CrawlPageType.SCHOLARSHIP_PAGE: IntelPageType.FUNDING,
    CrawlPageType.IRRELEVANT: IntelPageType.OTHER,
    CrawlPageType.UNKNOWN: IntelPageType.OTHER,
}


def make_source(page: CrawledPage) -> Source:
    return Source(
        id=page.page_id,
        url=page.url,
        title=page.title,
        source_type=SourceType.OFFICIAL_UNIVERSITY,
        page_type=_PAGE_TYPE_MAP.get(page.page_type, IntelPageType.OTHER),
        retrieved_at=page.retrieved_at,
        content_hash=page.content_hash,
        last_updated=page.last_updated,
        tier=1,
        http_status=page.http_status,
        is_pdf=page.is_pdf,
    )


def make_clean_page(page: CrawledPage) -> CleanPage:
    return CleanPage(url=page.url, title=page.title or "", text=page.text or "")


class PageExtractionCache:
    def __init__(self, path: str) -> None:
        self.path = path
        self.entries: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("version") == REQUIREMENTS_EXTRACTOR_VERSION:
                self.entries = data.get("entries", {})
        except (OSError, ValueError):
            self.entries = {}

    def key(self, page_id: str, content_hash: Optional[str]) -> str:
        payload = f"{REQUIREMENTS_EXTRACTOR_VERSION}|{page_id}|{content_hash or ''}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[ProgramIntelligence]:
        data = self.entries.get(key)
        if data is None:
            return None
        try:
            return ProgramIntelligence(**data)
        except Exception:
            return None

    def set(self, key: str, obj: ProgramIntelligence) -> None:
        self.entries[key] = obj.model_dump(mode="json")

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {"version": REQUIREMENTS_EXTRACTOR_VERSION, "entries": self.entries}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        try:
            os.replace(tmp, self.path)
        except PermissionError:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)


class RequirementsPageExtractor:
    def __init__(self, cache: Optional[PageExtractionCache] = None, use_llm: bool = False) -> None:
        self.cache = cache
        self.use_llm = use_llm
        self.last_from_cache = False

    def extract(self, page: CrawledPage, program: Dict[str, Any]) -> ProgramIntelligence:
        self.last_from_cache = False
        key = self.cache.key(page.page_id, page.content_hash) if self.cache else None
        if self.cache and key:
            cached = self.cache.get(key)
            if cached is not None:
                self.last_from_cache = True
                return cached

        source = make_source(page)
        hints = {
            "program_name": program.get("name"),
            "university": program.get("university_name"),
            "country": (program.get("location") or {}).get("country"),
            "city": (program.get("location") or {}).get("city"),
        }
        clean = make_clean_page(page)
        extractor = PageExtractor(source, country_hint=hints.get("country"))
        obj = extractor.extract(
            clean,
            hints,
            is_program_page=(page.page_type == CrawlPageType.PROGRAM_PAGE),
        )

        if self.use_llm and not page.is_pdf:
            from ..intelligence.llm import extract_with_llm, is_enabled

            if is_enabled():
                llm_obj = extract_with_llm(page.text or "", source, hints)
                if llm_obj is not None:
                    from ..intelligence.merge import Merger

                    Merger({source.id: source}).merge(obj, llm_obj)

        if self.cache and key:
            self.cache.set(key, obj)
        return obj
