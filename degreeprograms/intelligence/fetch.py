"""HTTP fetching with on-disk caching, retries, timeouts and a request budget.

The cache is keyed by URL. Both HTML text and raw binary (PDF) payloads are
cached so re-running an extraction never re-downloads unchanged pages.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

import requests


class BudgetExceeded(RuntimeError):
    """Raised when the per-program request budget is exhausted."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: Optional[int] = None
    content_type: str = ""
    text: str = ""
    binary: Optional[bytes] = None
    headers: Dict[str, str] = field(default_factory=dict)
    fetched_at: Optional[str] = None
    from_cache: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 400 and self.error is None

    @property
    def is_pdf(self) -> bool:
        return "pdf" in (self.content_type or "").lower() or self.final_url.lower().endswith(".pdf")

    @property
    def content_hash(self) -> str:
        payload = self.binary if self.binary else (self.text or "").encode("utf-8", "ignore")
        return hashlib.sha256(payload).hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_response(resp: requests.Response, content_type: str) -> str:
    """Decode a response body without trusting a missing/incorrect charset.

    requests defaults to ISO-8859-1 when no charset is declared, which mangles
    UTF-8 pages. Prefer an explicitly declared charset, then UTF-8.
    """
    raw = resp.content
    if "charset=" in (content_type or "").lower():
        try:
            return raw.decode(resp.encoding or "utf-8", errors="replace")
        except (LookupError, TypeError):
            pass
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


class Fetcher:
    def __init__(
        self,
        cache_dir: str,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        ),
        timeout: int = 25,
        max_retries: int = 2,
        max_requests: int = 40,
        delay: float = 1.0,
        cache_ttl_seconds: int = 7 * 24 * 3600,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_requests = max_requests
        self.delay = delay
        self.cache_ttl_seconds = cache_ttl_seconds
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.requests_made = 0
        self._last_request_time = 0.0

    # -- cache ---------------------------------------------------------------
    def _cache_paths(self, url: str):
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return (
            os.path.join(self.cache_dir, key + ".json"),
            os.path.join(self.cache_dir, key + ".bin"),
        )

    def _load_cache(self, url: str) -> Optional[FetchResult]:
        meta_path, bin_path = self._cache_paths(url)
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            return None
        if self.cache_ttl_seconds and meta.get("cached_epoch"):
            age = time.time() - float(meta["cached_epoch"])
            if age > self.cache_ttl_seconds:
                return None
        binary = None
        if meta.get("has_binary") and os.path.exists(bin_path):
            with open(bin_path, "rb") as fh:
                binary = fh.read()
        return FetchResult(
            url=url,
            final_url=meta.get("final_url", url),
            status=meta.get("status"),
            content_type=meta.get("content_type", ""),
            text=meta.get("text", ""),
            binary=binary,
            headers=meta.get("headers", {}),
            fetched_at=meta.get("fetched_at"),
            from_cache=True,
            error=meta.get("error"),
        )

    def _store_cache(self, result: FetchResult) -> None:
        meta_path, bin_path = self._cache_paths(result.url)
        meta = {
            "url": result.url,
            "final_url": result.final_url,
            "status": result.status,
            "content_type": result.content_type,
            "text": result.text,
            "headers": result.headers,
            "fetched_at": result.fetched_at,
            "error": result.error,
            "has_binary": result.binary is not None,
            "cached_epoch": time.time(),
            "content_hash": result.content_hash,
        }
        try:
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, ensure_ascii=False)
            if result.binary is not None:
                with open(bin_path, "wb") as fh:
                    fh.write(result.binary)
        except OSError:
            pass

    # -- fetch ---------------------------------------------------------------
    def has_fresh_cache(self, url: str) -> bool:
        return self._load_cache(url) is not None

    def fetch(self, url: str, force: bool = False) -> FetchResult:
        if not force:
            cached = self._load_cache(url)
            if cached is not None:
                return cached

        if self.requests_made >= self.max_requests:
            raise BudgetExceeded(
                f"Request budget of {self.max_requests} exceeded for this program"
            )

        last_error: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            self._respect_delay()
            self.requests_made += 1
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                content_type = resp.headers.get("Content-Type", "")
                is_pdf = "pdf" in content_type.lower() or resp.url.lower().endswith(".pdf")
                result = FetchResult(
                    url=url,
                    final_url=resp.url,
                    status=resp.status_code,
                    content_type=content_type,
                    headers={k: v for k, v in resp.headers.items()},
                    fetched_at=utcnow(),
                )
                if is_pdf:
                    result.binary = resp.content
                else:
                    result.text = _decode_response(resp, content_type)
                self._store_cache(result)
                return result
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))

        result = FetchResult(
            url=url,
            final_url=url,
            fetched_at=utcnow(),
            error=last_error or "request failed",
        )
        self._store_cache(result)
        return result

    def _respect_delay(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()
