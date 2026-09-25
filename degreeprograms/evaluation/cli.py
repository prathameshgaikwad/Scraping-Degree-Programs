"""CLI for Phase 8 evaluation.

    python -m degreeprograms.cli evaluate
    python -m degreeprograms.cli evaluate classification
    python -m degreeprograms.evaluation.cli --classifications data/enriched/program_classifications/classifications.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Optional

from ..normalize.io import ensure_dir, utcnow, write_json
from .models import EvaluationReport
from .runners import (
    dataset_path,
    evaluate_classification,
    evaluate_eligibility,
    evaluate_page_classification,
    evaluate_requirements,
    evaluate_universities,
)
from .versions import EVALUATION_VERSION

_DEFAULT_CLASSIFICATIONS = "data/enriched/program_classifications/classifications.jsonl"
_DEFAULT_UNIVERSITIES = "data/normalized/universities.jsonl"
_DEFAULT_PAGES = "data/enriched/university_pages/pages.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evaluate", description="Evaluate pipeline correctness against gold sets")
    parser.add_argument("target", nargs="?", default="all",
                        choices=["all", "classification", "universities", "pages", "requirements", "eligibility"])
    parser.add_argument("--classifications", default=_DEFAULT_CLASSIFICATIONS)
    parser.add_argument("--universities", default=_DEFAULT_UNIVERSITIES)
    parser.add_argument("--pages", default=_DEFAULT_PAGES)
    parser.add_argument("--out", default="data/evaluation")
    parser.add_argument("--quiet", action="store_true")
    return parser


def _select(target: str, args) -> List:
    if target == "classification":
        return [evaluate_classification(args.classifications)]
    if target == "universities":
        return [evaluate_universities(args.universities)]
    if target == "pages":
        return [evaluate_page_classification(args.pages)]
    if target == "requirements":
        return [evaluate_requirements()]
    if target == "eligibility":
        return [evaluate_eligibility()]
    metrics = []
    if os.path.exists(args.classifications):
        metrics.append(evaluate_classification(args.classifications))
    if os.path.exists(args.universities):
        metrics.append(evaluate_universities(args.universities))
    if os.path.exists(args.pages):
        metrics.append(evaluate_page_classification(args.pages))
    metrics.append(evaluate_requirements())
    metrics.append(evaluate_eligibility())
    return metrics


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    metrics = _select(args.target, args)
    report = EvaluationReport(
        generated_at=utcnow(),
        evaluation_version=EVALUATION_VERSION,
        metrics=metrics,
        artifacts={
            "classification_gold": dataset_path("classification_gold.jsonl"),
            "university_gold": dataset_path("university_gold.jsonl"),
            "page_classification_gold": dataset_path("page_classification_gold.jsonl"),
            "requirements_gold": dataset_path("requirements_gold.jsonl"),
            "eligibility_gold": dataset_path("eligibility_gold.jsonl"),
        },
    )
    ensure_dir(args.out)
    write_json(os.path.join(args.out, "report.json"), report)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(_markdown(report))

    if not args.quiet:
        for metric in metrics:
            print(f"[EVAL] {metric.name}: n={metric.n} accuracy={metric.accuracy:.3f} macro_f1={metric.macro_f1:.3f}")
            for err in metric.errors[:5]:
                print(f"        ! {err}")
        print(f"[EVAL] wrote {os.path.join(args.out, 'report.json')}")
    return 0


def _markdown(report: EvaluationReport) -> str:
    lines = ["# Evaluation report", "", f"Generated: {report.generated_at}", ""]
    lines.append("| metric | n | accuracy | macro F1 |")
    lines.append("|---|---|---|---|")
    for m in report.metrics:
        lines.append(f"| {m.name} | {m.n} | {m.accuracy:.3f} | {m.macro_f1:.3f} |")
    lines.append("")
    for m in report.metrics:
        if not m.errors:
            continue
        lines.append(f"## {m.name} — errors")
        for err in m.errors:
            lines.append(f"- {err}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
