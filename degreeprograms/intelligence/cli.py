"""Command line entry point.

Examples
--------
Run the bundled test set::

    python -m degreeprograms.intelligence.cli --input degreeprograms/intelligence/testdata/qs_programs.json --limit 5

Run a single program by URL::

    python -m degreeprograms.intelligence.cli --url https://... --name "MSc Artificial Intelligence" --university "Example University" --country Germany
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from .pipeline import PipelineConfig, ProgramIntelligencePipeline
from .store import save_completeness_summary


def load_records(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return [data]
    return data


def build_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        cache_dir=args.cache,
        out_dir=args.out,
        max_pages=args.max_pages,
        max_pdfs=args.max_pdfs,
        max_depth=args.max_depth,
        max_requests=args.max_requests,
        timeout=args.timeout,
        delay=args.delay,
        use_llm=not args.no_llm,
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Program Intelligence extraction")
    parser.add_argument("--input", help="JSON file with QS-style program records")
    parser.add_argument("--url", help="Single official program URL")
    parser.add_argument("--name", help="Program name (with --url)")
    parser.add_argument("--university", help="University name (with --url)")
    parser.add_argument("--country", help="Country (with --url)")
    parser.add_argument("--city", help="City (with --url)")
    parser.add_argument("--university-domain", dest="university_domain", help="University domain (with --url)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of records")
    parser.add_argument("--out", default="data/intelligence", help="Output directory")
    parser.add_argument("--cache", default="data/cache", help="HTTP cache directory")
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--max-pdfs", type=int, default=3)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-requests", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--no-llm", action="store_true", help="Disable the optional LLM pass")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.input and not args.url:
        parser.error("Provide --input or --url")

    if args.url:
        records = [
            {
                "program_name": args.name,
                "university": args.university,
                "country": args.country,
                "city": args.city,
                "program_url": args.url,
                "university_domain": args.university_domain,
            }
        ]
    else:
        records = load_records(args.input)

    if args.limit:
        records = records[: args.limit]

    config = build_config(args)
    pipeline = ProgramIntelligencePipeline(config)

    results = []
    for index, record in enumerate(records, start=1):
        label = record.get("program_name") or record.get("name") or record.get("program_url")
        if not args.quiet:
            print(f"[{index}/{len(records)}] {label}", flush=True)
        try:
            obj, stats, path = pipeline.run_and_save(record)
        except Exception as exc:  # keep the batch alive
            print(f"  FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        results.append(obj)
        if not args.quiet:
            c = obj.completeness
            print(
                "   -> {path}\n      pages={p} pdfs={pdf} requests={r} "
                "completeness: identity={i} fees={f} deadlines={d} tests={t} gre={g}".format(
                    path=os.path.relpath(path),
                    p=stats.pages_fetched,
                    pdf=stats.pdfs_fetched,
                    r=stats.requests_made,
                    i=int(c.identity),
                    f=int(c.fees),
                    d=int(c.deadlines),
                    t=int(c.english_tests),
                    g=int(c.gre or c.gmat),
                ),
                flush=True,
            )
        if stats.errors and not args.quiet:
            for err in stats.errors[:5]:
                print(f"      ! {err}")

    if results:
        summary = save_completeness_summary(results, config.out_dir)
        if not args.quiet:
            print(f"\nSaved {len(results)} records. Summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
