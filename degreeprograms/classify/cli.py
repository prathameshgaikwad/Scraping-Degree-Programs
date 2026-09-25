"""CLI for Phase 3 classification.

    python -m degreeprograms.classify.cli --programs data/normalized/programs.jsonl
    python -m degreeprograms.cli classify programs
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .pipeline import ClassificationPipeline, ClassifyConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="classify", description="Classify canonical programs")
    parser.add_argument("--programs", default="data/normalized/programs.jsonl")
    parser.add_argument("--out", default="data/enriched/program_classifications")
    parser.add_argument("--force", action="store_true", help="Recompute even if unchanged")
    parser.add_argument("--no-llm", action="store_true", help="Disable the optional LLM fallback")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = ClassifyConfig(
        programs_path=args.programs, out_dir=args.out, force=args.force, use_llm=not args.no_llm
    )
    manifest = ClassificationPipeline(config).run()
    if not args.quiet:
        print(f"[CLASSIFY] programs={manifest.programs} cache_hits={manifest.cache_hits} llm_calls={manifest.llm_calls}")
        print(f"[CLASSIFY] by_relevance={manifest.by_relevance}")
        print(f"[CLASSIFY] by_primary_field={manifest.by_primary_field}")
        print(f"[CLASSIFY] wrote {os.path.join(args.out, 'classifications.jsonl')}")
        print(f"[CLASSIFY] wrote {os.path.join(args.out, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
