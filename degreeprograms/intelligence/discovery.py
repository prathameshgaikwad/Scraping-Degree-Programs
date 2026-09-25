"""Targeted multi-page discovery.

Given a program page (and later, the best linked pages), score same-site links
by information value and return a capped, de-duplicated work list. This maps to
Section 63 and Section 73 of the specification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .classify import classify_page, link_score
from .html_text import CleanPage, same_registered_domain
from .schema import PageType

_TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "mc_cid", "mc_eid", "_ga")
_NOISE_EXT = re.compile(
    r"\.(jpg|jpeg|png|gif|svg|webp|css|js|ico|woff2?|ttf|eot|mp4|mp3|zip|docx?|xlsx?|pptx?)$",
    re.IGNORECASE,
)
_PDF_RE = re.compile(r"\.pdf$", re.IGNORECASE)


@dataclass
class Target:
    url: str
    score: float
    is_pdf: bool
    predicted_page_type: PageType = PageType.OTHER
    anchor_text: str = ""
    from_url: str = ""
    reasons: List[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parsed.path or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query),
            "",
        )
    )


def _predict_page_type(anchor_text: str, href: str) -> PageType:
    return classify_page(href, anchor_text, anchor_text)


def collect_targets(
    page: CleanPage,
    allowed_reference_url: str,
    min_score: float = 1.2,
    include_pdfs: bool = True,
) -> List[Target]:
    targets: List[Target] = []
    seen: Set[str] = set()

    candidates = [(a.text, a.href) for a in page.anchors]
    if include_pdfs:
        candidates.extend([("", pdf) for pdf in page.pdf_links])

    for anchor_text, href in candidates:
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        if _NOISE_EXT.search(urlparse(href).path):
            continue
        if not same_registered_domain(href, allowed_reference_url):
            continue
        norm = normalize_url(href)
        if norm in seen:
            continue
        seen.add(norm)

        is_pdf = bool(_PDF_RE.search(urlparse(norm).path))
        score = link_score(anchor_text, norm)
        if not is_pdf:
            predicted = _predict_page_type(anchor_text, norm)
            if predicted != PageType.OTHER:
                score += 1.0
        if score < min_score:
            continue
        targets.append(
            Target(
                url=norm,
                score=round(score, 3),
                is_pdf=is_pdf,
                predicted_page_type=PageType.OTHER
                if is_pdf
                else _predict_page_type(anchor_text, norm),
                anchor_text=anchor_text,
                from_url=page.url,
            )
        )
    targets.sort(key=lambda t: t.score, reverse=True)
    return targets


def select_worklist(
    targets: Iterable[Target],
    max_pages: int,
    max_pdfs: int,
    exclude_urls: Iterable[str] = (),
) -> List[Target]:
    excluded = {normalize_url(u) for u in exclude_urls}
    selected: List[Target] = []
    pages = 0
    pdfs = 0
    best_by_type: Dict[PageType, Target] = {}
    remaining: List[Target] = []

    for target in targets:
        if target.url in excluded or any(t.url == target.url for t in selected):
            continue
        if target.is_pdf:
            if pdfs >= max_pdfs:
                continue
        else:
            if pages >= max_pages:
                continue
        # Keep at most one strong page per predicted type, then fill by score.
        if not target.is_pdf and target.predicted_page_type != PageType.OTHER:
            if target.predicted_page_type not in best_by_type:
                best_by_type[target.predicted_page_type] = target
                selected.append(target)
                pages += 1
                continue
            remaining.append(target)
            continue
        selected.append(target)
        if target.is_pdf:
            pdfs += 1
        else:
            pages += 1

    for target in remaining:
        if pages >= max_pages:
            break
        selected.append(target)
        pages += 1

    selected.sort(key=lambda t: t.score, reverse=True)
    return selected
