"""Tests for the Phase 3 classification layer.

    python -m unittest discover -s degreeprograms/classify/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from degreeprograms.classify.classifier import DeterministicClassifier, needs_llm_review
from degreeprograms.classify.models import ClassificationMethod, Relevance
from degreeprograms.classify.pipeline import ClassificationPipeline, ClassifyConfig

GOLD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "testdata", "classification_gold.jsonl"
)


def _load_gold():
    with open(GOLD_PATH, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.classifier = DeterministicClassifier()

    def test_obvious_ai_is_high(self):
        c = self.classifier.classify("p1", "u1", "MSc Artificial Intelligence")
        self.assertEqual(c.primary_field, "ARTIFICIAL_INTELLIGENCE")
        self.assertEqual(c.relevance, Relevance.HIGH)
        self.assertEqual(c.method, ClassificationMethod.DETERMINISTIC)
        self.assertGreater(c.confidence, 0.8)
        self.assertTrue(c.evidence)

    def test_irrelevant_materials_is_none(self):
        c = self.classifier.classify("p2", "u2", "Master of Science in Materials Science")
        self.assertEqual(c.relevance, Relevance.NONE)
        self.assertEqual(c.primary_field, "UNKNOWN")

    def test_related_field_is_medium(self):
        c = self.classifier.classify("p3", "u3", "MSc Robotics")
        self.assertEqual(c.primary_field, "ROBOTICS")
        self.assertEqual(c.relevance, Relevance.MEDIUM)

    def test_semantic_case_without_literal_ai(self):
        # "Intelligent Autonomous Systems" should not require the literal phrase "AI".
        c = self.classifier.classify("p4", "u4", "Intelligent Autonomous Systems")
        self.assertIn(c.primary_field, {"ROBOTICS", "INTELLIGENT_SYSTEMS"})
        self.assertIn(c.relevance, {Relevance.MEDIUM, Relevance.HIGH})

    def test_needs_llm_review_only_for_ambiguous(self):
        high = self.classifier.classify("p5", "u5", "MSc Data Science")
        none = self.classifier.classify("p6", "u6", "Materials Science")
        low = self.classifier.classify("p7", "u7", "MSc Data")
        self.assertFalse(needs_llm_review(high))
        self.assertFalse(needs_llm_review(none))
        self.assertTrue(needs_llm_review(low))


class GoldSetTests(unittest.TestCase):
    def test_gold_accuracy(self):
        classifier = DeterministicClassifier()
        gold = _load_gold()
        relevance_correct = 0
        primary_correct = 0
        failures = []
        for item in gold:
            c = classifier.classify("p", "u", item["name"])
            if c.relevance.value == item["expected_relevance"]:
                relevance_correct += 1
            else:
                failures.append(
                    f"{item['name']!r}: relevance {c.relevance.value} != {item['expected_relevance']}"
                )
            if c.primary_field == item["expected_primary"]:
                primary_correct += 1
            else:
                failures.append(
                    f"{item['name']!r}: primary {c.primary_field} != {item['expected_primary']}"
                )
        total = len(gold)
        relevance_acc = relevance_correct / total
        primary_acc = primary_correct / total
        message = f"relevance_acc={relevance_acc:.3f} primary_acc={primary_acc:.3f}\n" + "\n".join(failures)
        self.assertGreaterEqual(relevance_acc, 0.9, message)
        self.assertGreaterEqual(primary_acc, 0.85, message)


class PipelineTests(unittest.TestCase):
    def _write_programs(self, path):
        programs = [
            {
                "program_id": "u1__ai",
                "university_id": "u1",
                "name": "MSc Artificial Intelligence",
                "normalized_name": "msc artificial intelligence",
            },
            {
                "program_id": "u1__materials",
                "university_id": "u1",
                "name": "MSc Materials Science",
                "normalized_name": "msc materials science",
            },
        ]
        with open(path, "w", encoding="utf-8") as fh:
            for p in programs:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    def test_end_to_end_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            programs_path = os.path.join(tmp, "programs.jsonl")
            self._write_programs(programs_path)
            out_dir = os.path.join(tmp, "out")

            manifest = ClassificationPipeline(
                ClassifyConfig(programs_path=programs_path, out_dir=out_dir, use_llm=False)
            ).run()
            self.assertEqual(manifest.programs, 2)
            self.assertEqual(manifest.by_relevance.get("HIGH"), 1)
            self.assertEqual(manifest.by_relevance.get("NONE"), 1)

            with open(os.path.join(out_dir, "classifications.jsonl"), encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
            self.assertEqual(len(rows), 2)

            # Idempotent: unchanged input reuses the manifest.
            manifest2 = ClassificationPipeline(
                ClassifyConfig(programs_path=programs_path, out_dir=out_dir, use_llm=False)
            ).run()
            self.assertEqual(manifest2.generated_at, manifest.generated_at)


if __name__ == "__main__":
    unittest.main()
