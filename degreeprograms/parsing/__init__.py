"""Pluggable resume/transcript parsing.

Resume parsing is deliberately abstracted behind a small provider interface so
the rest of the product never depends on any particular implementation. The
current heuristic parser is one provider (``heuristic``); the default is
``null`` (no parsing), because parsing quality is a work-in-progress and the
applicant can always enter details manually.

To add a new implementation (e.g. an LLM pass), implement :class:`DocumentParser`
and register it in :data:`PROVIDERS`. Nothing else needs to change.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Protocol


class DocumentParser(Protocol):
    """Extracts structured profile fields from a resume/transcript document."""

    name: str

    def parse(self, filename: str, data: bytes, kind: str = "resume") -> dict:
        """Return a partial applicant-profile dict (only fields actually found)."""
        ...


class NullParser:
    """Default provider: parsing is disabled, so nothing is extracted.

    Keeps the upload path a no-op while parsing is improved elsewhere; the UI
    steers the applicant to manual entry.
    """

    name = "null"

    def parse(self, filename: str, data: bytes, kind: str = "resume") -> dict:
        return {}


def _load_heuristic() -> Optional[DocumentParser]:
    try:
        from .heuristic import HeuristicParser

        return HeuristicParser()
    except Exception:
        return None


PROVIDERS: Dict[str, Callable[[], Optional[DocumentParser]]] = {
    "null": lambda: NullParser(),
    "heuristic": _load_heuristic,
}

DEFAULT_PROVIDER = "null"


def get_parser(name: Optional[str] = None) -> DocumentParser:
    """Return the configured parser. Falls back to the null parser."""
    key = (name or DEFAULT_PROVIDER).strip().lower()
    factory = PROVIDERS.get(key)
    parser = factory() if factory else None
    return parser or NullParser()


def parse_document(filename: str, data: bytes, kind: str = "resume", provider: Optional[str] = None) -> dict:
    """Parse a document with the selected provider (default: disabled)."""
    return get_parser(provider).parse(filename, data, kind=kind)


def parsing_enabled() -> bool:
    """Whether the active provider actually extracts anything."""
    return get_parser().name != "null"
