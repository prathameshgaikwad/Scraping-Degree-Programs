"""Tests for the Phase 5 crawl layer (no network; uses a stub fetcher).

    python -m unittest discover -s degreeprograms/crawl/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from degreeprograms.crawl.classify import classify_page_type, source_tier_for
from degreeprograms.crawl.crawler import CrawlLimits, OfficialSiteCrawler
from degreeprograms.crawl.domains import DomainResolver
from degreeprograms.crawl.models import CrawlStatus, CrawlTarget, PageType, SourceTier
from degreeprograms.crawl.pipeline import CrawlConfig, OfficialSiteCrawlPipeline
from degreeprograms.intelligence.fetch import BudgetExceeded, FetchResult

HOMEPAGE = """
<html><head><title>Example University</title></head><body>
<h1>Example University</h1>
<a href="/msc-artificial-intelligence">MSc Artificial Intelligence</a>
<a href="/admissions/entry-requirements">Entry requirements</a>
<a href="/tuition-fees">Tuition fees</a>
<a href="/privacy">Privacy</a>
</body></html>
"""

PROGRAM_PAGE = """
<html><head><title>MSc Artificial Intelligence</title></head><body>
<h1>MSc Artificial Intelligence</h1>
<p>Programme overview. Duration of studies: 1 year, full-time.</p>
<a href="/admissions/entry-requirements">Entry requirements</a>
<a href="/tuition-fees">Tuition fees</a>
</body></html>
"""

REQUIREMENTS_PAGE = """
<html><head><title>Entry requirements</title></head><body>
<h1>Entry requirements</h1>
<p>Entry requirements: a bachelor's degree in computer science. English language requirements apply.</p>
</body></html>
"""

TUITION_PAGE = """
<html><head><title>Tuition fees</title></head><body>
<h1>Tuition fees</h1>
<p>Tuition fees are 20,000 GBP per year for international students.</p>
</body></html>
"""

PRIVACY_PAGE = "<html><head><title>Privacy</title></head><body><p>Privacy policy</p></body></html>"


class StubFetcher:
    def __init__(self, pages):
        # url -> (status, content_type, body)
        self.pages = pages
        self.requests_made = 0

    def fetch(self, url):
        self.requests_made += 1
        if url not in self.pages:
            return FetchResult(url=url, final_url=url, status=404, error="not found", fetched_at="t")
        status, content_type, body = self.pages[url]
        result = FetchResult(
            url=url, final_url=url, status=status, content_type=content_type, fetched_at="t"
        )
        if "pdf" in content_type:
            result.binary = body
        else:
            result.text = body
        return result


class BudgetFetcher(StubFetcher):
    def __init__(self, pages, limit):
        super().__init__(pages)
        self.limit = limit

    def fetch(self, url):
        if self.requests_made >= self.limit:
            raise BudgetExceeded("budget")
        return super().fetch(url)


def _site():
    return StubFetcher(
        {
            "https://example.edu/": (200, "text/html", HOMEPAGE),
            "https://example.edu/msc-artificial-intelligence": (200, "text/html", PROGRAM_PAGE),
            "https://example.edu/admissions/entry-requirements": (200, "text/html", REQUIREMENTS_PAGE),
            "https://example.edu/tuition-fees": (200, "text/html", TUITION_PAGE),
            "https://example.edu/privacy": (200, "text/html", PRIVACY_PAGE),
        }
    )


class ClassifyTests(unittest.TestCase):
    def test_page_types(self):
        self.assertEqual(
            classify_page_type("https://x.edu/admissions/entry-requirements", "", "Entry requirements"),
            PageType.REQUIREMENTS_PAGE,
        )
        self.assertEqual(
            classify_page_type("https://x.edu/tuition-fees", "", "Tuition fees"),
            PageType.TUITION_PAGE,
        )
        self.assertEqual(
            classify_page_type("https://x.edu/msc-ai", "MSc AI", "Programme overview"),
            PageType.PROGRAM_PAGE,
        )
        self.assertEqual(classify_page_type("https://x.edu/privacy", "", "Privacy policy"), PageType.IRRELEVANT)
        self.assertEqual(classify_page_type("https://x.edu/random", "", "hello"), PageType.UNKNOWN)

    def test_source_tier(self):
        self.assertEqual(source_tier_for(PageType.PROGRAM_PAGE), SourceTier.PROGRAM_PAGE)
        self.assertEqual(source_tier_for(PageType.REQUIREMENTS_PAGE), SourceTier.ADMISSIONS)


class DomainTests(unittest.TestCase):
    def test_registry_resolution(self):
        resolver = DomainResolver({"University of Warwick": "warwick.ac.uk"})
        result = resolver.resolve(["University of Warwick"])
        self.assertEqual(result.domain, "warwick.ac.uk")
        self.assertEqual(result.method, "REGISTRY")

    def test_existing_domain_precedence(self):
        resolver = DomainResolver({"University of Warwick": "warwick.ac.uk"})
        result = resolver.resolve(["University of Warwick"], existing_domain="https://warwick.ac.uk/x")
        self.assertEqual(result.domain, "warwick.ac.uk")
        self.assertEqual(result.method, "EXISTING")

    def test_unresolved(self):
        result = DomainResolver({}).resolve(["Some University"])
        self.assertIsNone(result.domain)
        self.assertEqual(result.method, "UNRESOLVED")


class CrawlerTests(unittest.TestCase):
    def _target(self):
        return CrawlTarget(
            program_id="p1",
            university_id="example-university",
            program_name="MSc Artificial Intelligence",
            university_name="Example University",
        )

    def test_crawl_finds_targeted_pages(self):
        crawler = OfficialSiteCrawler(_site(), CrawlLimits(max_pages=8, max_depth=2))
        result = crawler.crawl(self._target(), "https://example.edu/")
        urls = {p.url for p in result.pages}
        self.assertIn("https://example.edu/msc-artificial-intelligence", urls)
        self.assertIn("https://example.edu/admissions/entry-requirements", urls)
        self.assertEqual(result.job.status, CrawlStatus.SUCCESS)
        types = {p.page_type for p in result.pages}
        self.assertIn(PageType.PROGRAM_PAGE, types)
        self.assertIn(PageType.REQUIREMENTS_PAGE, types)

    def test_irrelevant_pages_not_followed(self):
        crawler = OfficialSiteCrawler(_site(), CrawlLimits(max_pages=8, max_depth=2))
        result = crawler.crawl(self._target(), "https://example.edu/")
        self.assertNotIn("https://example.edu/privacy", {p.url for p in result.pages})

    def test_failed_page_does_not_crash(self):
        pages = _site().pages
        pages["https://example.edu/msc-artificial-intelligence"] = (500, "text/html", "")
        crawler = OfficialSiteCrawler(StubFetcher(pages), CrawlLimits(max_pages=8, max_depth=2))
        result = crawler.crawl(self._target(), "https://example.edu/")
        self.assertTrue(any(p.crawl_status == CrawlStatus.FAILED for p in result.pages))
        self.assertTrue(any(p.crawl_status == CrawlStatus.SUCCESS for p in result.pages))

    def test_budget_exceeded_recorded(self):
        crawler = OfficialSiteCrawler(BudgetFetcher(_site().pages, limit=1), CrawlLimits(max_depth=2))
        result = crawler.crawl(self._target(), "https://example.edu/")
        self.assertEqual(result.job.status, CrawlStatus.FAILED)
        self.assertEqual(result.job.reason, "BUDGET_EXCEEDED")


class PipelineTests(unittest.TestCase):
    def _write_fixtures(self, tmp):
        programs_path = os.path.join(tmp, "programs.jsonl")
        universities_path = os.path.join(tmp, "universities.jsonl")
        classifications_path = os.path.join(tmp, "classifications.jsonl")
        with open(programs_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "program_id": "p1",
                "university_id": "example-university",
                "name": "MSc Artificial Intelligence",
                "normalized_name": "msc artificial intelligence",
                "source": {"program_url": "https://www.topuniversities.com/x"},
            }) + "\n")
        with open(universities_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "university_id": "example-university",
                "canonical_name": "Example University",
                "official_domain": "example.edu",
                "aliases": [{"alias": "Example University"}],
            }) + "\n")
        with open(classifications_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "program_id": "p1",
                "relevance": "HIGH",
                "primary_field": "ARTIFICIAL_INTELLIGENCE",
                "secondary_fields": ["MACHINE_LEARNING"],
            }) + "\n")
        return programs_path, universities_path, classifications_path

    def test_end_to_end_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs_path, universities_path, classifications_path = self._write_fixtures(tmp)
            out_dir = os.path.join(tmp, "out")
            config = CrawlConfig(
                classifications_path=classifications_path,
                programs_path=programs_path,
                universities_path=universities_path,
                out_dir=out_dir,
                max_pages=8,
                max_depth=2,
            )
            manifest = OfficialSiteCrawlPipeline(config, fetcher=_site()).run()
            self.assertEqual(manifest.candidates, 1)
            self.assertEqual(manifest.domains_resolved, 1)
            self.assertEqual(manifest.jobs_success, 1)
            self.assertGreaterEqual(manifest.pages, 3)
            self.assertTrue(os.path.exists(os.path.join(out_dir, "pages.jsonl")))
            self.assertTrue(os.path.exists(os.path.join(out_dir, "state.json")))

            # Resume: completed program is skipped, existing pages retained.
            manifest2 = OfficialSiteCrawlPipeline(config, fetcher=_site()).run()
            self.assertEqual(manifest2.jobs_resumed_skipped, 1)
            self.assertEqual(manifest2.pages, manifest.pages)

    def test_no_domain_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs_path, universities_path, classifications_path = self._write_fixtures(tmp)
            with open(universities_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "university_id": "example-university",
                    "canonical_name": "Example University",
                    "official_domain": None,
                    "aliases": [],
                }) + "\n")
            config = CrawlConfig(
                classifications_path=classifications_path,
                programs_path=programs_path,
                universities_path=universities_path,
                out_dir=os.path.join(tmp, "out"),
            )
            manifest = OfficialSiteCrawlPipeline(config, fetcher=_site()).run()
            self.assertEqual(manifest.jobs_skipped, 1)
            self.assertEqual(manifest.domains_missing, 1)


if __name__ == "__main__":
    unittest.main()
