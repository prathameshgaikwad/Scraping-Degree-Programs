"""Page classification for the crawl layer (Section 12).

Uses the cleaned main content from ``degreeprograms.intelligence.html_text``
(navigation/footer already stripped) so classification is not polluted by menus.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from .models import PageType, SourceTier

# (page_type, url keywords, text keywords, weight)
_SIGNATURES: List[Tuple[PageType, List[str], List[str], float]] = [
    (
        PageType.REQUIREMENTS_PAGE,
        ["entry-requirement", "entry_requirement", "entryrequirement", "requirements",
         "eligibility", "admission-requirement", "admission_requirement"],
        ["entry requirements", "entry requirement", "admission requirements",
         "minimum requirement", "eligibility", "english language requirements",
         "academic requirements", "prerequisites"],
        1.1,
    ),
    (
        PageType.ADMISSION_PAGE,
        ["admission", "admissions", "how-to-apply", "howtoapply"],
        ["how to apply", "admission", "admissions", "application process", "apply for"],
        1.0,
    ),
    (
        PageType.TUITION_PAGE,
        ["fee", "fees", "tuition", "cost", "costs", "finance", "pricing"],
        ["tuition fee", "tuition fees", "programme fee", "program fee", "cost of study",
         "fees and funding", "tuition costs"],
        1.0,
    ),
    (
        PageType.APPLICATION_PAGE,
        ["apply", "application", "applications", "apply-now"],
        ["apply now", "application deadline", "application fee", "submit your application",
         "application portal"],
        0.9,
    ),
    (
        PageType.CURRICULUM_PAGE,
        ["curriculum", "modules", "module", "courses", "course-structure",
         "programme-structure", "study-plan", "syllabus", "catalogue", "catalog"],
        ["curriculum", "module catalogue", "course structure", "programme structure",
         "study plan", "compulsory modules", "core modules", "learning outcomes"],
        0.9,
    ),
    (
        PageType.INTERNATIONAL_STUDENTS_PAGE,
        ["international", "overseas", "visa", "country"],
        ["international students", "international applicants", "visa", "country-specific",
         "coming to study"],
        0.8,
    ),
    (
        PageType.SCHOLARSHIP_PAGE,
        ["scholarship", "scholarships", "funding", "financial-aid", "financial_aid",
         "bursar", "grants", "studentship"],
        ["scholarship", "funding", "financial aid", "bursary", "studentship", "grant"],
        0.8,
    ),
    (
        PageType.PROGRAM_PAGE,
        ["programme", "program", "course", "degree", "masters", "msc", "postgrad",
         "postgraduate"],
        ["programme overview", "course details", "about the programme", "study mode",
         "programme aims", "duration of studies", "program overview"],
        0.7,
    ),
]

_IRRELEVANT_URL = re.compile(
    r"(privacy|cookie|login|sign[-_ ]?in|register|facebook|twitter|linkedin|instagram|"
    r"youtube|news|events|alumni|donate|jobs|careers?$|library|sitemap|accessibility|"
    r"newsletter|subscribe|contact-us$|search\?|/search|terms|disclaimer|basket|shop|"
    r"feedback|captcha|webform|/undergraduate|undergraduate-|site-feedback)",
    re.IGNORECASE,
)


def classify_page_type(url: str, title: str, text: str) -> PageType:
    url_l = (url or "").lower()
    title_l = (title or "").lower()
    text_l = (text or "")[:20000].lower()

    if _IRRELEVANT_URL.search(url_l):
        return PageType.IRRELEVANT

    # A bare domain/homepage is a general landing page, not a targeted page.
    from urllib.parse import urlparse

    if urlparse(url or "").path.strip("/") == "":
        return PageType.UNKNOWN

    scores = {}
    for page_type, url_kws, text_kws, weight in _SIGNATURES:
        score = 0.0
        for kw in url_kws:
            if kw in url_l:
                score += 2.0 * weight
        for kw in text_kws:
            if kw in text_l:
                score += 1.0 * weight
        for kw in text_kws:
            if kw in title_l:
                score += 1.5 * weight
        if score:
            scores[page_type] = score

    if not scores:
        return PageType.UNKNOWN
    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    # Require a URL or title signal, or a strong body signal, so homepages and
    # generic pages that merely mention "international"/"fees" stay UNKNOWN.
    if best_score < 1.2:
        return PageType.UNKNOWN
    return best_type


def source_tier_for(page_type: PageType) -> SourceTier:
    return {
        PageType.PROGRAM_PAGE: SourceTier.PROGRAM_PAGE,
        PageType.ADMISSION_PAGE: SourceTier.ADMISSIONS,
        PageType.REQUIREMENTS_PAGE: SourceTier.ADMISSIONS,
        PageType.INTERNATIONAL_STUDENTS_PAGE: SourceTier.INTERNATIONAL,
        PageType.CURRICULUM_PAGE: SourceTier.REGULATIONS,
        PageType.TUITION_PAGE: SourceTier.ADMISSIONS,
        PageType.APPLICATION_PAGE: SourceTier.ADMISSIONS,
        PageType.SCHOLARSHIP_PAGE: SourceTier.AGGREGATOR,
    }.get(page_type, SourceTier.UNKNOWN)
