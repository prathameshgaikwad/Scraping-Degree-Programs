"""CLI for Phase 2 normalization.

    python -m degreeprograms.normalize.cli --input degreeprograms/qs-spidy.jsonl --out data/normalized
    python -m degreeprograms.cli normalize qs
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .pipeline import NormalizationPipeline, NormalizeConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="normalize", description="Normalize raw QS records")
    parser.add_argument("--input", default="degreeprograms/qs-spidy.jsonl", help="Raw QS JSONL file")
    parser.add_argument("--out", default="data/normalized", help="Output directory")
    parser.add_argument("--aliases", default=None, help="Alias registry JSON (defaults to bundled)")
    parser.add_argument("--force", action="store_true", help="Reprocess even if input is unchanged")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = NormalizeConfig(input_path=args.input, out_dir=args.out, force=args.force)
    if args.aliases:
        config.alias_registry_path = args.aliases

    manifest = NormalizationPipeline(config).run()

    if not args.quiet:
        print(f"[NORMALIZE] input={manifest.input_path} rows={manifest.input_rows}")
        print(f"[NORMALIZE] universities={manifest.universities} "
              f"(needs_review={manifest.universities_needing_review})")
        print(f"[NORMALIZE] programs={manifest.programs} "
              f"(merged={manifest.programs_deduplicated})")
        print(f"[NORMALIZE] by_degree={manifest.programs_by_degree}")
        print(f"[NORMALIZE] by_format={manifest.programs_by_format}")
        print(f"[NORMALIZE] top_countries={dict(list(manifest.programs_by_country.items())[:8])}")
        print(f"[NORMALIZE] wrote {os.path.join(args.out, 'universities.jsonl')}")
        print(f"[NORMALIZE] wrote {os.path.join(args.out, 'programs.jsonl')}")
        print(f"[NORMALIZE] wrote {os.path.join(args.out, 'manifest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
