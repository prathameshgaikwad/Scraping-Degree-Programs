"""Tests for the Phase 2 normalization layer.

    python -m unittest discover -s degreeprograms/normalize/tests -t .
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from degreeprograms.normalize.io import load_alias_registry
from degreeprograms.normalize.models import DegreeType, ProgramFormat, ResolutionMethod
from degreeprograms.normalize.pipeline import NormalizationPipeline, NormalizeConfig
from degreeprograms.normalize.programs import ProgramNormalizer
from degreeprograms.normalize.text import (
    base_university_slug,
    normalize_name,
    parse_degree_type,
    parse_program_format,
    parse_ranking,
    slugify,
    split_multi,
)
from degreeprograms.normalize.universities import UniversityResolver


def _registry():
    return load_alias_registry(NormalizeConfig().alias_registry_path)

WARWICK = {
    "name": "Applied Artificial Intelligence",
    "university_name": "WMG - Warwick Manufacturing Group",
    "campus_name": "WMG, University of Warwick, Coventry, GB",
    "region": "Europe",
    "country": "United Kingdom",
    "city": "Coventry",
    "rankings_position": "=67",
    "program_url": "https://www.topuniversities.com/universities/university-warwick/wmg-warwick-manufacturing-group/postgrad/applied-artificial-intelligence",
    "university_url": "https://www.topuniversities.com/universities/university-warwick/wmg-warwick-manufacturing-group",
    "source_search_url": "https://www.topuniversities.com/pd/endpoint?study_level=[3]&subjects=[4049]",
}

WARWICK_BASE = {
    "name": "Artificial Intelligence",
    "university_name": "University of Warwick",
    "campus_name": "University of Warwick",
    "region": "Europe",
    "country": "United Kingdom",
    "city": "Coventry",
    "rankings_position": "=67",
    "program_url": "https://www.topuniversities.com/universities/university-warwick/postgrad/artificial-intelligence",
    "university_url": "https://www.topuniversities.com/universities/university-warwick",
    "source_search_url": "https://www.topuniversities.com/pd/endpoint?study_level=[3]&subjects=[4049]",
}

MESSY = {
    "name": "Applied Articificial Intelligence (M.Sc.) (Executive Education)",
    "university_name": "Technische Hochschule Ingolstadt",
    "campus_name": "Campus Ingolstadt",
    "region": "Europe, Europe, Europe",
    "country": "Germany, Germany",
    "city": "Ingolstadt",
    "rankings_position": "601-650",
    "program_url": "https://www.topuniversities.com/universities/technische-hochschule-ingolstadt/postgrad/applied-ai",
    "university_url": "https://www.topuniversities.com/universities/technische-hochschule-ingolstadt",
    "source_search_url": "https://www.topuniversities.com/pd/endpoint?study_level=[3]&subjects=[4049]",
}


class TextTests(unittest.TestCase):
    def test_split_multi_dedupes(self):
        self.assertEqual(split_multi("Europe, Europe, Europe"), ["Europe"])
        self.assertEqual(split_multi("United Kingdom, United Kingdom"), ["United Kingdom"])
        self.assertEqual(split_multi(""), [])
        self.assertEqual(split_multi("Sheffield,"), ["Sheffield"])

    def test_slugify_unicode(self):
        self.assertEqual(slugify("Universität Łódź"), "universitat-lodz")
        self.assertEqual(slugify("  A & B / C  "), "a-b-c")

    def test_normalize_name(self):
        self.assertEqual(normalize_name("M.Sc. Artificial-Intelligence"), "m sc artificial intelligence")

    def test_degree_type(self):
        self.assertEqual(parse_degree_type("Applied Artificial Intelligence (M.Sc.) (Executive Education)"), "MSC")
        self.assertEqual(parse_degree_type("Advanced Artificial Intelligence MRes"), "MRES")
        self.assertEqual(parse_degree_type("Data Science and AI MSc"), "MSC")
        self.assertEqual(parse_degree_type("Master of Business Administration"), "MBA")
        self.assertEqual(parse_degree_type("Something Else"), "UNKNOWN")

    def test_program_format(self):
        self.assertEqual(parse_program_format("Applied AI (Executive Education)"), "EXECUTIVE")
        self.assertEqual(parse_program_format("Online MSc Data Science"), "ONLINE")
        self.assertEqual(parse_program_format("Data Science and AI MSc"), "UNKNOWN")

    def test_ranking(self):
        r = parse_ranking("=314")
        self.assertEqual(r["university_rank"], 314)
        self.assertTrue(r["tied"])
        r = parse_ranking("601-650")
        self.assertIsNone(r["university_rank"])
        self.assertTrue(r["is_range"])
        self.assertEqual((r["rank_low"], r["rank_high"]), (601, 650))
        r = parse_ranking("1401+")
        self.assertTrue(r["is_plus"])
        self.assertEqual(r["rank_low"], 1401)
        r = parse_ranking("")
        self.assertIsNone(r["university_rank"])

    def test_base_university_slug(self):
        self.assertEqual(base_university_slug(WARWICK["university_url"]), "university-warwick")
        self.assertEqual(base_university_slug("https://www.topuniversities.com/universities/ucl"), "ucl")
        self.assertIsNone(base_university_slug("https://example.com/x"))


class UniversityTests(unittest.TestCase):
    def test_org_unit_groups_under_parent(self):
        universities, index_map = UniversityResolver(_registry()).resolve([WARWICK, WARWICK_BASE])
        self.assertEqual(len(universities), 1)
        uni = universities[0]
        self.assertEqual(uni.canonical_name, "University of Warwick")
        self.assertEqual(uni.university_id, "university-of-warwick")
        self.assertEqual(uni.official_domain, "warwick.ac.uk")
        self.assertEqual(uni.qs.university_rank, 67)
        aliases = {a.alias for a in uni.aliases}
        self.assertIn("WMG - Warwick Manufacturing Group", aliases)
        self.assertIn("University of Warwick", aliases)
        self.assertEqual(index_map[0], "university-of-warwick")
        self.assertEqual(index_map[1], "university-of-warwick")

    def test_messy_multivalue_country(self):
        universities, _ = UniversityResolver().resolve([MESSY])
        uni = universities[0]
        self.assertEqual(uni.country, "Germany")
        self.assertEqual(uni.canonical_name, "Technische Hochschule Ingolstadt")
        self.assertEqual(uni.qs.rank_display, "601-650")
        self.assertTrue(uni.qs.is_range)


class ProgramTests(unittest.TestCase):
    def test_program_fields_and_dedup(self):
        raw = [WARWICK, WARWICK_BASE]
        _, index_map = UniversityResolver().resolve(raw)
        programs = ProgramNormalizer().normalize(raw, index_map)
        self.assertEqual(len(programs), 2)  # different names -> not merged

        # Exact duplicate should merge.
        raw_dup = [WARWICK, dict(WARWICK)]
        _, index_map2 = UniversityResolver().resolve(raw_dup)
        programs2 = ProgramNormalizer().normalize(raw_dup, index_map2)
        self.assertEqual(len(programs2), 1)
        self.assertEqual(len(programs2[0].merged_sources), 2)

    def test_degree_and_format(self):
        raw = [MESSY]
        _, index_map = UniversityResolver().resolve(raw)
        programs = ProgramNormalizer().normalize(raw, index_map)
        p = programs[0]
        self.assertEqual(p.degree_type, DegreeType.MSC)
        self.assertEqual(p.program_format, ProgramFormat.EXECUTIVE)
        self.assertEqual(p.location.country, "Germany")
        self.assertEqual(p.location.region, "Europe")


class PipelineTests(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "raw.jsonl")
            with open(in_path, "w", encoding="utf-8") as fh:
                for record in (WARWICK, WARWICK_BASE, MESSY):
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_dir = os.path.join(tmp, "out")
            manifest = NormalizationPipeline(
                NormalizeConfig(input_path=in_path, out_dir=out_dir)
            ).run()
            self.assertEqual(manifest.input_rows, 3)
            self.assertEqual(manifest.universities, 2)
            self.assertEqual(manifest.programs, 3)
            self.assertTrue(os.path.exists(os.path.join(out_dir, "universities.jsonl")))
            self.assertTrue(os.path.exists(os.path.join(out_dir, "programs.jsonl")))

            # Idempotent: second run reuses output.
            manifest2 = NormalizationPipeline(
                NormalizeConfig(input_path=in_path, out_dir=out_dir)
            ).run()
            self.assertEqual(manifest2.input_sha256, manifest.input_sha256)
            self.assertEqual(manifest2.generated_at, manifest.generated_at)


if __name__ == "__main__":
    unittest.main()
