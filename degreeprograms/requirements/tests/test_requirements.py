"""Tests for the Phase 6 requirements layer.

    python -m unittest discover -s degreeprograms/requirements/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from degreeprograms.intelligence.schema import (
    Fact,
    PageType as IntelPageType,
    ProgramIntelligence,
    Source,
    SourceType,
    StandardizedTest,
    TestScore,
    TestStatus,
)
from degreeprograms.requirements.mapping import build_requirements, infer_degree_level
from degreeprograms.requirements.pipeline import RequirementsConfig, RequirementsPipeline

REQUIREMENTS_TEXT = (
    "Entry requirements: a bachelor's degree in Computer Science or a related field "
    "with a minimum GPA of 3.0 on a 4.0 scale. "
    "English language requirements: IELTS overall 6.5. TOEFL iBT 90. "
    "GRE is not required. "
    "The application deadline is 31 March 2027. "
    "Tuition fees are 20000 GBP per year for international students. "
    "Applicants should have knowledge of programming and mathematics."
)


def _source(source_id="s1"):
    return Source(
        id=source_id,
        url="https://example.edu/study/msc-ai/entry-requirements",
        title="Entry requirements",
        source_type=SourceType.OFFICIAL_UNIVERSITY,
        page_type=IntelPageType.ADMISSION_REQUIREMENTS,
        retrieved_at="2026-09-21T00:00:00Z",
        content_hash="abc",
        tier=1,
    )


class MappingTests(unittest.TestCase):
    def test_values_status_and_evidence(self):
        obj = ProgramIntelligence()
        obj.academic_requirements.background.minimum_degree = Fact.known(
            "undergraduate degree in a relevant field", "s1", "requires an undergraduate degree"
        )
        obj.academic_requirements.performance.minimum_gpa = Fact.known(3.0, "s1", "minimum GPA of 3.0")
        obj.english_requirements.ielts = TestScore(
            required=True, status=TestStatus.REQUIRED, minimum_overall=6.5, source_id="s1", evidence_text="IELTS 6.5"
        )
        obj.gre = StandardizedTest(
            name="GRE", status=TestStatus.NOT_REQUIRED, source_id="s1", evidence_text="GRE is not required"
        )
        obj.fees.tuition.amount = Fact.known(20000.0, "s1", "tuition fees are 20000 GBP")
        obj.fees.tuition.currency = Fact.known("GBP", "s1", "tuition fees are 20000 GBP")

        req = build_requirements("p1", "u1", obj, {"s1": _source()})
        self.assertEqual(req.academic_requirements.minimum_degree_level.value, "BACHELOR")
        self.assertEqual(req.academic_requirements.minimum_degree_level.status, "KNOWN")
        self.assertEqual(req.academic_requirements.minimum_gpa.value, 3.0)
        self.assertEqual(req.language_requirements.ielts.value, 6.5)
        self.assertEqual(req.tests.gre_required.value, "NOT_REQUIRED")
        self.assertEqual(req.financial.tuition.value, 20000.0)
        self.assertEqual(req.financial.currency.value, "GBP")
        ev = req.language_requirements.ielts.evidence[0]
        self.assertEqual(ev.url, "https://example.edu/study/msc-ai/entry-requirements")
        self.assertEqual(ev.page_title, "Entry requirements")
        self.assertTrue(ev.retrieved_at)

    def test_unknown_has_no_evidence(self):
        req = build_requirements("p1", "u1", ProgramIntelligence(), {})
        self.assertEqual(req.academic_requirements.minimum_gpa.status, "UNKNOWN")
        self.assertEqual(req.academic_requirements.minimum_gpa.evidence, [])
        self.assertEqual(req.tests.gre_required.status, "NOT_MENTIONED")
        self.assertFalse(req.completeness.academic)
        self.assertFalse(req.completeness.financial)

    def test_evidence_never_invented_without_source(self):
        obj = ProgramIntelligence()
        obj.fees.tuition.amount = Fact.known(1000.0, "missing", "some text")
        req = build_requirements("p1", "u1", obj, {})
        self.assertEqual(req.financial.tuition.value, 1000.0)
        self.assertEqual(req.financial.tuition.evidence, [])  # no fabricated URL

    def test_degree_level_inference(self):
        self.assertEqual(infer_degree_level("a bachelor's degree"), "BACHELOR")
        self.assertEqual(infer_degree_level("undergraduate degree"), "BACHELOR")
        self.assertEqual(infer_degree_level("master's degree"), "MASTER")
        self.assertIsNone(infer_degree_level("some qualification"))

    def test_conflict_preserved(self):
        obj = ProgramIntelligence()
        obj.fees.tuition.amount = Fact(
            value=6000.0,
            status="CONFLICTING",
            values=[
                {"value": 6000.0, "source": "s1", "evidence": "6,000 per semester"},
                {"value": 3000.0, "source": "s2", "evidence": "3,000 per semester"},
            ],
        )
        sources = {"s1": _source("s1"), "s2": _source("s2")}
        req = build_requirements("p1", "u1", obj, sources)
        self.assertEqual(req.financial.tuition.status, "CONFLICTING")
        self.assertEqual(len(req.financial.tuition.evidence), 2)


class PipelineTests(unittest.TestCase):
    def _write_fixtures(self, tmp):
        pages_path = os.path.join(tmp, "pages.jsonl")
        programs_path = os.path.join(tmp, "programs.jsonl")
        universities_path = os.path.join(tmp, "universities.jsonl")
        with open(pages_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "page_id": "page_1",
                "program_id": "p1",
                "university_id": "u1",
                "program_ids": ["p1"],
                "url": "https://example.edu/study/msc-ai/entry-requirements",
                "final_url": "https://example.edu/study/msc-ai/entry-requirements",
                "title": "Entry requirements",
                "page_type": "REQUIREMENTS_PAGE",
                "crawl_status": "SUCCESS",
                "depth": 1,
                "content_hash": "h1",
                "text": REQUIREMENTS_TEXT,
                "retrieved_at": "2026-09-21T00:00:00Z",
            }) + "\n")
        with open(programs_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "program_id": "p1",
                "university_id": "u1",
                "name": "MSc Artificial Intelligence",
                "location": {"country": "United Kingdom", "city": "London"},
            }) + "\n")
        with open(universities_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"university_id": "u1", "canonical_name": "Example University"}) + "\n")
        return pages_path, programs_path, universities_path

    def test_end_to_end_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages_path, programs_path, universities_path = self._write_fixtures(tmp)
            out_dir = os.path.join(tmp, "out")
            config = RequirementsConfig(
                pages_path=pages_path,
                programs_path=programs_path,
                universities_path=universities_path,
                out_dir=out_dir,
            )
            manifest = RequirementsPipeline(config).run()
            self.assertEqual(manifest.programs, 1)
            self.assertEqual(manifest.pages_considered, 1)
            self.assertEqual(manifest.pages_extracted, 1)
            self.assertEqual(manifest.cache_hits, 0)

            with open(os.path.join(out_dir, "requirements.jsonl"), encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
            req = rows[0]
            self.assertEqual(req["academic_requirements"]["minimum_degree_level"]["value"], "BACHELOR")
            self.assertEqual(req["language_requirements"]["ielts"]["value"], 6.5)
            self.assertEqual(req["language_requirements"]["toefl"]["value"], 90.0)
            self.assertEqual(req["tests"]["gre_required"]["value"], "NOT_REQUIRED")
            self.assertEqual(req["application"]["deadline"]["value"], "2027-03-31")
            self.assertEqual(req["financial"]["tuition"]["value"], 20000.0)
            self.assertTrue(req["sources"])

            # Second run: unchanged pages are served from the extraction cache.
            manifest2 = RequirementsPipeline(config).run()
            self.assertEqual(manifest2.pages_extracted, 0)
            self.assertEqual(manifest2.cache_hits, 1)


if __name__ == "__main__":
    unittest.main()
