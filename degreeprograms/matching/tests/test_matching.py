"""Tests for the Phase 7 eligibility matcher.

    python -m unittest discover -s degreeprograms/matching/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from degreeprograms.matching.matcher import match
from degreeprograms.matching.models import DimensionStatus, EligibilityState
from degreeprograms.matching.pipeline import MatchConfig, MatchPipeline
from degreeprograms.profile.models import ApplicantProfile
from degreeprograms.requirements.models import (
    AcademicRequirements,
    ApplicationInfo,
    Evidence,
    FieldValue,
    FinancialInfo,
    LanguageRequirements,
    Prerequisite,
    ProgramRequirements,
    Tests,
)

EV = Evidence(url="https://example.edu/study/msc-ai/entry-requirements", quote="quote", page_title="Entry", retrieved_at="t")


def fv(value=None, status="KNOWN", evidence=True):
    return FieldValue(value=value, status=status, evidence=[EV] if evidence else [])


def make_requirements(
    degree_level=None,
    accepted=None,
    related=None,
    gpa=None,
    gpa_scale=None,
    ielts=None,
    english_required=True,
    prereqs=None,
    exp_required=None,
    exp_years=None,
):
    from degreeprograms.requirements.models import ExperienceRequirements

    return ProgramRequirements(
        program_id="p1",
        university_id="u1",
        academic_requirements=AcademicRequirements(
            minimum_degree_level=fv(degree_level, "KNOWN" if degree_level else "UNKNOWN", evidence=bool(degree_level)),
            accepted_backgrounds=[fv(a) for a in (accepted or [])],
            related_degree_allowed=fv(related, "KNOWN" if related is not None else "UNKNOWN", evidence=related is not None),
            minimum_gpa=fv(gpa, "KNOWN" if gpa is not None else "UNKNOWN", evidence=gpa is not None),
            minimum_gpa_scale=fv(gpa_scale, "KNOWN" if gpa_scale is not None else "UNKNOWN", evidence=gpa_scale is not None),
        ),
        prerequisites=[Prerequisite(category=c, requirement=c, credits=cr, evidence=[EV]) for c, cr in (prereqs or [])],
        language_requirements=LanguageRequirements(
            english_required=fv(english_required, "KNOWN"),
            ielts=fv(ielts, "KNOWN" if ielts is not None else "NOT_MENTIONED", evidence=ielts is not None),
        ),
        experience=ExperienceRequirements(
            required=fv(exp_required, "KNOWN" if exp_required is not None else "NOT_MENTIONED", evidence=False),
            minimum_years=fv(exp_years, "KNOWN" if exp_years is not None else "UNKNOWN", evidence=False),
        ),
    )


BASE_PROFILE = ApplicantProfile(
    applicant_id="p",
    education=[{"degree": "B.Tech", "field": "Metallurgy", "country": "India", "cgpa": 7.67}],
    experience=[{"title": "Software Engineer", "years": 2, "field": "Software Engineering"}],
    target_fields=["Artificial Intelligence"],
)


class DimensionTests(unittest.TestCase):
    def test_degree_level_pass_and_fail(self):
        a = match(BASE_PROFILE, make_requirements(degree_level="BACHELOR"))
        self.assertEqual(a.dimensions["degree_level"].status, DimensionStatus.PASS)
        # A Master's programme requiring a Master's/Doctorate is unusual -> verify.
        b = match(BASE_PROFILE, make_requirements(degree_level="MASTER"))
        self.assertEqual(b.dimensions["degree_level"].status, DimensionStatus.UNCLEAR)
        # A genuine shortfall (below bachelor) is a hard fail.
        diploma = ApplicantProfile(applicant_id="p", education=[{"degree": "Diploma", "field": "Engineering"}])
        c = match(diploma, make_requirements(degree_level="BACHELOR"))
        self.assertEqual(c.dimensions["degree_level"].status, DimensionStatus.FAIL)
        self.assertEqual(c.state, EligibilityState.NOT_ELIGIBLE)

    def test_degree_level_unclear_when_not_extracted(self):
        a = match(BASE_PROFILE, make_requirements(degree_level=None, english_required=False))
        self.assertEqual(a.dimensions["degree_level"].status, DimensionStatus.UNCLEAR)
        self.assertEqual(a.state, EligibilityState.UNCLEAR)

    def test_english_states(self):
        none = match(BASE_PROFILE, make_requirements(degree_level="BACHELOR", ielts=6.5))
        self.assertEqual(none.dimensions["english"].status, DimensionStatus.UNKNOWN)
        passed = match(
            ApplicantProfile(applicant_id="p", education=[{"degree": "BSc", "field": "CS"}], testing={"ielts": 7.0}),
            make_requirements(degree_level="BACHELOR", ielts=6.5),
        )
        self.assertEqual(passed.dimensions["english"].status, DimensionStatus.PASS)
        failed = match(
            ApplicantProfile(applicant_id="p", education=[{"degree": "BSc", "field": "CS"}], testing={"ielts": 5.0}),
            make_requirements(degree_level="BACHELOR", ielts=6.5),
        )
        self.assertEqual(failed.dimensions["english"].status, DimensionStatus.FAIL)

    def test_gpa_scale_handling(self):
        profile = ApplicantProfile(applicant_id="p", education=[{"degree": "BSc", "field": "CS", "cgpa": 3.5, "cgpa_scale": 4.0}])
        same = match(profile, make_requirements(degree_level="BACHELOR", gpa=3.0, gpa_scale=4.0))
        self.assertEqual(same.dimensions["gpa"].status, DimensionStatus.PASS)
        diff = match(profile, make_requirements(degree_level="BACHELOR", gpa=80, gpa_scale=100))
        self.assertEqual(diff.dimensions["gpa"].status, DimensionStatus.UNCLEAR)
        no_scale = match(BASE_PROFILE, make_requirements(degree_level="BACHELOR", gpa=3.0))
        self.assertEqual(no_scale.dimensions["gpa"].status, DimensionStatus.UNCLEAR)

    def test_prerequisites_gap_vs_unknown(self):
        req = make_requirements(degree_level="BACHELOR", prereqs=[("PROGRAMMING", 15)])
        no_coursework = match(BASE_PROFILE, req)
        self.assertEqual(no_coursework.dimensions["programming"].status, DimensionStatus.UNKNOWN)

        with_coursework = match(
            ApplicantProfile(applicant_id="p", education=[{"degree": "BSc", "field": "CS"}],
                             coursework=[{"name": "Databases", "category": "DATABASES", "credits": 10}]),
            req,
        )
        self.assertEqual(with_coursework.dimensions["programming"].status, DimensionStatus.GAP)
        self.assertEqual(with_coursework.state, EligibilityState.PREREQUISITE_GAP)

    def test_professional_experience_is_not_a_prerequisite(self):
        # 2 years software engineering must NOT satisfy a programming prerequisite.
        req = make_requirements(degree_level="BACHELOR", prereqs=[("PROGRAMMING", 15)])
        a = match(BASE_PROFILE, req)
        self.assertNotEqual(a.dimensions["programming"].status, DimensionStatus.PASS)

    def test_work_experience_dimension(self):
        req = make_requirements(degree_level="BACHELOR", exp_required=True, exp_years=3)
        a = match(BASE_PROFILE, req)  # 2 years
        self.assertEqual(a.dimensions["work_experience"].status, DimensionStatus.FAIL)

    def test_eligible_when_all_pass(self):
        profile = ApplicantProfile(
            applicant_id="p",
            education=[{"degree": "BSc", "field": "Computer Science", "cgpa": 3.5, "cgpa_scale": 4.0}],
            testing={"ielts": 7.0},
            coursework=[{"name": "Programming", "category": "PROGRAMMING", "credits": 20}],
        )
        req = make_requirements(degree_level="BACHELOR", accepted=["Computer Science"], gpa=3.0, gpa_scale=4.0,
                                ielts=6.5, prereqs=[("PROGRAMMING", 15)])
        a = match(profile, req)
        self.assertEqual(a.state, EligibilityState.ELIGIBLE, a.reasons)

    def test_no_probability_or_fit_score(self):
        a = match(BASE_PROFILE, make_requirements(degree_level="BACHELOR"))
        dumped = a.model_dump()
        for forbidden in ("probability", "chance", "fit_score", "score", "rank"):
            self.assertNotIn(forbidden, dumped)
        self.assertIn("dimensions", dumped)
        self.assertIn("state", dumped)

    def test_evidence_attached(self):
        a = match(BASE_PROFILE, make_requirements(degree_level="BACHELOR", ielts=6.5))
        self.assertEqual(a.dimensions["degree_level"].evidence[0].url, EV.url)
        self.assertTrue(a.evidence)


class PipelineTests(unittest.TestCase):
    def _write_fixtures(self, tmp):
        req = make_requirements(degree_level="BACHELOR", accepted=["Computer Science"], related=True, ielts=6.5)
        req.program_id = "p1"
        req_path = os.path.join(tmp, "requirements.jsonl")
        with open(req_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(req.model_dump(mode="json"), ensure_ascii=False) + "\n")
        programs_path = os.path.join(tmp, "programs.jsonl")
        with open(programs_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"program_id": "p1", "university_id": "u1", "name": "MSc AI"}) + "\n")
        unis_path = os.path.join(tmp, "universities.jsonl")
        with open(unis_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"university_id": "u1", "canonical_name": "Example University"}) + "\n")
        profile_path = os.path.join(tmp, "applicant.json")
        with open(profile_path, "w", encoding="utf-8") as fh:
            json.dump({"applicant": {
                "applicant_id": "dev",
                "education": {"degree": "B.Tech", "field": "Metallurgy", "cgpa": 7.67},
                "experience": [{"title": "Software Engineer", "years": 2, "field": "Software Engineering"}],
                "target_fields": ["Artificial Intelligence"],
            }}, fh)
        return req_path, programs_path, unis_path, profile_path

    def test_end_to_end_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            req_path, programs_path, unis_path, profile_path = self._write_fixtures(tmp)
            out_dir = os.path.join(tmp, "out")
            config = MatchConfig(
                profile_path=profile_path,
                requirements_path=req_path,
                programs_path=programs_path,
                universities_path=unis_path,
                out_dir=out_dir,
                use_llm=False,
            )
            manifest = MatchPipeline(config).run()
            self.assertEqual(manifest.programs, 1)
            self.assertEqual(manifest.cache_hits, 0)

            with open(os.path.join(out_dir, "eligibility.jsonl"), encoding="utf-8") as fh:
                row = json.loads(fh.readline())
            self.assertIn(row["state"], {s.value for s in EligibilityState})
            self.assertEqual(row["dimensions"]["degree_level"]["status"], "PASS")
            self.assertEqual(row["dimensions"]["english"]["status"], "UNKNOWN")

            manifest2 = MatchPipeline(config).run()
            self.assertEqual(manifest2.cache_hits, 1)


if __name__ == "__main__":
    unittest.main()
