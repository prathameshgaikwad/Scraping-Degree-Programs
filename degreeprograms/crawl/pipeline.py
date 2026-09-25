"""Phase 5 pipeline: crawl official university sites for candidate programs.

Reads classifications + normalized programs/universities, resolves official
domains, and crawls a small targeted set of pages per program.

Reliability features:
* robots.txt + per-domain delay (via ``PoliteFetcher``)
* blocked-domain circuit breaker (stops wasting budget on 403/429 hosts)
* bounded, resumable runs (``max_programs`` / ``max_runtime_seconds``)
* optional JS rendering (Playwright) when available and enabled
* incremental, crash-safe state
"""

from __future__ import annotations

import os
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import degreeprograms.normalize as _normalize_pkg
from ..intelligence.fetch import Fetcher
from ..normalize.io import (
    ensure_dir,
    load_alias_registry,
    read_jsonl,
    utcnow,
    write_json,
    write_jsonl,
)
from .crawler import CrawlLimits, OfficialSiteCrawler
from .domains import DomainResolver
from .models import (
    CrawlJobRecord,
    CrawlManifest,
    CrawlStatus,
    CrawlTarget,
    PageType,
)
from .politeness import PoliteFetcher, Politeness
from .render import make_renderer
from .state import CrawlState
from .versions import CRAWLER_VERSION, CRAWL_SCHEMA_VERSION, PARSER_VERSION

_DEFAULT_ALIASES = os.path.join(
    os.path.dirname(_normalize_pkg.__file__), "data", "university_aliases.json"
)


@dataclass
class CrawlConfig:
    classifications_path: str = "data/enriched/program_classifications/classifications.jsonl"
    programs_path: str = "data/normalized/programs.jsonl"
    universities_path: str = "data/normalized/universities.jsonl"
    out_dir: str = "data/enriched/university_pages"
    cache_dir: str = "data/cache"
    alias_registry_path: str = _DEFAULT_ALIASES
    relevance: List[str] = field(default_factory=lambda: ["HIGH", "MEDIUM"])
    target_field_codes: List[str] = field(default_factory=list)
    resolve_domains: bool = False
    # crawl limits
    max_pages: int = 8
    max_pdfs: int = 3
    max_depth: int = 2
    max_requests: int = 25
    timeout: int = 25
    max_retries: int = 2
    delay: float = 1.0
    # politeness
    obey_robots: bool = True
    default_delay: float = 0.5
    # bounded runs
    max_programs: int = 0          # 0 = unlimited
    max_runtime_seconds: int = 0   # 0 = unlimited
    blocked_domain_threshold: int = 3
    # rendering (optional, requires Playwright)
    render: bool = False
    render_timeout_ms: int = 20000
    # misc
    force: bool = False
    limit: int = 0
    store_text: bool = True


class OfficialSiteCrawlPipeline:
    def __init__(
        self,
        config: Optional[CrawlConfig] = None,
        fetcher=None,
        resolver: Optional[DomainResolver] = None,
        renderer=None,
    ) -> None:
        self.config = config or CrawlConfig()
        cfg = self.config
        base_fetcher = fetcher or Fetcher(
            cache_dir=cfg.cache_dir,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
            max_requests=cfg.max_requests,
            delay=cfg.delay,
        )
        # Wrap in politeness only for a real Fetcher (keeps injected test stubs fast).
        if hasattr(base_fetcher, "has_fresh_cache") and (cfg.obey_robots or cfg.default_delay > 0):
            self.fetcher = PoliteFetcher(
                base_fetcher,
                Politeness(
                    base_fetcher,
                    user_agent="*",
                    obey_robots=cfg.obey_robots,
                    default_delay=cfg.default_delay,
                ),
            )
        else:
            self.fetcher = base_fetcher
        self.renderer = renderer if renderer is not None else make_renderer(cfg.render, cfg.render_timeout_ms)
        self._resolver = resolver

    def run(self) -> CrawlManifest:
        cfg = self.config
        ensure_dir(cfg.out_dir)
        pages_path = os.path.join(cfg.out_dir, "pages.jsonl")
        state_path = os.path.join(cfg.out_dir, "state.json")
        manifest_path = os.path.join(cfg.out_dir, "manifest.json")

        pages: Dict[str, dict] = {}
        if os.path.exists(pages_path):
            for row in read_jsonl(pages_path):
                pages[row["page_id"]] = row

        state = CrawlState(state_path)
        programs = {p["program_id"]: p for p in read_jsonl(cfg.programs_path)}
        universities = {u["university_id"]: u for u in read_jsonl(cfg.universities_path)}
        classifications = read_jsonl(cfg.classifications_path)

        targets = self._filtered(self._build_targets(classifications, programs, universities), classifications)
        if cfg.limit:
            targets = targets[: cfg.limit]

        registry = load_alias_registry(cfg.alias_registry_path).get("domains", {})
        resolver = self._resolver or DomainResolver(
            registry, fetcher=self.fetcher, search_enabled=cfg.resolve_domains
        )
        crawler = OfficialSiteCrawler(
            self.fetcher,
            CrawlLimits(
                max_pages=cfg.max_pages,
                max_pdfs=cfg.max_pdfs,
                max_depth=cfg.max_depth,
                max_requests=cfg.max_requests,
            ),
            renderer=self.renderer,
        )

        jobs: List[CrawlJobRecord] = []
        resumed_skipped = 0
        domains_resolved = 0
        domains_missing = 0
        processed = 0
        stopped_early = False
        remaining = 0
        blocked_domains: Set[str] = set()
        blocked_counts: Dict[str, int] = {}
        started_at = time.time()

        try:
            for index, target in enumerate(targets):
                if cfg.max_runtime_seconds and (time.time() - started_at) > cfg.max_runtime_seconds:
                    stopped_early = True
                    remaining = len(targets) - index
                    break
                if cfg.max_programs and processed >= cfg.max_programs:
                    stopped_early = True
                    remaining = len(targets) - index
                    break
                if not cfg.force and state.is_done(target.program_id):
                    resumed_skipped += 1
                    continue

                university = universities.get(target.university_id, {})
                candidate_names = [target.university_name or university.get("canonical_name") or ""]
                for alias in university.get("aliases", []) or []:
                    candidate_names.append(alias.get("alias", ""))
                domain_result = resolver.resolve(candidate_names, university.get("official_domain"))

                if not domain_result.domain:
                    domains_missing += 1
                    self._finish(state, jobs, target, CrawlStatus.SKIPPED, "NO_DOMAIN")
                    continue

                if domain_result.domain in blocked_domains:
                    self._finish(state, jobs, target, CrawlStatus.SKIPPED, "DOMAIN_BLOCKED")
                    continue

                domains_resolved += 1
                processed += 1
                target.official_domain = domain_result.domain
                if hasattr(self.fetcher, "requests_made"):
                    self.fetcher.requests_made = 0  # per-program budget
                start_url = self._start_url(domain_result.domain)
                state.mark_started(target.program_id)

                crawl_result = crawler.crawl(target, start_url)
                job = crawl_result.job
                job.reason = job.reason or domain_result.method
                jobs.append(job)

                for page in crawl_result.pages:
                    if not cfg.store_text:
                        page.text = ""
                    existing = pages.get(page.page_id)
                    if existing is not None:
                        ids = set(existing.get("program_ids") or []) | set(page.program_ids or [page.program_id])
                        fresh = page.model_dump(mode="json")
                        fresh["program_ids"] = sorted(i for i in ids if i)
                        pages[page.page_id] = fresh
                    else:
                        pages[page.page_id] = page.model_dump(mode="json")
                    state.update_page(page.url, page.content_hash, page.crawl_status.value)
                state.mark_finished(job)

                if job.status == CrawlStatus.FAILED and job.reason == "BLOCKED":
                    blocked_counts[domain_result.domain] = blocked_counts.get(domain_result.domain, 0) + 1
                    if blocked_counts[domain_result.domain] >= cfg.blocked_domain_threshold:
                        blocked_domains.add(domain_result.domain)

                # Persist incrementally so a crash can resume.
                write_jsonl(pages_path, list(pages.values()))
                state.save()
        finally:
            if self.renderer is not None and hasattr(self.renderer, "close"):
                self.renderer.close()

        write_jsonl(pages_path, list(pages.values()))
        state.save()
        manifest = self._manifest(
            cfg, targets, jobs, pages, resumed_skipped, domains_resolved, domains_missing,
            processed, stopped_early, remaining, sorted(blocked_domains),
        )
        write_json(manifest_path, manifest)
        return manifest

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _finish(state: CrawlState, jobs: List[CrawlJobRecord], target: CrawlTarget, status: CrawlStatus, reason: str) -> None:
        job = CrawlJobRecord(
            program_id=target.program_id,
            university_id=target.university_id,
            status=status,
            reason=reason,
            parser_version=PARSER_VERSION,
            started_at=utcnow(),
            finished_at=utcnow(),
            crawler_version=CRAWLER_VERSION,
        )
        jobs.append(job)
        state.mark_finished(job)

    def _start_url(self, domain: str) -> str:
        """Prefer the www host (many university sites 403/timeout on the apex)."""
        if domain.startswith("www."):
            return f"https://{domain}/"
        for candidate in (f"https://www.{domain}/", f"https://{domain}/"):
            try:
                result = self.fetcher.fetch(candidate)
            except Exception:
                continue
            if result.ok:
                return candidate
        return f"https://{domain}/"

    @staticmethod
    def _build_targets(classifications, programs, universities) -> List[CrawlTarget]:
        targets: List[CrawlTarget] = []
        for classification in classifications:
            relevance = classification.get("relevance")
            program = programs.get(classification.get("program_id"))
            if program is None:
                continue
            university = universities.get(program.get("university_id"), {})
            targets.append(
                CrawlTarget(
                    program_id=program["program_id"],
                    university_id=program.get("university_id", ""),
                    program_name=program.get("name", ""),
                    university_name=university.get("canonical_name"),
                    relevance=relevance,
                    official_domain=university.get("official_domain"),
                    qs_program_url=(program.get("source") or {}).get("program_url"),
                )
            )
        return targets

    def _filtered(self, targets: List[CrawlTarget], classifications) -> List[CrawlTarget]:
        cfg = self.config
        by_id = {c["program_id"]: c for c in classifications}
        allowed = set(cfg.target_field_codes)
        out: List[CrawlTarget] = []
        for target in targets:
            classification = by_id.get(target.program_id, {})
            if classification.get("relevance") not in cfg.relevance:
                continue
            if allowed:
                fields = {classification.get("primary_field")} | set(classification.get("secondary_fields") or [])
                if not (fields & allowed):
                    continue
            out.append(target)
        return out

    def _manifest(
        self,
        cfg: CrawlConfig,
        targets: List[CrawlTarget],
        jobs: List[CrawlJobRecord],
        pages: Dict[str, dict],
        resumed_skipped: int,
        domains_resolved: int,
        domains_missing: int,
        processed: int,
        stopped_early: bool,
        remaining: int,
        blocked_domains: List[str],
    ) -> CrawlManifest:
        by_type = Counter(p.get("page_type", PageType.UNKNOWN.value) for p in pages.values())
        pdfs = sum(1 for p in pages.values() if p.get("is_pdf"))
        return CrawlManifest(
            classifications_path=cfg.classifications_path,
            programs_path=cfg.programs_path,
            universities_path=cfg.universities_path,
            crawler_version=CRAWLER_VERSION,
            parser_version=PARSER_VERSION,
            schema_version=CRAWL_SCHEMA_VERSION,
            generated_at=utcnow(),
            candidates=len(targets),
            jobs_success=sum(1 for j in jobs if j.status == CrawlStatus.SUCCESS),
            jobs_failed=sum(1 for j in jobs if j.status == CrawlStatus.FAILED),
            jobs_skipped=sum(1 for j in jobs if j.status == CrawlStatus.SKIPPED),
            jobs_resumed_skipped=resumed_skipped,
            jobs_blocked=sum(1 for j in jobs if j.reason == "BLOCKED"),
            jobs_timed_out=sum(1 for j in jobs if j.reason == "TIMEOUT"),
            blocked_domains=blocked_domains,
            programs_processed=processed,
            stopped_early=stopped_early,
            remaining=remaining,
            pages=len(pages),
            pdfs=pdfs,
            pages_by_type=dict(by_type.most_common()),
            domains_resolved=domains_resolved,
            domains_missing=domains_missing,
        )
