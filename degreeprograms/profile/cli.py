"""CLI for Phase 4 applicant profiles.

    python -m degreeprograms.profile.cli --input degreeprograms/profile/testdata/applicant.example.yaml
    python -m degreeprograms.cli profile --input path/to/applicant.yaml --show
"""

from __future__ import annotations

import argparse
import json
from typing import List, Optional

from .loading import load_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="profile", description="Load and validate an applicant profile")
    parser.add_argument(
        "--input",
        default="degreeprograms/profile/testdata/applicant.example.yaml",
        help="Applicant profile (.yaml/.yml/.json)",
    )
    parser.add_argument("--show", action="store_true", help="Print the full normalized profile JSON")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profile = load_profile(args.input)
    except Exception as exc:
        print(f"[PROFILE] INVALID: {type(exc).__name__}: {exc}")
        return 1

    primary = profile.primary_education
    print(f"[PROFILE] applicant_id={profile.applicant_id}")
    print(f"[PROFILE] highest_degree={profile.highest_degree_level.value}")
    if primary:
        print(
            f"[PROFILE] education={primary.degree} in {primary.field} "
            f"({primary.degree_level.value}, category={primary.field_category.value if primary.field_category else None})"
        )
        print(f"[PROFILE] cgpa={primary.cgpa} scale={primary.cgpa_scale}")
    print(f"[PROFILE] experience_years={profile.total_experience_years}")
    print(f"[PROFILE] target_fields={profile.target_fields}")
    print(f"[PROFILE] target_field_codes={profile.target_field_codes}")
    print(f"[PROFILE] technical_background={len(profile.technical_background)} skills")
    print(f"[PROFILE] coursework={len(profile.coursework)} items")
    print(f"[PROFILE] testing={profile.testing.model_dump(mode='json')}")

    if args.show:
        print(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
