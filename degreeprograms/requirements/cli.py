"""CLI for Phase 6 requirement extraction.

    python -m degreeprograms.requirements.cli
    python -m degreeprograms.cli extract requirements
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .pipeline import RequirementsConfig, RequirementsPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="extract", description="Extract program requirements with evidence")
    parser.add_argument("--pages", default="data/enriched/university_pages/pages.jsonl")
    parser.add_argument("--programs", default="data/normalized/programs.jsonl")
    parser.add_argument("--universities", default="data/normalized/universities.jsonl")
    parser.add_argument("--out", default="data/enriched/requirements")
    parser.add_argument("--llm", action="store_true", help="Enable the optional LLM pass (if configured)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = RequirementsConfig(
        pages_path=args.pages,
        programs_path=args.programs,
        universities_path=args.universities,
        out_dir=args.out,
        use_llm=args.llm,
        force=args.force,
        limit=args.limit,
    )
    manifest = RequirementsPipeline(config).run()
    if not args.quiet:
        print(f"[EXTRACT] programs={manifest.programs} pages_considered={manifest.pages_considered}")
        print(f"[EXTRACT] pages_extracted={manifest.pages_extracted} cache_hits={manifest.cache_hits}")
        print(f"[EXTRACT] programs_with_evidence={manifest.programs_with_evidence}")
        print(f"[EXTRACT] by_completeness={manifest.by_completeness}")
        print(f"[EXTRACT] wrote {os.path.join(args.out, 'requirements.jsonl')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
