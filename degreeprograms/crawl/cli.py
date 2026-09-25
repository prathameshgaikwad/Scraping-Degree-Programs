"""CLI for Phase 5 official-site crawling.

    python -m degreeprograms.crawl.cli
    python -m degreeprograms.cli crawl official-sites --limit 10
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .pipeline import CrawlConfig, OfficialSiteCrawlPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crawl", description="Crawl official university sites")
    parser.add_argument("--classifications", default="data/enriched/program_classifications/classifications.jsonl")
    parser.add_argument("--programs", default="data/normalized/programs.jsonl")
    parser.add_argument("--universities", default="data/normalized/universities.jsonl")
    parser.add_argument("--out", default="data/enriched/university_pages")
    parser.add_argument("--cache", default="data/cache")
    parser.add_argument("--profile", default=None, help="Optional applicant profile to filter by target fields")
    parser.add_argument("--relevance", default="HIGH,MEDIUM", help="Comma-separated relevance levels")
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--max-pdfs", type=int, default=3)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-requests", type=int, default=25)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-programs", type=int, default=0, help="Stop after N crawled programs (0=unlimited)")
    parser.add_argument("--max-runtime", type=int, default=0, help="Stop after N seconds (0=unlimited)")
    parser.add_argument("--no-robots", action="store_true", help="Do not honor robots.txt")
    parser.add_argument("--default-delay", type=float, default=0.5, help="Per-domain minimum delay (seconds)")
    parser.add_argument("--render", action="store_true", help="Render JS pages with Playwright (if installed)")
    parser.add_argument("--resolve-domains", action="store_true", help="Enable optional web-search domain resolution")
    parser.add_argument("--force", action="store_true", help="Recrawl completed programs")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    target_codes: List[str] = []
    if args.profile:
        from ..profile.loading import load_profile

        target_codes = load_profile(args.profile).target_field_codes

    config = CrawlConfig(
        classifications_path=args.classifications,
        programs_path=args.programs,
        universities_path=args.universities,
        out_dir=args.out,
        cache_dir=args.cache,
        relevance=[r.strip().upper() for r in args.relevance.split(",") if r.strip()],
        target_field_codes=target_codes,
        resolve_domains=args.resolve_domains,
        max_pages=args.max_pages,
        max_pdfs=args.max_pdfs,
        max_depth=args.max_depth,
        max_requests=args.max_requests,
        delay=args.delay,
        max_programs=args.max_programs,
        max_runtime_seconds=args.max_runtime,
        obey_robots=not args.no_robots,
        default_delay=args.default_delay,
        render=args.render,
        force=args.force,
        limit=args.limit,
    )
    manifest = OfficialSiteCrawlPipeline(config).run()
    if not args.quiet:
        print(f"[CRAWL] candidates={manifest.candidates} domains_resolved={manifest.domains_resolved} missing={manifest.domains_missing}")
        print(f"[CRAWL] success={manifest.jobs_success} failed={manifest.jobs_failed} skipped={manifest.jobs_skipped} resumed_skipped={manifest.jobs_resumed_skipped}")
        print(f"[CRAWL] blocked={manifest.jobs_blocked} timed_out={manifest.jobs_timed_out} blocked_domains={manifest.blocked_domains}")
        print(f"[CRAWL] processed={manifest.programs_processed} stopped_early={manifest.stopped_early} remaining={manifest.remaining}")
        print(f"[CRAWL] pages={manifest.pages} pdfs={manifest.pdfs}")
        print(f"[CRAWL] pages_by_type={manifest.pages_by_type}")
        print(f"[CRAWL] wrote {os.path.join(args.out, 'pages.jsonl')}")
        print(f"[CRAWL] wrote {os.path.join(args.out, 'state.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
