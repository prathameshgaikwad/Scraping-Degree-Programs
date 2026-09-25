"""Top-level pipeline CLI dispatcher.

Only the implemented stages are wired up; later phases are listed so the shape
is visible, but they intentionally error until built.

    python -m degreeprograms.cli normalize qs
"""

from __future__ import annotations

import sys
from typing import List, Optional

_IMPLEMENTED = {"normalize"}


def _usage() -> str:
    return (
        "usage: python -m degreeprograms.cli <stage> [options]\n\n"
        "stages:\n"
        "  normalize qs        Normalize raw QS records into canonical entities (implemented)\n"
        "  classify programs   Program relevance classification (implemented)\n"
        "  profile             Load/validate an applicant profile (implemented)\n"
        "  crawl official-sites Crawl official university sites (implemented)\n"
        "  extract requirements Requirement extraction with evidence (implemented)\n"
        "  match applicant     Applicant eligibility matching (implemented)\n"
        "  evaluate            Evaluate correctness against gold sets (implemented)\n"
        "  serve               Run the local UI/API (implemented)\n"
        "  pipeline            Full pipeline (not implemented yet)\n"
    )


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_usage())
        return 0

    stage = argv[0]
    rest = argv[1:]

    if stage == "normalize":
        if rest and rest[0] == "qs":
            rest = rest[1:]
        from degreeprograms.normalize.cli import main as normalize_main

        return normalize_main(rest)

    if stage == "classify":
        if rest and rest[0] == "programs":
            rest = rest[1:]
        from degreeprograms.classify.cli import main as classify_main

        return classify_main(rest)

    if stage == "profile":
        from degreeprograms.profile.cli import main as profile_main

        return profile_main(rest)

    if stage == "crawl":
        if rest and rest[0] == "official-sites":
            rest = rest[1:]
        from degreeprograms.crawl.cli import main as crawl_main

        return crawl_main(rest)

    if stage == "extract":
        if rest and rest[0] == "requirements":
            rest = rest[1:]
        from degreeprograms.requirements.cli import main as extract_main

        return extract_main(rest)

    if stage == "match":
        if rest and rest[0] == "applicant":
            rest = rest[1:]
        from degreeprograms.matching.cli import main as match_main

        return match_main(rest)

    if stage == "evaluate":
        from degreeprograms.evaluation.cli import main as evaluate_main

        return evaluate_main(rest)

    if stage in ("serve", "ui"):
        from degreeprograms.webapp.cli import main as serve_main

        return serve_main(rest)

    if stage == "pipeline":
        print(f"'{stage}' is not implemented yet (see development order in the spec).", file=sys.stderr)
        return 2

    print(_usage(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
