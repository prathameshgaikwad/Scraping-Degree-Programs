"""Robots.txt + per-domain politeness for the crawler.

A thin wrapper around the HTTP fetcher that:
* honors robots.txt (disallow + crawl-delay), configurable
* enforces a minimum per-domain delay
* fails closed on disallowed URLs with a synthetic 403 result (recorded, not thrown)

Robots files and page bodies are served from the shared HTTP cache, so resume
runs do not re-download.
"""

from __future__ import annotations

import time
from typing import Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from ..intelligence.fetch import FetchResult, utcnow
from ..intelligence.html_text import host_of


class Politeness:
    def __init__(
        self,
        fetcher,
        user_agent: str = "*",
        obey_robots: bool = True,
        default_delay: float = 0.5,
    ) -> None:
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.obey_robots = obey_robots
        self.default_delay = default_delay
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self._last_request: Dict[str, float] = {}

    # -- robots --------------------------------------------------------------
    def _robots_for(self, url: str) -> Optional[RobotFileParser]:
        host = host_of(url)
        if host in self._robots:
            return self._robots[host]
        parser: Optional[RobotFileParser] = None
        try:
            scheme = urlparse(url).scheme or "https"
            result = self.fetcher.fetch(f"{scheme}://{host}/robots.txt")
            if result.ok and result.text:
                parser = RobotFileParser()
                parser.parse(result.text.splitlines())
        except Exception:
            parser = None
        self._robots[host] = parser
        return parser

    def allows(self, url: str) -> bool:
        if not self.obey_robots:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True  # no/!ok robots.txt -> allow
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def delay_for(self, url: str) -> float:
        if not self.obey_robots:
            return self.default_delay
        parser = self._robots_for(url)
        if parser is not None:
            try:
                crawl_delay = parser.crawl_delay(self.user_agent)
                if crawl_delay:
                    return float(crawl_delay)
            except Exception:
                pass
        return self.default_delay

    def wait(self, url: str) -> None:
        host = host_of(url)
        delay = self.delay_for(url)
        if delay <= 0:
            return
        elapsed = time.time() - self._last_request.get(host, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request[host] = time.time()


class PoliteFetcher:
    """Drop-in wrapper adding robots + per-domain delay around a Fetcher."""

    def __init__(self, fetcher, politeness: Optional[Politeness] = None, **kwargs) -> None:
        self.fetcher = fetcher
        self.politeness = politeness or Politeness(fetcher, **kwargs)

    @property
    def requests_made(self) -> int:
        return getattr(self.fetcher, "requests_made", 0)

    @requests_made.setter
    def requests_made(self, value: int) -> None:
        if hasattr(self.fetcher, "requests_made"):
            self.fetcher.requests_made = value

    def fetch(self, url: str, force: bool = False) -> FetchResult:
        # Serve cache hits without robots/delay (no network contact).
        cache_check = getattr(self.fetcher, "has_fresh_cache", None)
        if not force and cache_check and cache_check(url):
            return self.fetcher.fetch(url, force=force)

        if not self.politeness.allows(url):
            return FetchResult(
                url=url, final_url=url, status=403, error="robots_disallowed",
                fetched_at=utcnow(),
            )
        self.politeness.wait(url)
        return self.fetcher.fetch(url, force=force)
