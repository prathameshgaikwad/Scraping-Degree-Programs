"""Clean HTML -> text / links / tables extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_DROP_TAGS = ["script", "style", "noscript", "svg", "template", "iframe"]


@dataclass
class Anchor:
    text: str
    href: str


@dataclass
class Table:
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)

    def as_text(self) -> str:
        lines = []
        if self.headers:
            lines.append(" | ".join(self.headers))
        for row in self.rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)


@dataclass
class CleanPage:
    url: str
    title: str = ""
    text: str = ""
    anchors: List[Anchor] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)
    pdf_links: List[str] = field(default_factory=list)
    last_updated: Optional[str] = None


def _clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = _WS_RE.sub(" ", value)
    value = _MULTI_NL_RE.sub("\n\n", value)
    # Collapse single newlines (one element per line) into spaces, but keep
    # blank-line paragraph breaks so sentence detection has real boundaries.
    value = re.sub(r"(?<!\n)\n(?!\n)", " ", value)
    return value.strip()


def _extract_tables(soup: BeautifulSoup) -> List[Table]:
    tables: List[Table] = []
    for table in soup.find_all("table"):
        headers: List[str] = []
        rows: List[List[str]] = []
        header_cells = table.find_all("th")
        if header_cells:
            headers = [_clean_text(c.get_text(" ", strip=True)) for c in header_cells]
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row = [_clean_text(c.get_text(" ", strip=True)) for c in cells]
            if any(row):
                rows.append(row)
        if rows:
            # Drop a duplicated header row.
            if headers and rows and rows[0] == headers:
                rows = rows[1:]
            tables.append(Table(headers=headers, rows=rows))
    return tables


def _extract_last_updated(text: str) -> Optional[str]:
    patterns = [
        r"last (?:updated|modified|reviewed)\s*[:\-]?\s*([A-Za-z0-9 ,/\-]{4,30})",
        r"updated\s*[:\-]\s*([A-Za-z0-9 ,/\-]{4,30})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def parse_html(html: str, base_url: str) -> CleanPage:
    soup = BeautifulSoup(html, "lxml")

    title = ""
    if soup.title and soup.title.string:
        title = _clean_text(soup.title.string)
    h1 = soup.find("h1")
    if h1:
        h1_text = _clean_text(h1.get_text(" ", strip=True))
        if h1_text:
            title = h1_text

    meta: Dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property")
        content = tag.get("content")
        if name and content:
            meta[name.lower()] = _clean_text(content)

    anchors: List[Anchor] = []
    pdf_links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        text = _clean_text(a.get_text(" ", strip=True))
        anchors.append(Anchor(text=text, href=href))
        if href.lower().split("?")[0].endswith(".pdf"):
            pdf_links.append(href)

    body = soup
    for tag_name in _DROP_TAGS:
        for tag in body.find_all(tag_name):
            tag.decompose()
    for tag in soup.find_all(["nav", "header", "footer", "aside"]):
        tag.decompose()

    text = _clean_text(soup.get_text("\n", strip=True))
    tables = _extract_tables(soup)
    last_updated = _extract_last_updated(text)

    return CleanPage(
        url=base_url,
        title=title,
        text=text,
        anchors=anchors,
        tables=tables,
        meta=meta,
        pdf_links=sorted(set(pdf_links)),
        last_updated=last_updated,
    )


def section_text(text: str, keywords: List[str], window: int = 1400) -> str:
    """Return a window of text around the first keyword hit (for evidence)."""
    lowered = text.lower()
    for kw in keywords:
        idx = lowered.find(kw.lower())
        if idx != -1:
            start = max(0, idx - window // 3)
            end = min(len(text), idx + window)
            return text[start:end]
    return ""


def sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def host_of(url: str) -> str:
    return (urlparse(url).netloc or "").lower()


def same_site(a: str, b: str) -> bool:
    """Approximate registrable-domain comparison supporting common ccTLDs."""
    ha, hb = host_of(a), host_of(b)
    if not ha or not hb:
        return False
    if ha == hb:
        return True
    return _registrable(ha) == _registrable(hb)


_MULTI_SUFFIX = {
    "ac.uk", "co.uk", "gov.uk", "org.uk", "ac.jp", "co.jp", "ac.kr", "co.kr",
    "edu.au", "com.au", "ac.nz", "co.nz", "edu.sg", "com.sg", "ac.za", "co.za",
    "edu.hk", "com.hk", "edu.my", "com.my", "ac.in", "edu.in", "co.in",
}


def _registrable(host: str) -> str:
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    suffix2 = ".".join(parts[-2:])
    if suffix2 in _MULTI_SUFFIX and len(parts) >= 3:
        return ".".join(parts[-3:])
    return suffix2


def same_registered_domain(a: str, b: str) -> bool:
    ha, hb = host_of(a), host_of(b)
    return bool(ha and hb) and _registrable(ha) == _registrable(hb)
