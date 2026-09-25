"""Targeted official-site crawler (Sections 11, 23).

Starting from a university domain, the crawler prioritizes pages likely to hold
admission requirements and never crawls the whole site. Every failure is
recorded on the page/job record instead of aborting the crawl.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from bs4 import BeautifulSoup

from ..intelligence.classify import link_score
from ..intelligence.discovery import collect_targets, normalize_url
from ..intelligence.fetch import BudgetExceeded, FetchResult, utcnow
from ..intelligence.html_text import parse_html
from ..intelligence.pdf_text import extract_pdf_pages
from ..normalize.text import normalize_name
from .classify import classify_page_type, source_tier_for
from .render import needs_render
from .models import (
    CrawlJobRecord,
    CrawledPage,
    CrawlStatus,
    CrawlTarget,
    PageLink,
    PageType,
)
from .versions import CRAWLER_VERSION, PARSER_VERSION


@dataclass
class CrawlLimits:
    max_pages: int = 8
    max_pdfs: int = 3
    max_depth: int = 2
    max_requests: int = 25
    min_link_score: float = 1.2
    max_links_per_page: int = 40


@dataclass
class CrawlResult:
    pages: List[CrawledPage] = field(default_factory=list)
    job: CrawlJobRecord = field(default_factory=lambda: CrawlJobRecord(program_id="", university_id=""))


def _page_id(url: str) -> str:
    """Pages are stored once per URL (shared across programs that reference them)."""
    return "page_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _hash(html: str) -> str:
    return hashlib.sha256((html or "").encode("utf-8", "ignore")).hexdigest()


def _headings(html: str, limit: int = 30) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    out: List[str] = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if 2 < len(text) < 200 and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


class OfficialSiteCrawler:
    def __init__(self, fetcher, limits: Optional[CrawlLimits] = None, renderer=None) -> None:
        self.fetcher = fetcher
        self.limits = limits or CrawlLimits()
        self.renderer = renderer

    def crawl(self, target: CrawlTarget, start_url: str) -> CrawlResult:
        limits = self.limits
        job = CrawlJobRecord(
            program_id=target.program_id,
            university_id=target.university_id,
            start_url=start_url,
            started_at=utcnow(),
            parser_version=PARSER_VERSION,
            crawler_version=CRAWLER_VERSION,
        )
        result = CrawlResult(job=job)

        reference_url = start_url
        program_tokens = self._program_tokens(target)
        blocked = False
        timed_out = False
        queue: List[Tuple[int, float, str]] = [(0, 1000.0, start_url)]
        visited: Set[str] = set()
        page_count = 0
        pdf_count = 0
        budget_exceeded = False

        while queue:
            queue.sort(key=lambda item: (-item[1], item[0]))
            depth, _score, url = queue.pop(0)
            norm = normalize_url(url)
            if norm in visited:
                continue
            visited.add(norm)

            is_pdf_url = url.lower().split("?")[0].endswith(".pdf")
            if is_pdf_url and pdf_count >= limits.max_pdfs:
                continue
            if not is_pdf_url and depth > 0 and page_count >= limits.max_pages:
                continue

            fetched: Optional[FetchResult] = None
            fetch_error: Optional[str] = None
            try:
                fetched = self.fetcher.fetch(url)
            except BudgetExceeded:
                budget_exceeded = True
                break
            except Exception as exc:  # never let one page kill the crawl
                fetch_error = f"{type(exc).__name__}: {exc}"
                if "Timeout" in type(exc).__name__:
                    timed_out = True

            if fetched is not None and not fetched.ok:
                if fetched.error == "robots_disallowed" or fetched.status in (401, 403, 429):
                    blocked = True
                if fetched.error and "Timeout" in fetched.error:
                    timed_out = True

            # PDF fast path (never rendered).
            if fetched is not None and fetched.ok and fetched.is_pdf:
                pdf_count += 1
                result.pages.append(self._pdf_page(target, fetched, depth))
                continue

            html: Optional[str] = None
            rendered = False
            render_attempted = False
            robots_disallowed = fetched is not None and fetched.error == "robots_disallowed"
            if fetched is not None and fetched.ok and not fetched.is_pdf:
                html = fetched.text

            # Rendering fallback: blocked statuses, JS interstitials, thin bodies,
            # or a request that failed at the HTTP layer (a browser can succeed
            # where requests cannot). Robots-disallowed URLs are never rendered.
            if self.renderer is not None and not robots_disallowed and not is_pdf_url:
                want_render = (
                    fetch_error is not None
                    or (fetched is not None and fetched.status in (401, 403, 429, 503))
                    or (fetched is not None and fetched.ok and not fetched.is_pdf and needs_render(fetched.status, fetched.text))
                )
                if want_render:
                    render_attempted = True
                    rendered_html = self.renderer.render((fetched.final_url if fetched else url) or url)
                    if rendered_html:
                        html = rendered_html
                        rendered = True

            # Rendering could not clear an interstitial -> record as blocked.
            if (
                render_attempted
                and not rendered
                and fetched is not None
                and fetched.ok
                and needs_render(fetched.status, fetched.text)
            ):
                blocked = True
                result.pages.append(self._error_page(target, url, depth, "blocked_interstitial", fetched))
                continue

            if html is None:
                error = fetch_error or (fetched.error if fetched is not None else "request failed")
                result.pages.append(self._error_page(target, url, depth, error, fetched))
                continue

            page_count += 1
            final_url = (fetched.final_url if fetched else url) or url
            clean = parse_html(html, final_url)
            page_type = classify_page_type(final_url, clean.title, clean.text)
            content_hash = _hash(html) if rendered or fetched is None else fetched.content_hash
            crawled = CrawledPage(
                page_id=_page_id(final_url),
                program_id=target.program_id,
                university_id=target.university_id,
                program_ids=[target.program_id],
                url=final_url,
                final_url=final_url,
                title=clean.title or None,
                page_type=page_type,
                source_tier=source_tier_for(page_type),
                http_status=200 if rendered else (fetched.status if fetched else None),
                content_hash=content_hash,
                is_pdf=False,
                depth=depth,
                text=clean.text[:200_000],
                headings=_headings(html),
                tables=len(clean.tables),
                pdf_links=clean.pdf_links[:20],
                links=self._relevant_links(clean, final_url),
                last_updated=clean.last_updated,
                retrieved_at=fetched.fetched_at if fetched else utcnow(),
                crawl_status=CrawlStatus.SUCCESS,
                from_cache=(fetched.from_cache if fetched else False) and not rendered,
                rendered=rendered,
            )
            result.pages.append(crawled)

            if depth >= limits.max_depth:
                continue
            # Collect all same-site links, then rank by keyword relevance plus a
            # bonus for matching the program name / QS slug (the program page
            # itself may not contain any of the admission/tuition keywords).
            for candidate in collect_targets(clean, reference_url, 0.0):
                if normalize_url(candidate.url) in visited:
                    continue
                bonus = self._program_bonus(candidate.url, candidate.anchor_text, program_tokens)
                effective = candidate.score + bonus
                if effective < limits.min_link_score:
                    continue
                queue.append((depth + 1, effective, candidate.url))

        job.pages_crawled = page_count
        job.pdfs_crawled = pdf_count
        job.requests_made = getattr(self.fetcher, "requests_made", 0)
        job.finished_at = utcnow()
        if budget_exceeded:
            job.status = CrawlStatus.FAILED
            job.reason = "BUDGET_EXCEEDED"
        elif blocked and not any(p.crawl_status == CrawlStatus.SUCCESS for p in result.pages):
            job.status = CrawlStatus.FAILED
            job.reason = "BLOCKED"
        elif timed_out and not any(p.crawl_status == CrawlStatus.SUCCESS for p in result.pages):
            job.status = CrawlStatus.FAILED
            job.reason = "TIMEOUT"
        elif not result.pages:
            job.status = CrawlStatus.FAILED
            job.reason = "NO_PAGES"
        elif any(p.crawl_status == CrawlStatus.SUCCESS for p in result.pages):
            job.status = CrawlStatus.SUCCESS
        else:
            job.status = CrawlStatus.FAILED
            job.reason = "ALL_PAGES_FAILED"
        return result

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _program_tokens(target: CrawlTarget) -> List[str]:
        tokens = [t for t in normalize_name(target.program_name or "").split() if len(t) > 2]
        # The QS program slug is a strong signal for the official program page.
        if target.qs_program_url:
            from urllib.parse import urlparse

            slug = urlparse(target.qs_program_url).path.rstrip("/").split("/")[-1]
            for token in slug.split("-"):
                if len(token) > 3 and not token.isdigit() and token not in tokens:
                    tokens.append(token)
        return tokens

    @staticmethod
    def _program_bonus(url: str, anchor_text: str, program_tokens: List[str]) -> float:
        if not program_tokens:
            return 0.0
        haystack = normalize_name(f"{url} {anchor_text}")
        overlap = sum(1 for token in program_tokens if token in haystack)
        return min(overlap, 4) * 2.5

    def _relevant_links(self, clean, base_url: str) -> List[PageLink]:
        links: List[PageLink] = []
        seen = set()
        for anchor in clean.anchors:
            if not anchor.href or anchor.href in seen:
                continue
            seen.add(anchor.href)
            score = link_score(anchor.text, anchor.href)
            if score <= 0:
                continue
            links.append(
                PageLink(
                    url=anchor.href,
                    text=anchor.text[:160],
                    score=round(score, 2),
                    page_type=classify_page_type(anchor.href, anchor.text, anchor.text),
                )
            )
        links.sort(key=lambda l: l.score, reverse=True)
        return links[: self.limits.max_links_per_page]

    def _error_page(
        self, target: CrawlTarget, url: str, depth: int, error: Optional[str], fetched: Optional[FetchResult] = None
    ) -> CrawledPage:
        return CrawledPage(
            page_id=_page_id(url),
            program_id=target.program_id,
            university_id=target.university_id,
            program_ids=[target.program_id],
            url=url,
            final_url=fetched.final_url if fetched else url,
            page_type=PageType.UNKNOWN,
            http_status=fetched.status if fetched else None,
            depth=depth,
            crawl_status=CrawlStatus.FAILED,
            error=error or "request failed",
            retrieved_at=fetched.fetched_at if fetched else utcnow(),
        )

    def _pdf_page(self, target: CrawlTarget, fetched: FetchResult, depth: int) -> CrawledPage:
        text = ""
        try:
            pages = extract_pdf_pages(fetched.binary or b"")
            text = "\n\n".join(page_text for _num, page_text in pages if page_text)
        except Exception as exc:
            return CrawledPage(
                page_id=_page_id(fetched.final_url),
                program_id=target.program_id,
                university_id=target.university_id,
                program_ids=[target.program_id],
                url=fetched.final_url,
                final_url=fetched.final_url,
                page_type=PageType.UNKNOWN,
                source_tier=source_tier_for(PageType.UNKNOWN),
                http_status=fetched.status,
                content_hash=fetched.content_hash,
                is_pdf=True,
                depth=depth,
                crawl_status=CrawlStatus.FAILED,
                error=f"PDF_PARSE_FAILED: {type(exc).__name__}",
                retrieved_at=fetched.fetched_at,
            )
        page_type = classify_page_type(fetched.final_url, "", text)
        return CrawledPage(
            page_id=_page_id(fetched.final_url),
            program_id=target.program_id,
            university_id=target.university_id,
            program_ids=[target.program_id],
            url=fetched.final_url,
            final_url=fetched.final_url,
            title=fetched.final_url.rsplit("/", 1)[-1],
            page_type=page_type,
            source_tier=source_tier_for(page_type),
            http_status=fetched.status,
            content_hash=fetched.content_hash,
            is_pdf=True,
            depth=depth,
            text=text[:200_000],
            crawl_status=CrawlStatus.SUCCESS,
            from_cache=fetched.from_cache,
            retrieved_at=fetched.fetched_at,
        )
