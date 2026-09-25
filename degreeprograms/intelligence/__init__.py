"""Program Intelligence extraction layer.

This package turns a single discovered Master's program into a structured,
evidence-backed Program Intelligence object by performing targeted multi-page
discovery against official university sources.

It is intentionally decoupled from Scrapy so it can be driven by a Scrapy
pipeline, a CLI, or a queue worker. It only depends on packages that are
already available in this project environment (requests, beautifulsoup4, lxml,
pydantic, httpx).
"""

from .versions import CRAWLER_VERSION, EXTRACTOR_VERSION, SCHEMA_VERSION

__all__ = ["CRAWLER_VERSION", "EXTRACTOR_VERSION", "SCHEMA_VERSION"]
