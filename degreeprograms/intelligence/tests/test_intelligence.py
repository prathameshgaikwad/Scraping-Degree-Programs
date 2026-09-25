"""Deterministic tests for the Program Intelligence layer.

Run from the repository root::

    python -m unittest discover -s degreeprograms/intelligence/tests -v
"""

from __future__ import annotations

import unittest

from degreeprograms.intelligence.dates import parse_date
from degreeprograms.intelligence.discovery import normalize_url, collect_targets, select_worklist
from degreeprograms.intelligence.extract import PageExtractor
from degreeprograms.intelligence.fetch import utcnow
from degreeprograms.intelligence.html_text import parse_html
from degreeprograms.intelligence.merge import Merger, finalize
from degreeprograms.intelligence.pdf_text import _extract_text_from_content
from degreeprograms.intelligence.schema import (
    Fact,
    Intake,
    PageType,
    ProgramIntelligence,
    Source,
    SourceType,
    TestStatus,
    ValueStatus,
)

SYNTHETIC_HTML = """
<html><head><title>MSc Artificial Intelligence - Example University</title></head>
<body>
<h1>MSc Artificial Intelligence</h1>
<p>This one-year full-time programme is taught in English and starts in September 2027.</p>
<p>Tuition fees are EUR 15,000 per year for international students. The application fee is EUR 75.</p>
<p>The application deadline is 31 March 2027. Applications open on 1 October 2026.</p>
<p>Entry requirements: a bachelor's degree in Computer Science or a related field
with a minimum GPA of 3.0 on a 4.0 scale.</p>
<p>IELTS: overall 6.5 with no less than 6.0 in each component. TOEFL iBT 90.
GRE is not required. GMAT is not required.</p>
<p>Applicants should have knowledge of programming, mathematics, data structures and linear algebra.</p>
</body></html>
"""


def _extract():
    page = parse_html(SYNTHETIC_HTML, "https://example.edu/msc-ai")
    source = Source(
        id="src_test",
        url=page.url,
        source_type=SourceType.OFFICIAL_UNIVERSITY,
        page_type=PageType.PROGRAM,
    )
    obj = PageExtractor(source, country_hint="Germany").extract(
        page,
        {"program_name": "Artificial Intelligence", "university": "Example University", "country": "Germany"},
        is_program_page=True,
    )
    base = ProgramIntelligence()
    Merger({source.id: source}).merge(base, obj)
    finalize(base, utcnow())
    return base


class DateTests(unittest.TestCase):
    def test_full_date(self):
        p = parse_date("31 March 2027")
        self.assertEqual(p.normalized, "2027-03-31")
        self.assertEqual(p.month, 3)
        self.assertEqual(p.year, 2027)

    def test_month_year_does_not_fabricate_day(self):
        p = parse_date("March 2027")
        self.assertIsNone(p.normalized)
        self.assertEqual(p.month, 3)
        self.assertEqual(p.year, 2027)
        self.assertEqual(p.precision, "MONTH")

    def test_iso(self):
        self.assertEqual(parse_date("2027-03-31").normalized, "2027-03-31")

    def test_ambiguous_numeric_is_not_guessed(self):
        p = parse_date("03/04/2027")
        self.assertTrue(p.ambiguous)
        self.assertIsNone(p.normalized)

    def test_term(self):
        p = parse_date("winter semester 2027/28")
        self.assertEqual(p.term, "WINTER")
        self.assertEqual(p.year, 2027)


class CurrencyAndScoreTests(unittest.TestCase):
    def test_scores_and_statuses(self):
        obj = _extract()
        self.assertEqual(obj.identity.degree_type.value, "MSc")
        self.assertEqual(obj.duration.value.value, 1.0)
        self.assertEqual(obj.duration.unit.value, "year")
        self.assertEqual(obj.application.opens, "2026-10-01")
        self.assertEqual(obj.application.deadline, "2027-03-31")
        self.assertEqual(obj.fees.application_fee.amount.value, 75.0)
        self.assertEqual(obj.fees.application_fee.currency.value, "EUR")
        self.assertEqual(obj.fees.tuition.amount.value, 15000.0)
        self.assertEqual(obj.fees.tuition.currency.value, "EUR")
        self.assertEqual(obj.fees.tuition.period.value, "per_year")
        self.assertEqual(obj.english_requirements.ielts.minimum_overall, 6.5)
        self.assertEqual(obj.english_requirements.toefl.minimum_total, 90.0)
        self.assertEqual(obj.gre.status, TestStatus.NOT_REQUIRED)
        self.assertEqual(obj.gmat.status, TestStatus.NOT_REQUIRED)
        cats = {p.category for p in obj.prerequisites}
        self.assertIn("PROGRAMMING", cats)
        self.assertIn("COMPUTER_SCIENCE", cats)

    def test_completeness(self):
        obj = _extract()
        self.assertTrue(obj.completeness.identity)
        self.assertTrue(obj.completeness.fees)
        self.assertTrue(obj.completeness.deadlines)
        self.assertTrue(obj.completeness.english_tests)
        self.assertTrue(obj.completeness.gre)


class MergeTests(unittest.TestCase):
    def test_unknown_never_overwrites_known(self):
        merger = Merger({})
        base = ProgramIntelligence()
        base.identity.degree_type = Fact.known("MSc", "s1", "evidence", 0.9)
        incoming = ProgramIntelligence()
        incoming.identity.degree_type = Fact()  # UNKNOWN
        merger.merge(base, incoming)
        self.assertEqual(base.identity.degree_type.value, "MSc")
        self.assertEqual(base.identity.degree_type.status, ValueStatus.KNOWN)

    def test_conflict_is_retained(self):
        merger = Merger({})
        base = ProgramIntelligence()
        base.fees.tuition.amount = Fact.known(6000.0, "s1", "a", 0.8)
        incoming = ProgramIntelligence()
        incoming.fees.tuition.amount = Fact.known(3000.0, "s2", "b", 0.8)
        merger.merge(base, incoming)
        fact = base.fees.tuition.amount
        self.assertEqual(fact.status, ValueStatus.CONFLICTING)
        self.assertEqual(len(fact.values), 2)

    def test_intake_records_deduplicate_and_merge(self):
        merger = Merger({})
        base = ProgramIntelligence()
        base.intakes = [Intake(term="WINTER", source_id="s1")]
        incoming = ProgramIntelligence()
        incoming.intakes = [
            Intake(term="WINTER", application_open_date="01.02.", source_id="s2")
        ]
        merger.merge(base, incoming)
        self.assertEqual(len(base.intakes), 1)
        self.assertEqual(base.intakes[0].application_open_date, "01.02.")


class PdfTests(unittest.TestCase):
    def test_content_stream_text(self):
        stream = b"BT /F1 12 Tf (Hello) Tj T* [(World) -250 (Again)] TJ ET"
        text = _extract_text_from_content(stream)
        self.assertIn("Hello", text)
        self.assertIn("World", text)
        self.assertIn("Again", text)


class DiscoveryTests(unittest.TestCase):
    def test_normalize_url_strips_tracking(self):
        self.assertEqual(
            normalize_url("https://X.edu/a?utm_source=x&b=1#frag"),
            "https://x.edu/a?b=1",
        )

    def test_collect_targets_stays_on_domain_and_scores(self):
        html = """
        <html><body>
        <a href="/study/msc-ai/entry-requirements">Entry requirements</a>
        <a href="/study/msc-ai/tuition-fees">Tuition fees</a>
        <a href="https://evil.example.com/apply">Apply here</a>
        <a href="/privacy">Privacy</a>
        </body></html>
        """
        page = parse_html(html, "https://example.edu/study/msc-ai")
        targets = collect_targets(page, "https://example.edu/study/msc-ai")
        urls = [t.url for t in targets]
        self.assertTrue(any("entry-requirements" in u for u in urls))
        self.assertTrue(any("tuition-fees" in u for u in urls))
        self.assertFalse(any("evil.example.com" in u for u in urls))

    def test_select_worklist_respects_caps(self):
        from degreeprograms.intelligence.discovery import Target

        targets = [Target(url=f"https://e.edu/p{i}", score=5 - i, is_pdf=False) for i in range(10)]
        selected = select_worklist(targets, max_pages=3, max_pdfs=0)
        self.assertLessEqual(len(selected), 3)


if __name__ == "__main__":
    unittest.main()
