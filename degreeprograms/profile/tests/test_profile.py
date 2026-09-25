"""Tests for the Phase 4 applicant profile layer.

    python -m unittest discover -s degreeprograms/profile/tests -t .
"""

from __future__ import annotations

import os
import unittest

from pydantic import ValidationError

from degreeprograms.profile.loading import load_profile, load_profile_dict
from degreeprograms.profile.models import (
    ApplicantProfile,
    Coursework,
    CourseworkCategory,
    Education,
    EducationLevel,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "testdata")
YAML_PATH = os.path.join(DATA_DIR, "applicant.example.yaml")
JSON_PATH = os.path.join(DATA_DIR, "applicant.example.json")


class LoadingTests(unittest.TestCase):
    def test_load_yaml_example(self):
        profile = load_profile(YAML_PATH)
        self.assertEqual(profile.applicant_id, "dev-applicant")
        primary = profile.primary_education
        self.assertIsNotNone(primary)
        self.assertEqual(primary.degree, "B.Tech")
        self.assertEqual(primary.degree_level, EducationLevel.BACHELOR)
        self.assertEqual(primary.field, "Metallurgy")
        self.assertEqual(primary.field_category, CourseworkCategory.ENGINEERING)
        self.assertEqual(primary.institution, "COEP")
        self.assertEqual(primary.cgpa, 7.67)
        self.assertIsNone(primary.cgpa_scale)  # must not assume a scale
        self.assertEqual(profile.total_experience_years, 2.0)
        self.assertEqual(profile.highest_degree_level, EducationLevel.BACHELOR)
        self.assertEqual(len(profile.technical_background), 6)

    def test_target_field_codes(self):
        profile = load_profile(YAML_PATH)
        self.assertEqual(
            profile.target_field_codes,
            ["ARTIFICIAL_INTELLIGENCE", "MACHINE_LEARNING", "COMPUTER_SCIENCE", "DATA_SCIENCE"],
        )

    def test_no_invented_coursework(self):
        profile = load_profile(YAML_PATH)
        self.assertEqual(profile.coursework, [])
        empty = ApplicantProfile()
        self.assertEqual(empty.coursework, [])
        self.assertIsNone(empty.testing.ielts)
        self.assertIsNone(empty.testing.gre)

    def test_json_and_yaml_equivalent(self):
        yaml_profile = load_profile(YAML_PATH)
        json_profile = load_profile(JSON_PATH)
        self.assertEqual(
            yaml_profile.model_dump(mode="json"), json_profile.model_dump(mode="json")
        )

    def test_single_education_dict_is_accepted(self):
        profile = load_profile_dict(
            {"applicant": {"applicant_id": "x", "education": {"degree": "MSc", "field": "Computer Science"}}}
        )
        self.assertEqual(len(profile.education), 1)
        self.assertEqual(profile.education[0].degree_level, EducationLevel.MASTER)
        self.assertEqual(profile.education[0].field_category, CourseworkCategory.COMPUTER_SCIENCE)


class SubstitutionTests(unittest.TestCase):
    """Another applicant must work without changing the engine."""

    def test_second_applicant(self):
        profile = load_profile_dict(
            {
                "applicant": {
                    "applicant_id": "applicant-2",
                    "education": [
                        {"degree": "BSc", "field": "Physics", "country": "Nigeria", "cgpa": 3.5, "cgpa_scale": 4.0},
                        {"degree": "MSc", "field": "Data Science", "country": "Germany"},
                    ],
                    "experience": [],
                    "target_fields": ["Data Science", "Robotics"],
                    "coursework": [
                        {"name": "Linear Algebra", "credits": 6, "credit_system": "ECTS"},
                        {"name": "Introduction to Programming", "category": "PROGRAMMING"},
                    ],
                }
            }
        )
        self.assertEqual(profile.highest_degree_level, EducationLevel.MASTER)
        self.assertEqual(profile.total_experience_years, 0.0)
        self.assertEqual(profile.target_field_codes, ["DATA_SCIENCE", "ROBOTICS"])
        self.assertEqual(profile.coursework[0].category, CourseworkCategory.LINEAR_ALGEBRA)
        self.assertEqual(profile.coursework[1].category, CourseworkCategory.PROGRAMMING)


class ValidationTests(unittest.TestCase):
    def test_negative_cgpa_rejected(self):
        with self.assertRaises(ValidationError):
            Education(degree="BSc", cgpa=-1)

    def test_cgpa_exceeding_scale_rejected(self):
        with self.assertRaises(ValidationError):
            Education(degree="BSc", cgpa=4.5, cgpa_scale=4.0)

    def test_negative_years_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicantProfile(experience=[{"title": "Engineer", "years": -1}])

    def test_ielts_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicantProfile(testing={"ielts": 12})

    def test_coursework_category_inference(self):
        self.assertEqual(Coursework(name="Linear Algebra").category, CourseworkCategory.LINEAR_ALGEBRA)
        self.assertEqual(
            Coursework(name="Databases", category=CourseworkCategory.DATABASES).category,
            CourseworkCategory.DATABASES,
        )


if __name__ == "__main__":
    unittest.main()
