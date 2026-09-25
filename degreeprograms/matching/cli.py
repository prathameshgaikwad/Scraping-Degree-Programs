"""CLI for Phase 7 eligibility matching.

    python -m degreeprograms.matching.cli
    python -m degreeprograms.cli match applicant
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .pipeline import MatchConfig, MatchPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="match", description="Match an applicant against requirements")
    parser.add_argument("--profile", default="degreeprograms/profile/testdata/applicant.example.yaml")
    parser.add_argument("--requirements", default="data/enriched/requirements/requirements.jsonl")
    parser.add_argument("--programs", default="data/normalized/programs.jsonl")
    parser.add_argument("--universities", default="data/normalized/universities.jsonl")
    parser.add_argument("--out", default="data/matching/eligibility")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = MatchConfig(
        profile_path=args.profile,
        requirements_path=args.requirements,
        programs_path=args.programs,
        universities_path=args.universities,
        out_dir=args.out,
        use_llm=not args.no_llm,
        force=args.force,
        limit=args.limit,
    )
    manifest = MatchPipeline(config).run()
    if not args.quiet:
        print(f"[MATCH] programs={manifest.programs} cache_hits={manifest.cache_hits} llm_calls={manifest.llm_calls}")
        print(f"[MATCH] by_state={manifest.by_state}")
        print(f"[MATCH] wrote {os.path.join(args.out, 'eligibility.jsonl')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
