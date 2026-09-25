"""End-to-end Program Intelligence pipeline for a single program (Section 72)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .classify import classify_page
from .dates import parse_date
from .discovery import Target, collect_targets, normalize_url
from .extract import PageExtractor, make_input_source
from .fetch import BudgetExceeded, Fetcher, FetchResult, utcnow
from .html_text import CleanPage, parse_html, same_registered_domain
from .llm import extract_with_llm
from .merge import Merger, finalize
from .pdf_text import extract_pdf_pages
from .schema import PageType, ProgramIntelligence, Source, SourceType


@dataclass
class PipelineConfig:
    cache_dir: str = "data/cache"
    out_dir: str = "data/intelligence"
    max_pages: int = 8
    max_pdfs: int = 3
    max_depth: int = 2
    max_requests: int = 30
    timeout: int = 25
    max_retries: int = 2
    delay: float = 1.0
    cache_ttl_seconds: int = 7 * 24 * 3600
    use_llm: bool = True  # only takes effect if INTEL_LLM_ENABLED=1
    min_link_score: float = 1.2


@dataclass
class RunStats:
    pages_fetched: int = 0
    pdfs_fetched: int = 0
    requests_made: int = 0
    discovered: int = 0
    selected: int = 0
    errors: List[str] = field(default_factory=list)


class ProgramIntelligencePipeline:
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

    # -- public --------------------------------------------------------------
    def run(self, record: Dict[str, Any]) -> Tuple[ProgramIntelligence, RunStats]:
        cfg = self.config
        hints = self._hints(record)
        stats = RunStats()

        fetcher = Fetcher(
            cache_dir=cfg.cache_dir,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
            max_requests=cfg.max_requests,
            delay=cfg.delay,
            cache_ttl_seconds=cfg.cache_ttl_seconds,
        )

        sources: Dict[str, Source] = {}
        merger = Merger(sources)

        input_source = make_input_source(hints)
        sources[input_source.id] = input_source

        base = ProgramIntelligence()
        # Seed identity from the input record.
        merger.merge(base, self._from_hints(hints))

        program_url = self._resolve_program_url(record, fetcher, hints, stats)
        if not program_url:
            base.extraction_status = "NO_PROGRAM_URL"
            base.notes.append("No official program URL could be resolved.")
            return finalize(base, utcnow()), stats

        queue: List[Tuple[int, float, str]] = [(0, 1000.0, program_url)]
        visited: set = set()
        page_count = 0
        pdf_count = 0

        while queue:
            queue.sort(key=lambda item: (-item[1], item[0]))
            depth, score, url = queue.pop(0)
            norm = normalize_url(url)
            if norm in visited:
                continue
            visited.add(norm)

            if depth > 0:
                is_pdf_url = url.lower().split("?")[0].endswith(".pdf")
                if is_pdf_url and pdf_count >= cfg.max_pdfs:
                    continue
                if not is_pdf_url and page_count >= cfg.max_pages:
                    continue

            try:
                result = fetcher.fetch(url)
            except BudgetExceeded as exc:
                stats.errors.append(str(exc))
                break

            if not result.ok:
                stats.errors.append(f"{url} -> {result.status or result.error}")
                continue

            if depth > 0:
                if result.is_pdf:
                    pdf_count += 1
                else:
                    page_count += 1

            source = self._make_source(result, hints, program_url)
            sources[source.id] = source
            if result.is_pdf:
                stats.pdfs_fetched += 1
                page = self._pdf_clean_page(result)
            else:
                stats.pages_fetched += 1
                page = parse_html(result.text, result.final_url)
                source.page_type = classify_page(result.final_url, page.title, page.text)
                source.title = page.title or source.title
                if page.last_updated:
                    source.last_updated = page.last_updated

            if page is None or not page.text:
                continue

            extractor = PageExtractor(source, country_hint=hints.get("country"))
            merger.merge(base, extractor.extract(page, hints, is_program_page=(depth == 0)))

            if cfg.use_llm and not result.is_pdf and depth < cfg.max_depth:
                llm_obj = extract_with_llm(page.text, source, hints)
                if llm_obj is not None:
                    merger.merge(base, llm_obj)

            if result.is_pdf or depth >= cfg.max_depth:
                continue

            targets = collect_targets(page, program_url, cfg.min_link_score)
            stats.discovered += len(targets)
            for target in targets:
                if normalize_url(target.url) not in visited:
                    queue.append((depth + 1, target.score, target.url))

        base.sources = list(sources.values())
        stats.requests_made = fetcher.requests_made
        return finalize(base, utcnow()), stats

    # -- hints ---------------------------------------------------------------
    def _hints(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "program_name": record.get("program_name") or record.get("name"),
            "university": record.get("university") or record.get("university_name"),
            "country": record.get("country"),
            "city": record.get("city"),
            "program_url": record.get("program_url") or record.get("url"),
            "university_domain": record.get("university_domain") or record.get("domain"),
            "degree_type": record.get("degree_type") or record.get("degree_program"),
            "qs_rank": record.get("qs_rank"),
        }

    def _from_hints(self, hints: Dict[str, Any]) -> ProgramIntelligence:
        from .schema import Fact

        obj = ProgramIntelligence()
        if hints.get("program_name"):
            obj.identity.program_name = Fact.known(
                hints["program_name"], "input", "QS program record", 0.7
            )
        if hints.get("university"):
            obj.university.name = Fact.known(
                hints["university"], "input", "QS program record", 0.7
            )
        if hints.get("country"):
            obj.location.country = Fact.known(
                hints["country"], "input", "QS program record", 0.6
            )
        if hints.get("city"):
            obj.location.city = Fact.known(
                hints["city"], "input", "QS program record", 0.6
            )
        if hints.get("degree_type"):
            obj.identity.degree_type = Fact.known(
                hints["degree_type"], "input", "QS program record", 0.6
            )
        if hints.get("university_domain"):
            obj.university.official_domain = Fact.known(
                hints["university_domain"], "input", "QS program record", 0.6
            )
        return obj

    # -- url resolution ------------------------------------------------------
    def _resolve_program_url(
        self,
        record: Dict[str, Any],
        fetcher: Fetcher,
        hints: Dict[str, Any],
        stats: RunStats,
    ) -> Optional[str]:
        explicit = hints.get("program_url")
        if explicit and str(explicit).startswith("http"):
            return explicit

        domain = hints.get("university_domain")
        if not domain:
            return None
        if not str(domain).startswith("http"):
            domain = "https://" + str(domain).lstrip("/")

        try:
            landing = fetcher.fetch(domain)
        except BudgetExceeded:
            return None
        if not landing.ok:
            stats.errors.append(f"landing {domain} -> {landing.status or landing.error}")
            return None

        page = parse_html(landing.text, landing.final_url)
        name_tokens = [
            t for t in _tokenize(hints.get("program_name") or "") if len(t) > 2
        ]
        best: Optional[Target] = None
        best_score = 0.0
        for target in collect_targets(page, domain, min_score=0.0):
            if target.is_pdf:
                continue
            text = (target.anchor_text or "").lower()
            score = sum(1 for t in name_tokens if t in text)
            if not text:
                continue
            if score > best_score:
                best_score = score
                best = target
        if best and best_score >= max(2, len(name_tokens) // 2):
            return best.url
        return None

    # -- source/page builders ------------------------------------------------
    def _make_source(self, result: FetchResult, hints: Dict[str, Any], reference_url: str) -> Source:
        sid = "src_" + hashlib.sha1(result.final_url.encode("utf-8")).hexdigest()[:10]
        source_type = (
            SourceType.OFFICIAL_UNIVERSITY
            if same_registered_domain(result.final_url, reference_url)
            else SourceType.OFFICIAL_UNIVERSITY
        )
        return Source(
            id=sid,
            url=result.final_url,
            title=None,
            source_type=source_type,
            page_type=PageType.OTHER,
            retrieved_at=result.fetched_at,
            content_hash=result.content_hash,
            tier=1,
            http_status=result.status,
            is_pdf=result.is_pdf,
        )

    def _pdf_clean_page(self, result: FetchResult) -> Optional[CleanPage]:
        try:
            pages = extract_pdf_pages(result.binary or b"")
        except Exception as exc:  # a malformed PDF must not fail the program
            self._last_pdf_error = f"{type(exc).__name__}: {exc}"
            return None
        if not pages:
            return None
        text = "\n\n".join(page_text for _num, page_text in pages if page_text).strip()
        if not text:
            return None
        return CleanPage(url=result.final_url, title=result.final_url.rsplit("/", 1)[-1], text=text)

    # -- diagnostics ---------------------------------------------------------
    def run_and_save(self, record: Dict[str, Any]) -> Tuple[ProgramIntelligence, RunStats, str]:
        from .store import save_intelligence

        obj, stats = self.run(record)
        path = save_intelligence(obj, self.config.out_dir)
        return obj, stats, path


def _tokenize(value: str) -> List[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in value).split() if t]
