"""Tests for the Phase 8 evaluation layer.

    python -m unittest discover -s degreeprograms/evaluation/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from degreeprograms.evaluation.cli import main as evaluate_main
from degreeprograms.evaluation.metrics import compute_metric
from degreeprograms.evaluation.runners import (
    evaluate_classification,
    evaluate_eligibility,
    evaluate_page_classification,
    evaluate_requirements,
    evaluate_universities,
)


class MetricTests(unittest.TestCase):
    def test_accuracy_and_per_class(self):
        pairs = [("A", "A"), ("A", "B"), ("B", "B"), ("B", "B")]
        metric = compute_metric("t", pairs)
        self.assertEqual(metric.n, 4)
        self.assertEqual(metric.accuracy, 0.75)
        # A: tp=1 fp=0 fn=1 -> recall 0.5 ; B: tp=2 fp=1 fn=0
        self.assertEqual(metric.per_class["A"].recall, 0.5)
        self.assertEqual(metric.per_class["B"].precision, round(2 / 3, 4))
        self.assertEqual(metric.confusion["A"], {"A": 1, "B": 1})

    def test_perfect(self):
        metric = compute_metric("t", [("X", "X"), ("Y", "Y")])
        self.assertEqual(metric.accuracy, 1.0)
        self.assertEqual(metric.macro_f1, 1.0)


class GoldTests(unittest.TestCase):
    """Lock the bundled gold accuracy so regressions are caught."""

    def test_requirements_gold(self):
        metric = evaluate_requirements()
        self.assertGreaterEqual(metric.accuracy, 0.95, metric.errors)

    def test_eligibility_gold(self):
        metric = evaluate_eligibility()
        self.assertGreaterEqual(metric.accuracy, 0.9, metric.errors)


class FixtureTests(unittest.TestCase):
    def test_classification_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            classifications = os.path.join(tmp, "c.jsonl")
            gold = os.path.join(tmp, "g.jsonl")
            with open(classifications, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"normalized_name": "msc artificial intelligence",
                                     "primary_field": "ARTIFICIAL_INTELLIGENCE", "relevance": "HIGH"}) + "\n")
                fh.write(json.dumps({"normalized_name": "msc materials science",
                                     "primary_field": "UNKNOWN", "relevance": "NONE"}) + "\n")
            with open(gold, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"name": "MSc Artificial Intelligence",
                                     "expected_primary": "ARTIFICIAL_INTELLIGENCE", "expected_relevance": "HIGH"}) + "\n")
                fh.write(json.dumps({"name": "MSc Materials Science",
                                     "expected_primary": "UNKNOWN", "expected_relevance": "NONE"}) + "\n")
            metric = evaluate_classification(classifications, gold)
            self.assertEqual(metric.accuracy, 1.0)

    def test_university_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            unis = os.path.join(tmp, "u.jsonl")
            gold = os.path.join(tmp, "g.jsonl")
            with open(unis, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"university_id": "university-of-warwick",
                                     "canonical_name": "University of Warwick",
                                     "aliases": [{"alias": "WMG - Warwick Manufacturing Group"}]}) + "\n")
            with open(gold, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"raw": "WMG - Warwick Manufacturing Group",
                                     "expected_canonical": "University of Warwick"}) + "\n")
            metric = evaluate_universities(unis, gold)
            self.assertEqual(metric.accuracy, 1.0)

    def test_page_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = os.path.join(tmp, "p.jsonl")
            gold = os.path.join(tmp, "g.jsonl")
            with open(pages, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"url": "https://x.edu/tuition-fees?q=1", "page_type": "TUITION_PAGE"}) + "\n")
            with open(gold, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"url": "https://x.edu/tuition-fees", "expected": "TUITION_PAGE"}) + "\n")
            metric = evaluate_page_classification(pages, gold)
            self.assertEqual(metric.accuracy, 1.0)


class CliTests(unittest.TestCase):
    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = evaluate_main(["requirements", "--out", tmp, "--quiet"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "report.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "report.md")))


if __name__ == "__main__":
    unittest.main()
