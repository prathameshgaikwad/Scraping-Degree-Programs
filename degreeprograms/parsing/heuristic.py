"""Resume / transcript parsing into an applicant profile (Phase 4 extension).

Extracts structured fields from a resume or transcript (PDF, DOCX, or plain
text) so the applicant can upload a document instead of typing everything.

Design rules:
* Evidence over guessing: every extracted value is a best-effort parse of text
  that was actually present; unknown stays missing.
* The result is only a *starting point* — the UI lets the applicant edit every
  field, and the profile is re-validated by the normal schema afterwards.
* No network calls; parsing is local and deterministic.
"""

from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

from ..intelligence.pdf_text import extract_pdf_pages
from ..normalize.text import normalize_name
from ..profile.models import ApplicantProfile, infer_education_level, infer_field_category

# -- text extraction ---------------------------------------------------------
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_CGPA_RE = re.compile(
    r"(?:c\.?g\.?p\.?a\.?|gpa)[^0-9]{0,12}(\d{1,3}(?:\.\d{1,2})?)\s*(?:/\s*(\d{1,3}(?:\.\d{1,2})?))?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d{1,2})?)\s*%")

_IELTS_RE = re.compile(r"ielts[^0-9]{0,12}(\d(?:\.\d)?)", re.IGNORECASE)
_TOEFL_RE = re.compile(r"toefl[^0-9]{0,12}(\d{2,3})", re.IGNORECASE)
_GRE_RE = re.compile(r"\bgre\b[^0-9]{0,12}(\d{3})", re.IGNORECASE)
_GMAT_RE = re.compile(r"\bgmat\b[^0-9]{0,12}(\d{3})", re.IGNORECASE)
_PTE_RE = re.compile(r"\bpte\b[^0-9]{0,12}(\d{2,3})", re.IGNORECASE)
_DUOLINGO_RE = re.compile(r"duolingo[^0-9]{0,12}(\d{2,3})", re.IGNORECASE)

_DEGREE_KEYWORDS = [
    "b.tech", "btech", "b.e", "be ", "b.sc", "bsc", "b.a", "ba ", "b.com", "bcom",
    "bachelor", "m.tech", "mtech", "m.sc", "msc", "m.a", "ma ", "mba", "master",
    "m.eng", "meng", "m.s", "ph.d", "phd", "doctorate", "diploma",
]

_FIELD_KEYWORDS = {
    "computer science": "Computer Science",
    "computing": "Computer Science",
    "software engineering": "Software Engineering",
    "information technology": "Information Technology",
    "artificial intelligence": "Artificial Intelligence",
    "machine learning": "Machine Learning",
    "data science": "Data Science",
    "data analytics": "Data Analytics",
    "metallurgy": "Metallurgy",
    "metallurgical": "Metallurgy",
    "materials": "Materials Science",
    "mechanical": "Mechanical Engineering",
    "electrical": "Electrical Engineering",
    "electronics": "Electronics Engineering",
    "civil": "Civil Engineering",
    "chemical": "Chemical Engineering",
    "mathematics": "Mathematics",
    "statistics": "Statistics",
    "physics": "Physics",
    "economics": "Economics",
    "business": "Business",
    "finance": "Finance",
}

_SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "r",
    "sql", "mysql", "postgresql", "mongodb", "redis", "spark", "hadoop", "kafka",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "machine learning", "deep learning", "nlp", "computer vision",
    "docker", "kubernetes", "aws", "azure", "gcp", "git", "linux",
    "spring boot", "django", "flask", "react", "node.js", "rest apis",
    "microservices", "data structures", "algorithms", "statistics",
]

_SECTION_HEADERS = [
    "experience", "work experience", "professional experience", "employment",
    "education", "academics", "projects", "skills", "technical skills",
    "certifications", "coursework", "publications", "awards",
]

_TITLE_RE = re.compile(
    r"\b(engineer|developer|analyst|scientist|manager|consultant|intern|architect|"
    r"researcher|associate|specialist|lead|director|administrator)\b",
    re.IGNORECASE,
)


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from a resume/transcript file (PDF, DOCX, or text)."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(".docx"):
        return _extract_docx(data)
    # .txt, .md, .json, or unknown: decode as text.
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "ignore")


def _extract_pdf(data: bytes) -> str:
    try:
        pages = extract_pdf_pages(data)
        text = "\n".join(p.get("text") or "" for p in pages)
        if text.strip():
            return text
    except Exception:
        pass
    return ""


def _extract_docx(data: bytes) -> str:
    """DOCX is a zip of XML; pull text out of word/document.xml without deps."""
    try:
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.endswith("document.xml")]
            if not names:
                return ""
            xml = zf.read(names[0]).decode("utf-8", "ignore")
        # Paragraph and line breaks become newlines; tags stripped.
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:br\s*/?>", "\n", xml)
        xml = re.sub(r"<[^>]+>", "", xml)
        return _unescape_xml(xml)
    except Exception:
        return ""


def _unescape_xml(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )


# -- field parsing -----------------------------------------------------------
def _lines(text: str) -> List[str]:
    return [ln.strip() for ln in re.split(r"[\r\n]+", text or "") if ln.strip()]


def _find_name(lines: List[str], text: str) -> Optional[str]:
    email = _EMAIL_RE.search(text)
    for line in lines[:6]:
        low = line.lower()
        if email and email.group(0).lower() in low:
            continue
        if any(h in low for h in _SECTION_HEADERS):
            continue
        if _PHONE_RE.fullmatch(line.strip()):
            continue
        words = line.split()
        if 1 < len(words) <= 4 and not any(ch.isdigit() for ch in line) and len(line) <= 48:
            if line == line.title() or line.isupper():
                return line.title() if line.isupper() else line
    return None


def _find_field(text: str) -> Optional[str]:
    low = text.lower()
    for keyword, label in _FIELD_KEYWORDS.items():
        if keyword in low:
            return label
    return None


def _find_degree(lines: List[str], text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (degree, institution) from education-ish lines."""
    degree = None
    institution = None
    for line in lines:
        low = line.lower()
        if degree is None and any(k in low for k in _DEGREE_KEYWORDS):
            # Prefer a compact degree phrase, not a whole sentence.
            match = re.search(
                r"((?:b|m)\.?\s?(?:tech|sc|a|e|s|com|eng)|bachelor[^,|;]{0,30}|master[^,|;]{0,30}|"
                r"mba|ph\.?d|doctorate|diploma)[^,|;|]{0,40}",
                low,
            )
            if match:
                degree = match.group(1).strip().title()
                if len(degree) < 3:
                    degree = None
    # Institution: the name of an org, not the whole degree line.
    for line in lines:
        match = re.search(
            r"([A-Z][A-Za-z&.'\-]*(?:\s+(?:of|at|for|and|the|de))?"
            r"(?:\s+[A-Z][A-Za-z&.'\-]*)*"
            r"\s+(?:University|College|Institute|School|Academy)"
            r"(?:\s+(?:of|at|for|and|the)?\s*[A-Z][A-Za-z&.'\-]*)*)",
            line,
        )
        if match:
            institution = re.sub(r"\s+", " ", match.group(1)).strip(" ,-–—|")
            break
        if re.search(r"university|college|institute|school|academy", line, re.IGNORECASE):
            # Fallback: strip a leading degree phrase and trailing years.
            cleaned = re.sub(r"^.*?\b(?:b|m)\.?\s?(?:tech|sc|a|e|s|com|eng|ba|bsc)\b[^,]*,\s*", "", line, flags=re.IGNORECASE)
            cleaned = re.sub(r"\b(19|20)\d{2}\b.*$", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-–—|")
            if cleaned:
                institution = cleaned
                break
    return degree, institution


def _find_cgpa(text: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    cgpa = scale = percentage = None
    m = _CGPA_RE.search(text)
    if m:
        try:
            cgpa = float(m.group(1))
            if m.group(2):
                scale = float(m.group(2))
        except ValueError:
            pass
    if cgpa is None:
        p = _PERCENT_RE.search(text)
        if p:
            percentage = float(p.group(1))
    return cgpa, scale, percentage


def _find_experience(lines: List[str], text: str) -> List[dict]:
    """Find job entries: a title line near a year or 'present'."""
    out: List[dict] = []
    seen_titles = set()
    for i, line in enumerate(lines):
        if not _TITLE_RE.search(line) or len(line) > 90:
            continue
        title = line.strip(" -–—|,")
        # Keep the job title itself; drop trailing company/dates.
        title = re.split(r"\s*[,|·–—]\s*|\s{2,}", title)[0].strip()
        key = title.lower()
        if key in seen_titles:
            continue
        # years: look on this line and the next two
        window = " ".join(lines[i : i + 3])
        years = _extract_years(window)
        entry = {"title": title}
        if years is not None:
            entry["years"] = years
        seen_titles.add(key)
        out.append(entry)
        if len(out) >= 6:
            break
    return out


def _extract_years(window: str) -> Optional[float]:
    years_full = [int(m.group(0)) for m in _YEAR_RE.finditer(window)]
    if "present" in window.lower() or "current" in window.lower():
        if years_full:
            import datetime

            end = datetime.date.today().year
            start = min(years_full)
            return float(max(0, end - start))
    if len(years_full) >= 2:
        return float(max(0, max(years_full) - min(years_full)))
    return None


def _find_skills(text: str) -> List[str]:
    low = text.lower()
    out: List[str] = []
    for skill in _SKILL_KEYWORDS:
        if re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", low):
            label = skill.title() if len(skill) > 3 else skill.upper()
            if label not in out:
                out.append(label)
    return out[:25]


def _find_testing(text: str) -> Dict[str, float]:
    testing: Dict[str, float] = {}
    for key, pattern in (
        ("ielts", _IELTS_RE),
        ("toefl", _TOEFL_RE),
        ("gre", _GRE_RE),
        ("gmat", _GMAT_RE),
        ("pte", _PTE_RE),
        ("duolingo", _DUOLINGO_RE),
    ):
        m = pattern.search(text)
        if m:
            try:
                testing[key] = float(m.group(1))
            except ValueError:
                pass
    return testing


def _find_coursework(lines: List[str]) -> List[dict]:
    """Pull course-like lines (a transcript often lists course names + grades)."""
    out: List[dict] = []
    for line in lines:
        if not re.search(r"\b(course|module|subject)\b", line, re.IGNORECASE):
            continue
        name = re.sub(r"^\s*(course|module|subject)\s*[:\-]\s*", "", line, flags=re.IGNORECASE)
        name = re.sub(r"\s+", " ", name).strip(" -–—|,")
        if 3 <= len(name) <= 90:
            out.append({"name": name})
        if len(out) >= 30:
            break
    return out


def parse_resume(filename: str, data: bytes) -> dict:
    """Parse a resume/transcript into a partial applicant-profile dict.

    The returned dict is intended to be merged into (and then edited in) the UI.
    Only fields actually found are present.
    """
    text = extract_text(filename, data)
    lines = _lines(text)

    degree, institution = _find_degree(lines, text)
    cgpa, scale, percentage = _find_cgpa(text)
    field = _find_field(text)

    education: List[dict] = []
    if degree or institution or field or cgpa is not None:
        edu: dict = {}
        if degree:
            edu["degree"] = degree
        elif field:
            # No explicit degree keyword; leave degree absent (do not invent).
            pass
        if field:
            edu["field"] = field
        if institution:
            edu["institution"] = institution
        if cgpa is not None:
            edu["cgpa"] = cgpa
        if scale is not None:
            edu["cgpa_scale"] = scale
        if percentage is not None:
            edu["percentage"] = percentage
        if edu:
            education.append(edu)

    experience = _find_experience(lines, text)
    skills = _find_skills(text)
    testing = _find_testing(text)
    coursework = _find_coursework(lines)

    # Target fields default to any AI/CS/data-ish names found in the resume.
    target_fields: List[str] = []
    low = text.lower()
    for phrase in ("artificial intelligence", "machine learning", "data science", "computer science"):
        if phrase in low:
            target_fields.append(phrase.title())

    result: dict = {}
    email = _EMAIL_RE.search(text)
    name = _find_name(lines, text)
    if name:
        result["name"] = name
    if email:
        result.setdefault("metadata", {})["email"] = email.group(0)
    if education:
        result["education"] = education
    if experience:
        result["experience"] = experience
    if skills:
        result["technical_background"] = skills
    if testing:
        result["testing"] = testing
    if coursework:
        result["coursework"] = coursework
    if target_fields:
        result["target_fields"] = target_fields
    return result


def parse_transcript(filename: str, data: bytes) -> dict:
    """Parse a transcript specifically for coursework + grades.

    Merges into the same shape as ``parse_resume`` but focuses on course lines.
    """
    text = extract_text(filename, data)
    lines = _lines(text)
    coursework = _find_coursework(lines)
    cgpa, scale, percentage = _find_cgpa(text)
    degree, institution = _find_degree(lines, text)

    education: List[dict] = []
    edu: dict = {}
    if degree:
        edu["degree"] = degree
    if institution:
        edu["institution"] = institution
    if cgpa is not None:
        edu["cgpa"] = cgpa
    if scale is not None:
        edu["cgpa_scale"] = scale
    if percentage is not None:
        edu["percentage"] = percentage
    if edu:
        edu["transcript_available"] = True
        education.append(edu)

    result: dict = {"coursework": coursework} if coursework else {}
    if education:
        result["education"] = education
    return result


def _merge_education(existing: List[dict], incoming: List[dict]) -> List[dict]:
    """Fold education entries together without duplicating or creating degreeless rows.

    A transcript often yields only grades/cgpa with no degree; that must enrich
    the existing degree entry rather than become an invalid second entry.
    """
    out = [dict(e) for e in existing]
    for item in incoming:
        item = dict(item)
        if item in out:
            continue
        # Enrich an existing entry only when degree AND field agree (or the
        # incoming entry has neither); otherwise it is genuinely new.
        target = None
        if item.get("degree") or item.get("field"):
            for entry in out:
                same_degree = item.get("degree") and entry.get("degree") == item.get("degree")
                same_field = item.get("field") and entry.get("field") == item.get("field")
                if same_degree and (same_field or not item.get("field") or not entry.get("field")):
                    target = entry
                    break
        elif out:
            target = out[0]
        if target is not None:
            for k, v in item.items():
                if target.get(k) in (None, "", []):
                    target[k] = v
        else:
            out.append(item)
    return out


def merge_profile_dicts(base: dict, incoming: dict) -> dict:
    """Merge parsed fields into an existing profile dict, without clobbering.

    Lists (education/experience/coursework) are concatenated/deduplicated;
    scalars prefer an existing set value, else the incoming one.
    """
    merged = dict(base or {})
    for key, value in (incoming or {}).items():
        if value in (None, "", [], {}):
            continue
        if key in ("education", "experience", "coursework") and isinstance(value, list):
            existing = list(merged.get(key) or [])
            if key == "education":
                existing = _merge_education(existing, value)
            else:
                for item in value:
                    if item not in existing:
                        existing.append(item)
            merged[key] = existing
        elif key == "metadata" and isinstance(value, dict):
            existing = dict(merged.get("metadata") or {})
            existing.update(value)
            merged["metadata"] = existing
        elif key == "testing" and isinstance(value, dict):
            existing = dict(merged.get("testing") or {})
            for k, v in value.items():
                if existing.get(k) in (None, ""):
                    existing[k] = v
            merged["testing"] = existing
        elif merged.get(key) in (None, "", [], {}):
            merged[key] = value
        elif key in ("technical_background", "target_fields") and isinstance(value, list):
            existing = list(merged.get(key) or [])
            for item in value:
                if item not in existing:
                    existing.append(item)
            merged[key] = existing
    return merged


def parsed_to_profile(parsed: dict) -> ApplicantProfile:
    """Build a validated profile from parsed fields (used for tests/preview)."""
    return ApplicantProfile(**parsed)


class HeuristicParser:
    """Provider wrapping the regex/keyword extractors (quality WIP)."""

    name = "heuristic"

    def parse(self, filename: str, data: bytes, kind: str = "resume") -> dict:
        if kind == "transcript":
            return parse_transcript(filename, data)
        return parse_resume(filename, data)
