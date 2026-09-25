"""Resumable crawl state (Sections 24, 28).

Persisted as JSON. Tracks which programs have been crawled, the parser version
used, and a per-URL content-hash cache so unchanged pages can be detected.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from .models import CrawlJobRecord
from .versions import CRAWLER_VERSION, PARSER_VERSION


class CrawlState:
    def __init__(self, path: str) -> None:
        self.path = path
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.pages: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        self.jobs = data.get("jobs", {})
        self.pages = data.get("pages", {})

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = {"parser_version": PARSER_VERSION, "jobs": self.jobs, "pages": self.pages}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        # OneDrive/antivirus can briefly lock the destination; retry then fall back.
        for attempt in range(5):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                time.sleep(0.2 * (attempt + 1))
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        try:
            os.remove(tmp)
        except OSError:
            pass

    def is_done(self, program_id: str) -> bool:
        """A program is done only if it succeeded under the current versions.

        Bumping ``CRAWLER_VERSION``/``PARSER_VERSION`` invalidates prior successes
        so an upgraded crawl re-captures them (and chunked runs still progress,
        because freshly-crawled jobs adopt the new version and are then skipped).
        """
        job = self.jobs.get(program_id)
        if not job or job.get("status") != "SUCCESS":
            return False
        return job.get("crawler_version") == CRAWLER_VERSION and job.get("parser_version") == PARSER_VERSION

    def mark_started(self, program_id: str) -> None:
        self.jobs[program_id] = {"status": "IN_PROGRESS", "parser_version": PARSER_VERSION}

    def mark_finished(self, job: CrawlJobRecord) -> None:
        self.jobs[job.program_id] = job.model_dump(mode="json")

    def get_page_hash(self, url: str) -> Optional[str]:
        entry = self.pages.get(url)
        return entry.get("content_hash") if entry else None

    def update_page(self, url: str, content_hash: Optional[str], status: str) -> None:
        self.pages[url] = {"content_hash": content_hash, "status": status}
