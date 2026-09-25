"""Official university domain resolution (Section 11).

Order of preference:
1. an ``official_domain`` already present in the normalized university record
2. the curated alias/domain registry (Phase 2)
3. optional web search (DuckDuckGo HTML), used only when enabled

Search is off by default because it is network-heavy and fragile; universities
without a resolved domain are recorded as ``SKIPPED``/``NO_DOMAIN`` rather than
guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlparse

from ..intelligence.html_text import host_of, parse_html
from ..normalize.text import normalize_name

_AGGREGATOR_HOSTS = (
    "topuniversities.com", "wikipedia.org", "facebook.com", "linkedin.com",
    "youtube.com", "instagram.com", "twitter.com", "x.com", "mastersportal.com",
    "findamasters.com", "study.eu", "studyportals.com", "qs.com",
    "timeshighereducation.com", "usnews.com", "niche.com", "google.com",
    "bing.com", "duckduckgo.com", "yandex.com", "reddit.com", "glassdoor.com",
)

_ACADEMIC_SUFFIXES = (
    ".edu", ".ac.uk", ".edu.au", ".ac.nz", ".edu.sg", ".ac.jp", ".edu.hk",
    ".edu.my", ".ac.in", ".edu.in", ".ac.za", ".edu.cn", ".ac.kr", ".edu.tw",
    ".edu.pk", ".edu.tr", ".edu.br", ".ac.at", ".ac.be", ".uni-", ".university",
)


@dataclass
class DomainResult:
    domain: Optional[str] = None
    method: str = "UNRESOLVED"
    confidence: float = 0.0


def _clean_domain(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip().lower()
    if "://" in value:
        value = urlparse(value).netloc
    value = value.split("/")[0].split("?")[0].strip()
    return value or None


class DomainResolver:
    def __init__(
        self,
        registry_domains: Optional[Dict[str, str]] = None,
        fetcher=None,
        search_enabled: bool = False,
    ) -> None:
        self.registry = {normalize_name(k): _clean_domain(v) for k, v in (registry_domains or {}).items()}
        self.fetcher = fetcher
        self.search_enabled = search_enabled
        self._search_cache: Dict[str, DomainResult] = {}

    def resolve(self, candidate_names: List[str], existing_domain: Optional[str] = None) -> DomainResult:
        existing = _clean_domain(existing_domain)
        if existing:
            return DomainResult(existing, "EXISTING", 0.95)

        for name in candidate_names:
            domain = self.registry.get(normalize_name(name))
            if domain:
                return DomainResult(domain, "REGISTRY", 0.9)

        if self.search_enabled and self.fetcher is not None:
            return self._search(candidate_names)

        return DomainResult(None, "UNRESOLVED", 0.0)

    # -- optional web search -------------------------------------------------
    def _search(self, candidate_names: List[str]) -> DomainResult:
        primary = next((n for n in candidate_names if n), "")
        if not primary:
            return DomainResult(None, "UNRESOLVED", 0.0)
        if primary in self._search_cache:
            return self._search_cache[primary]

        query = quote_plus(f"{primary} official site")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        try:
            result = self.fetcher.fetch(url)
        except Exception:
            result = None
        domain = None
        if result is not None and result.ok and result.text:
            page = parse_html(result.text, result.final_url)
            domain = self._best_host(page.anchors, primary)
        outcome = (
            DomainResult(domain, "SEARCH", 0.6) if domain else DomainResult(None, "UNRESOLVED", 0.0)
        )
        self._search_cache[primary] = outcome
        return outcome

    def _best_host(self, anchors, university_name: str) -> Optional[str]:
        name_tokens = [t for t in normalize_name(university_name).split() if len(t) > 2]
        best_host, best_score = None, 0
        seen = set()
        for anchor in anchors:
            host = host_of(anchor.href)
            if not host or host in seen:
                continue
            seen.add(host)
            if any(bad in host for bad in _AGGREGATOR_HOSTS):
                continue
            score = sum(1 for token in name_tokens if token in host)
            if any(host.endswith(suffix) for suffix in _ACADEMIC_SUFFIXES):
                score += 2
            if score > best_score:
                best_score, best_host = score, host
        if best_host and best_score >= 2:
            return best_host
        return None
