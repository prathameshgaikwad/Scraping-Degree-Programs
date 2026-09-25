"""Tests for the pluggable document-parsing layer.

    python -m unittest discover -s degreeprograms/parsing/tests -t .

Parsing is abstracted: the default provider (``null``) extracts nothing, and
the heuristic provider is one optional implementation.
"""

from __future__ import annotations

import unittest

from degreeprograms.parsing import (
    DEFAULT_PROVIDER,
    NullParser,
    get_parser,
    parse_document,
    parsing_enabled,
)
from degreeprograms.profile.models import EducationLevel


class ProviderInterfaceTests(unittest.TestCase):
    def test_default_provider_exists_and_is_null(self):
        self.assertEqual(DEFAULT_PROVIDER, "null")
        self.assertEqual(get_parser().name, "null")

    def test_default_parsing_extracts_nothing(self):
        # The product must not depend on parsing yet.
        self.assertEqual(parse_document("r.txt", b"B.Tech in Computer Science"), {})
        self.assertFalse(parsing_enabled())

    def test_unknown_provider_falls_back_to_null(self):
        self.assertEqual(get_parser("does-not-exist").name, "null")

    def test_null_parser_contract(self):
        self.assertEqual(NullParser().parse("x.txt", b"anything", kind="resume"), {})


class HeuristicProviderTests(unittest.TestCase):
    RESUME = (
        "Priya Sharma\n"
        "priya.sharma@example.com | +91 98765 43210\n\n"
        "EDUCATION\n"
        "B.Tech in Computer Science, Indian Institute of Technology Bombay, 2018 - 2022\n"
        "CGPA: 8.9/10\n\n"
        "EXPERIENCE\n"
        "Machine Learning Engineer, DataWorks, 2022 - Present\n\n"
        "SKILLS\n"
        "Python, TensorFlow, PyTorch, SQL, Docker, AWS, Machine Learning\n\n"
        "IELTS: 7.0\n"
    )
    TRANSCRIPT = "Course: Linear Algebra - A\nCourse: Data Structures - A\nCourse: Machine Learning - A\nCGPA: 8.9/10\n"

    def test_parse_resume_extracts_core_fields(self):
        from degreeprograms.parsing.heuristic import parse_resume

        parsed = parse_resume("resume.txt", self.RESUME.encode("utf-8"))
        self.assertEqual(parsed["name"], "Priya Sharma")
        edu = parsed["education"][0]
        self.assertEqual(edu["degree"], "B.Tech")
        self.assertEqual(edu["field"], "Computer Science")
        self.assertIn("Indian Institute", edu["institution"])
        self.assertEqual(edu["cgpa"], 8.9)
        self.assertEqual(edu["cgpa_scale"], 10.0)
        titles = [e["title"] for e in parsed["experience"]]
        self.assertIn("Machine Learning Engineer", titles)
        self.assertIn("Python", parsed["technical_background"])
        self.assertEqual(parsed["testing"]["ielts"], 7.0)
        self.assertEqual(parsed["metadata"]["email"], "priya.sharma@example.com")

    def test_parse_resume_is_a_valid_profile(self):
        from degreeprograms.parsing.heuristic import parse_resume, parsed_to_profile

        profile = parsed_to_profile(parse_resume("resume.txt", self.RESUME.encode("utf-8")))
        self.assertEqual(profile.highest_degree_level, EducationLevel.BACHELOR)
        self.assertEqual(profile.primary_education.field, "Computer Science")
        self.assertGreater(profile.total_experience_years, 0)

    def test_parse_transcript_extracts_coursework(self):
        from degreeprograms.parsing.heuristic import parse_transcript

        parsed = parse_transcript("transcript.txt", self.TRANSCRIPT.encode("utf-8"))
        names = [c["name"] for c in parsed["coursework"]]
        self.assertTrue(any("Linear Algebra" in n for n in names))
        self.assertTrue(any("Machine Learning" in n for n in names))

    def test_merge_does_not_create_degreeless_duplicate(self):
        from degreeprograms.parsing.heuristic import merge_profile_dicts, parse_resume, parse_transcript
        from degreeprograms.profile.models import ApplicantProfile

        base = parse_resume("resume.txt", self.RESUME.encode("utf-8"))
        incoming = parse_transcript("transcript.txt", self.TRANSCRIPT.encode("utf-8"))
        merged = merge_profile_dicts(base, incoming)
        self.assertEqual(len(merged["education"]), 1)
        self.assertEqual(merged["education"][0]["degree"], "B.Tech")
        self.assertEqual(len(merged["coursework"]), 3)
        ApplicantProfile(**merged)

    def test_extract_text_handles_plain_text(self):
        from degreeprograms.parsing.heuristic import extract_text

        self.assertIn("Priya", extract_text("r.txt", self.RESUME.encode("utf-8")))

    def test_parse_empty_resume_returns_no_inventions(self):
        from degreeprograms.parsing.heuristic import parse_resume

        parsed = parse_resume("empty.txt", b"")
        self.assertNotIn("education", parsed)
        self.assertNotIn("experience", parsed)
        self.assertNotIn("technical_background", parsed)

    def test_heuristic_provider_callable_through_registry(self):
        from degreeprograms.parsing import get_parser

        parser = get_parser("heuristic")
        self.assertEqual(parser.name, "heuristic")
        self.assertTrue(parser.parse("r.txt", self.RESUME.encode("utf-8")).get("name"))


if __name__ == "__main__":
    unittest.main()
