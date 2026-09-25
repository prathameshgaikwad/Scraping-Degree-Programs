"""CLI to run the Program Intelligence UI/API.

    python -m degreeprograms.cli serve
    python -m degreeprograms.webapp.cli --port 8000
"""

from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .app import run
from .service import ProgramsService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serve", description="Program Intelligence UI/API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--programs", default="data/normalized/programs.jsonl")
    parser.add_argument("--classifications", default="data/enriched/program_classifications/classifications.jsonl")
    parser.add_argument("--requirements", default="data/enriched/requirements/requirements.jsonl")
    parser.add_argument("--eligibility", default="data/matching/eligibility/eligibility.jsonl")
    parser.add_argument("--universities", default="data/normalized/universities.jsonl")
    parser.add_argument("--profile", default="degreeprograms/profile/testdata/applicant.example.yaml")
    parser.add_argument("--frontend-dir", default=None, help="React build to serve at / (default: static/app)")
    parser.add_argument("--cors-origin", default=os.environ.get("WEBAPP_CORS_ORIGIN"),
                        help="Access-Control-Allow-Origin value for cross-origin dev (e.g. * or http://localhost:5173)")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    service = ProgramsService(
        programs_path=args.programs,
        classifications_path=args.classifications,
        requirements_path=args.requirements,
        eligibility_path=args.eligibility,
        universities_path=args.universities,
        profile_path=args.profile,
    )
    run(
        args.host,
        args.port,
        service,
        frontend_dir=args.frontend_dir,
        cors_origin=args.cors_origin,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
