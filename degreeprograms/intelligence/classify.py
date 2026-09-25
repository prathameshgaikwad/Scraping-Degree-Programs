"""Page classification and link-relevance scoring."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .schema import PageType

# Ordered list of (page_type, url keywords, text keywords, weight).
PAGE_SIGNATURES: List[Tuple[PageType, List[str], List[str], float]] = [
    (
        PageType.ADMISSION_REQUIREMENTS,
        ["admission", "entry-requirement", "entry_requirement", "requirements", "eligibility", "how-to-apply", "howtoapply"],
        ["entry requirements", "admission requirements", "minimum requirement", "entry requirement", "eligibility"],
        1.0,
    ),
    (
        PageType.APPLICATION,
        ["apply", "application", "applications", "admission"],
        ["how to apply", "application process", "apply now", "submit your application"],
        0.95,
    ),
    (
        PageType.FEES,
        ["fee", "fees", "tuition", "cost", "costs", "finance", "pricing"],
        ["tuition fee", "tuition fees", "programme fee", "program fee", "cost of study", "fees and funding"],
        1.0,
    ),
    (
        PageType.FUNDING,
        ["funding", "scholarship", "scholarships", "financial-aid", "financial_aid", "bursaries", "grants"],
        ["scholarship", "funding", "financial aid", "bursary", "studentship"],
        0.8,
    ),
    (
        PageType.CURRICULUM,
        ["curriculum", "modules", "module", "courses", "course-structure", "programme-structure", "study-plan", "syllabus", "catalogue", "catalog"],
        ["curriculum", "module catalogue", "course structure", "programme structure", "study plan", "compulsory modules", "core modules"],
        0.85,
    ),
    (
        PageType.HANDBOOK,
        ["handbook", "prospectus", "regulations", "manual", "guide"],
        ["handbook", "prospectus", "academic regulations", "programme handbook"],
        0.6,
    ),
    (
        PageType.INTERNATIONAL,
        ["international", "visa", "country", "overseas", "eu", "non-eu"],
        ["international students", "visa", "international applicants", "country-specific"],
        0.75,
    ),
    (
        PageType.CONTACT,
        ["contact", "enquir", "advis"],
        ["contact us", "programme contact", "admissions office"],
        0.4,
    ),
]

# Keywords that make a discovered link worth following (Section 63).
LINK_KEYWORDS: Dict[str, float] = {
    "admission": 3.0, "admissions": 3.0, "apply": 2.5, "application": 2.5,
    "requirements": 3.0, "eligibility": 2.8, "entry": 2.5, "international": 2.0,
    "fees": 3.0, "fee": 2.8, "tuition": 3.2, "cost": 2.0, "funding": 1.8,
    "scholarship": 1.8, "curriculum": 2.2, "modules": 2.2, "courses": 1.8,
    "handbook": 1.8, "prospectus": 1.6, "deadline": 2.6, "dates": 1.8,
    "intake": 2.4, "semester": 1.5, "calendar": 1.4, "programme": 1.0,
    "graduate": 1.2, "entry-requirements": 3.0, "how-to-apply": 3.2,
    "study": 0.6, "requirements-and": 2.5, "language": 1.4, "english": 1.4,
    "tests": 1.2, "interview": 1.2, "portfolio": 1.0,
}

_NEGATIVE_LINK = re.compile(
    r"(privacy|cookie|login|sign[-_ ]?in|facebook|twitter|linkedin|instagram|youtube|"
    r"news|events|alumni|donate|jobs|careers$|library|sitemap|accessibility|"
    r"newsletter|subscribe|contact-us$)",
    re.IGNORECASE,
)


def classify_page(url: str, title: str, text: str) -> PageType:
    url_l = (url or "").lower()
    title_l = (title or "").lower()
    text_l = (text or "")[:20000].lower()
    scores: Dict[PageType, float] = {}
    for page_type, url_kws, text_kws, weight in PAGE_SIGNATURES:
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
        return PageType.OTHER
    return max(scores.items(), key=lambda kv: kv[1])[0]


def link_score(anchor_text: str, href: str) -> float:
    href_l = (href or "").lower()
    text_l = (anchor_text or "").lower()
    if _NEGATIVE_LINK.search(href_l) and not any(
        k in href_l for k in ("admission", "fee", "tuition", "apply", "curriculum")
    ):
        return -5.0
    score = 0.0
    for kw, weight in LINK_KEYWORDS.items():
        if kw in href_l:
            score += weight
        if kw in text_l:
            score += weight * 0.6
    if href_l.endswith(".pdf"):
        score += 1.0
    if text_l and len(text_l) > 120:
        score -= 1.0
    return score
