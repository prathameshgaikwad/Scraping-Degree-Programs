"""Scrapy bridge for the Program Intelligence layer.

This spider lets the existing Scrapy project drive the intelligence pipeline.
It is intentionally thin: the heavy lifting lives in
``degreeprograms.intelligence`` so it can also be run standalone via
``python -m degreeprograms.intelligence.cli``.

Usage (requires Scrapy, which is the project's declared crawler dependency)::

    # default input: degreeprograms/intelligence/testdata/qs_programs.json
    scrapy crawl program-intelligence

    # custom QS-style export
    scrapy crawl program-intelligence -a input=path/to/qs_programs.json -a limit=10
"""

from __future__ import annotations

import json
import os

import scrapy
from twisted.internet import defer, threads

from degreeprograms.intelligence.pipeline import PipelineConfig, ProgramIntelligencePipeline
from degreeprograms.intelligence.store import save_intelligence

DEFAULT_INPUT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "intelligence",
    "testdata",
    "qs_programs.json",
)


class ProgramIntelligenceSpider(scrapy.Spider):
    name = "program-intelligence"
    custom_settings = {
        "FEEDS": {
            "data/intelligence/scrapy_feed.json": {
                "format": "json",
                "encoding": "utf8",
                "indent": 2,
                "overwrite": True,
            }
        },
        "CONCURRENT_REQUESTS": 2,
        "DOWNLOAD_DELAY": 0.5,
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, input: str = "", limit: int = 0, out: str = "data/intelligence",
                 cache: str = "data/cache", **kwargs):
        super().__init__(**kwargs)
        self.input_path = input or DEFAULT_INPUT
        self.limit = int(limit) if limit else 0
        self.config = PipelineConfig(cache_dir=cache, out_dir=out)
        with open(self.input_path, "r", encoding="utf-8") as fh:
            records = json.load(fh)
        if isinstance(records, dict):
            records = [records]
        self.records = records[: self.limit] if self.limit else records

    def start_requests(self):
        for record in self.records:
            url = record.get("program_url")
            if not url and record.get("university_domain"):
                domain = str(record["university_domain"]).lstrip("/")
                url = domain if domain.startswith("http") else "https://" + domain
            if not url:
                self.logger.warning("Skipping record without a URL: %s", record.get("program_name"))
                continue
            yield scrapy.Request(
                url,
                callback=self.parse_program,
                meta={"record": record},
                dont_filter=True,
            )

    @defer.inlineCallbacks
    def parse_program(self, response):
        record = response.meta["record"]
        pipeline = ProgramIntelligencePipeline(self.config)
        try:
            obj, stats = yield threads.deferToThread(pipeline.run, record)
        except Exception as exc:
            self.logger.error("Intelligence extraction failed for %s: %s", record.get("program_name"), exc)
            return
        path = save_intelligence(obj, self.config.out_dir)
        self.logger.info(
            "Extracted %s (pages=%s pdfs=%s) -> %s",
            record.get("program_name"), stats.pages_fetched, stats.pdfs_fetched, path,
        )
        yield obj.model_dump(mode="json")
