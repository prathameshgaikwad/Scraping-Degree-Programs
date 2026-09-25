"""PDF text extraction.

Prefers a real PDF library if one is installed (pypdf / PyPDF2 / pdfminer),
and otherwise falls back to a dependency-free extractor that handles the most
common case: FlateDecode content streams with standard text operators.

The fallback is intentionally conservative. If it cannot decode a stream it
returns whatever it could read rather than inventing content.
"""

from __future__ import annotations

import re
import zlib
from typing import List, Optional, Tuple

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_STRING_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")
_HEX_RE = re.compile(rb"<([0-9A-Fa-f\s]+)>")
_TJ_ARRAY_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
_Tj_RE = re.compile(rb"(\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>)\s*Tj")
_QUOTE_RE = re.compile(rb"(\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>)\s*['\"]")
_POS_RE = re.compile(rb"(T\*|Td|TD|TL|ET)\b")


def available_backend() -> str:
    try:
        import pypdf  # noqa: F401

        return "pypdf"
    except Exception:
        pass
    try:
        import PyPDF2  # noqa: F401

        return "PyPDF2"
    except Exception:
        pass
    try:
        import pdfminer  # noqa: F401

        return "pdfminer"
    except Exception:
        pass
    return "builtin"


def extract_pdf_pages(binary: bytes) -> List[Tuple[int, str]]:
    """Return a list of (page_number, text). page_number is 1-indexed."""
    backend = available_backend()
    if backend == "pypdf":
        try:
            return _extract_pypdf(binary)
        except Exception:
            pass
    elif backend == "PyPDF2":
        try:
            return _extract_pypdf2(binary)
        except Exception:
            pass
    return _extract_builtin(binary)


def _extract_pypdf(binary: bytes) -> List[Tuple[int, str]]:
    import io

    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(binary))
    pages: List[Tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            pages.append((idx, page.extract_text() or ""))
        except Exception:
            pages.append((idx, ""))
    return pages


def _extract_pypdf2(binary: bytes) -> List[Tuple[int, str]]:
    import io

    import PyPDF2

    reader = PyPDF2.PdfReader(io.BytesIO(binary))
    pages: List[Tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            pages.append((idx, page.extract_text() or ""))
        except Exception:
            pages.append((idx, ""))
    return pages


def _decode_stream(raw: bytes) -> Optional[bytes]:
    raw = raw.strip(b"\r\n")
    try:
        return zlib.decompress(raw)
    except zlib.error:
        pass
    try:
        return zlib.decompressobj().decompress(raw)
    except zlib.error:
        return None


def _unescape_pdf_string(data: bytes) -> str:
    out = bytearray()
    i = 0
    mapping = {
        ord("n"): b"\n",
        ord("r"): b"\r",
        ord("t"): b"\t",
        ord("b"): b"\b",
        ord("f"): b"\f",
        ord("("): b"(",
        ord(")"): b")",
        ord("\\"): b"\\",
    }
    while i < len(data):
        ch = data[i]
        if ch == 0x5C and i + 1 < len(data):  # backslash
            nxt = data[i + 1]
            if nxt in mapping:
                out.extend(mapping[nxt])
                i += 2
                continue
            if 0x30 <= nxt <= 0x37:  # octal
                oct_digits = bytearray()
                j = i + 1
                while j < len(data) and len(oct_digits) < 3 and 0x30 <= data[j] <= 0x37:
                    oct_digits.append(data[j])
                    j += 1
                try:
                    out.append(int(oct_digits, 8) & 0xFF)
                except ValueError:
                    pass
                i = j
                continue
            i += 2
            continue
        out.append(ch)
        i += 1
    return out.decode("latin-1", "replace")


def _text_from_operand(operand: bytes) -> str:
    if operand.startswith(b"("):
        return _unescape_pdf_string(operand[1:-1])
    if operand.startswith(b"<"):
        hex_digits = re.sub(rb"\s", b"", operand[1:-1]).decode("ascii", "ignore")
        if len(hex_digits) % 2 == 1:
            hex_digits += "0"
        try:
            raw = bytes.fromhex(hex_digits)
        except ValueError:
            return ""
        # Many PDFs use 2-byte CID encodings; try utf-16-be then latin-1.
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            return raw.decode("latin-1", "replace")
    return ""


def _extract_text_from_content(content: bytes) -> str:
    text = content.decode("latin-1", "replace")

    store: List[str] = []

    def emit(value: str) -> str:
        # Strip control bytes so emitted text can never forge a sentinel.
        safe = "".join(ch for ch in value if ch >= " " or ch == "\n")
        store.append(safe)
        return f"\x01{len(store) - 1}\x01"

    # Text-showing array: [ (a) -250 (b) ] TJ
    def tj_array_repl(match: "re.Match[str]") -> str:
        inner = match.group(0).encode("latin-1", "replace")
        parts = [_text_from_operand(s) for s in _STRING_RE.findall(inner)]
        return emit("".join(parts))

    text = re.sub(r"\[(?:[^\[\]\\]|\\.)*\]\s*TJ", tj_array_repl, text, flags=re.DOTALL)

    # Single-string showing operators: (..) Tj  /  <..> Tj  /  (..) '  /  (..) "
    operand = r"(?:\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>)"

    def string_repl(match: "re.Match[str]") -> str:
        return emit(_text_from_operand(match.group(1).encode("latin-1", "replace")))

    text = re.sub(rf"({operand})\s*(?:Tj|'|\")", string_repl, text)

    # Line/positioning operators become newlines.
    text = re.sub(r"\bT\*|\bTd|\bTD|\bET\b", lambda _m: emit("\n"), text)

    # Keep only emitted text, in order.
    pieces = []
    for idx in re.findall(r"\x01(\d+)\x01", text):
        i = int(idx)
        if 0 <= i < len(store):
            pieces.append(store[i])
    result = "".join(pieces)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _extract_builtin(binary: bytes) -> List[Tuple[int, str]]:
    chunks: List[str] = []
    for match in _STREAM_RE.finditer(binary):
        raw = match.group(1)
        decoded = _decode_stream(raw)
        if decoded is None:
            decoded = raw
        # Only attempt streams that look like content streams.
        if b"Tj" not in decoded and b"TJ" not in decoded and b"BT" not in decoded:
            continue
        text = _extract_text_from_content(decoded)
        if text.strip():
            chunks.append(text)
    if not chunks:
        return []
    # Without a parser we cannot reliably recover page boundaries.
    return [(1, "\n\n".join(chunks))]
