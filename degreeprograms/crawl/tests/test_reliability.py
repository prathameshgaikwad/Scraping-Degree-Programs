"""Reliability tests: politeness/robots, rendering detection, QS-slug matching,
blocked-domain circuit breaker, and bounded runs.

    python -m unittest discover -s degreeprograms/crawl/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from urllib.parse import urlparse

from degreeprograms.crawl.crawler import CrawlLimits, OfficialSiteCrawler
from degreeprograms.crawl.models import CrawlStatus, CrawlTarget
from degreeprograms.crawl.pipeline import CrawlConfig, OfficialSiteCrawlPipeline
from degreeprograms.crawl.politeness import PoliteFetcher, Politeness
from degreeprograms.crawl.render import make_renderer, needs_render
from degreeprograms.intelligence.fetch import FetchResult

ROBOTS = "User-agent: *\nDisallow: /private\nCrawl-delay: 2\n"


class RobotsStub:
    def __init__(self, pages=None, allow_cache=False):
        self.pages = pages or {}
        self.allow_cache = allow_cache
        self.calls = []
        self.requests_made = 0

    def has_fresh_cache(self, url):
        return self.allow_cache

    def fetch(self, url, force=False):
        self.calls.append(url)
        self.requests_made += 1
        if url.endswith("/robots.txt"):
            return FetchResult(url=url, final_url=url, status=200, text=ROBOTS, fetched_at="t")
        if url in self.pages:
            return FetchResult(url=url, final_url=url, status=200, text=self.pages[url], fetched_at="t")
        return FetchResult(url=url, final_url=url, status=404, error="nf", fetched_at="t")


class PolitenessTests(unittest.TestCase):
    def test_robots_allow_disallow_and_delay(self):
        stub = RobotsStub()
        pol = Politeness(stub, user_agent="*", obey_robots=True, default_delay=0.5)
        self.assertTrue(pol.allows("https://x.edu/public"))
        self.assertFalse(pol.allows("https://x.edu/private/page"))
        self.assertEqual(pol.delay_for("https://x.edu/public"), 2.0)
        # robots.txt fetched once per host
        self.assertEqual(sum(1 for c in stub.calls if c.endswith("/robots.txt")), 1)

    def test_disobey_robots_uses_default_delay(self):
        stub = RobotsStub()
        pol = Politeness(stub, obey_robots=False, default_delay=0.3)
        self.assertTrue(pol.allows("https://x.edu/private/x"))
        self.assertEqual(pol.delay_for("https://x.edu/private/x"), 0.3)
        self.assertEqual(stub.calls, [])  # never fetched robots.txt

    def test_polite_fetcher_blocks_disallowed_without_delegating(self):
        stub = RobotsStub(pages={"https://x.edu/private/x": "<html>secret</html>"})
        pf = PoliteFetcher(stub, Politeness(stub, obey_robots=True, default_delay=0.0))
        result = pf.fetch("https://x.edu/private/x")
        self.assertEqual(result.status, 403)
        self.assertEqual(result.error, "robots_disallowed")
        self.assertNotIn("https://x.edu/private/x", stub.calls)

    def test_polite_fetcher_serves_cache_without_robots(self):
        stub = RobotsStub(pages={"https://x.edu/private/x": "<html>ok</html>"}, allow_cache=True)
        pf = PoliteFetcher(stub, Politeness(stub, obey_robots=True, default_delay=0.0))
        result = pf.fetch("https://x.edu/private/x")
        self.assertEqual(result.status, 200)


class RenderTests(unittest.TestCase):
    def test_needs_render(self):
        self.assertTrue(needs_render(403, "blocked"))
        self.assertTrue(needs_render(200, "<html>Enable JavaScript to continue</html>"))
        self.assertTrue(needs_render(200, "short"))
        self.assertFalse(needs_render(200, "x" * 1000))

    def test_make_renderer_disabled_or_missing(self):
        self.assertIsNone(make_renderer(False))


class RendererCrawlerTests(unittest.TestCase):
    def _block_fetcher(self, error="Forbidden", status=403):
        class _F:
            def __init__(self):
                self.requests_made = 0

            def fetch(self, url, force=False):
                self.requests_made += 1
                return FetchResult(url=url, final_url=url, status=status, error=error, fetched_at="t")

        return _F()

    def test_blocked_response_is_rendered(self):
        class FakeRenderer:
            def __init__(self):
                self.calls = []

            def render(self, url):
                self.calls.append(url)
                return "<html><head><title>Rendered</title></head><body>" + "x" * 800 + "</body></html>"

        renderer = FakeRenderer()
        crawler = OfficialSiteCrawler(self._block_fetcher(), CrawlLimits(max_depth=0), renderer=renderer)
        target = CrawlTarget(program_id="p", university_id="u", program_name="X")
        result = crawler.crawl(target, "https://blocked.edu/")
        self.assertTrue(any(p.crawl_status == CrawlStatus.SUCCESS and p.rendered for p in result.pages))
        self.assertIn("https://blocked.edu/", renderer.calls)
        self.assertEqual(result.job.status, CrawlStatus.SUCCESS)

    def test_robots_disallowed_is_not_rendered(self):
        renderer_calls = []

        class FakeRenderer:
            def render(self, url):
                renderer_calls.append(url)
                return "<html>" + "x" * 800 + "</html>"

        crawler = OfficialSiteCrawler(
            self._block_fetcher(error="robots_disallowed"), CrawlLimits(max_depth=0), renderer=FakeRenderer()
        )
        target = CrawlTarget(program_id="p", university_id="u", program_name="X")
        result = crawler.crawl(target, "https://x.edu/private")
        self.assertEqual(renderer_calls, [])  # robots must be respected
        self.assertEqual(result.job.reason, "BLOCKED")


class SlugTests(unittest.TestCase):
    def test_program_tokens_include_slug(self):
        target = CrawlTarget(
            program_id="p", university_id="u", program_name="Applied AI",
            qs_program_url="https://www.topuniversities.com/universities/x/postgrad/applied-artificial-intelligence",
        )
        tokens = OfficialSiteCrawler._program_tokens(target)
        self.assertIn("applied", tokens)
        self.assertIn("artificial", tokens)
        self.assertIn("intelligence", tokens)

    def test_slug_boosts_matching_link(self):
        target = CrawlTarget(
            program_id="p", university_id="u", program_name="Data Science",
            qs_program_url="https://www.topuniversities.com/universities/x/postgrad/applied-artificial-intelligence",
        )
        tokens = OfficialSiteCrawler._program_tokens(target)
        match = OfficialSiteCrawler._program_bonus("https://x.edu/courses/applied-artificial-intelligence", "Applied AI", tokens)
        other = OfficialSiteCrawler._program_bonus("https://x.edu/courses/history", "History", tokens)
        self.assertGreater(match, other)


class PipelineStubFetcher:
    """Returns 403 for a set of blocked hosts; simple HTML elsewhere."""

    def __init__(self, block_hosts=()):
        self.block = set(block_hosts)
        self.requests_made = 0

    def fetch(self, url, force=False):
        self.requests_made += 1
        host = urlparse(url).netloc.lower()
        if any(host == h or host.endswith("." + h) for h in self.block):
            return FetchResult(url=url, final_url=url, status=403, error="Forbidden", fetched_at="t")
        if url.rstrip("/") in (f"https://{host}", f"https://www.{host}"):
            body = "<html><head><title>Home</title></head><body>Welcome</body></html>"
        else:
            body = "<html><head><title>Page</title></head><body><p>Details</p></body></html>"
        return FetchResult(url=url, final_url=url, status=200, text=body, content_type="text/html", fetched_at="t")


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _fixtures(tmp, domain_for):
    programs = os.path.join(tmp, "programs.jsonl")
    universities = os.path.join(tmp, "universities.jsonl")
    classifications = os.path.join(tmp, "classifications.jsonl")
    _write(programs, [
        {"program_id": f"p{i}", "university_id": uid, "name": f"Program {i}", "location": {}}
        for i, uid in enumerate(["u1", "u1", "u1", "u2"])
    ])
    _write(universities, [
        {"university_id": "u1", "canonical_name": "Blocked University", "official_domain": domain_for["u1"], "aliases": []},
        {"university_id": "u2", "canonical_name": "Good University", "official_domain": domain_for["u2"], "aliases": []},
    ])
    _write(classifications, [
        {"program_id": f"p{i}", "relevance": "HIGH", "primary_field": "DATA_SCIENCE", "secondary_fields": []}
        for i in range(4)
    ])
    return programs, universities, classifications


class PipelineReliabilityTests(unittest.TestCase):
    def test_blocked_domain_circuit_breaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            progs, unis, cls = _fixtures(tmp, {"u1": "blocked.edu", "u2": "good.edu"})
            cfg = CrawlConfig(
                programs_path=progs, universities_path=unis, classifications_path=cls,
                out_dir=os.path.join(tmp, "out"), max_pages=3, max_depth=1,
                blocked_domain_threshold=1,
            )
            manifest = OfficialSiteCrawlPipeline(cfg, fetcher=PipelineStubFetcher(block_hosts={"blocked.edu"})).run()
            self.assertEqual(manifest.jobs_blocked, 1)
            self.assertIn("blocked.edu", manifest.blocked_domains)
            # remaining blocked.edu programs skipped via circuit breaker
            self.assertGreaterEqual(manifest.jobs_skipped, 2)
            self.assertGreaterEqual(manifest.jobs_success, 1)  # good.edu succeeds

    def test_bounded_run_stops_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            progs, unis, cls = _fixtures(tmp, {"u1": "a.edu", "u2": "b.edu"})
            cfg = CrawlConfig(
                programs_path=progs, universities_path=unis, classifications_path=cls,
                out_dir=os.path.join(tmp, "out"), max_pages=2, max_depth=0, max_programs=1,
            )
            manifest = OfficialSiteCrawlPipeline(cfg, fetcher=PipelineStubFetcher()).run()
            self.assertTrue(manifest.stopped_early)
            self.assertEqual(manifest.programs_processed, 1)
            self.assertGreater(manifest.remaining, 0)


if __name__ == "__main__":
    unittest.main()
