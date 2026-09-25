"""Minimal zero-dependency HTTP server exposing the read-only API + React SPA.

Serves the React frontend build (``static/app``) at ``/``.

    python -m degreeprograms.cli serve
    python -m degreeprograms.webapp.app --port 8000
"""

from __future__ import annotations

import json
import os
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from .service import ProgramsService

_THIS_DIR = os.path.dirname(__file__)
SPA_DIR = os.path.join(_THIS_DIR, "static", "app")


def _resolve_frontend_dir() -> str:
    """Directory served at ``/`` — the React build.

    Override with the ``WEBAPP_FRONTEND_DIR`` environment variable.
    """
    return os.environ.get("WEBAPP_FRONTEND_DIR") or SPA_DIR


_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    service: ProgramsService = None  # set by make_server
    frontend_dir: str = SPA_DIR  # set by make_server (React build, served at /)
    cors_origin: Optional[str] = None  # set by make_server; "*" allows any origin
    server_version = "ProgramIntelligence/0.1"

    def log_message(self, fmt, *args):  # quieter default logging
        pass

    # -- helpers -------------------------------------------------------------
    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors(self) -> None:
        if self.cors_origin:
            self.send_header("Access-Control-Allow-Origin", self.cors_origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802 (CORS preflight)
        self.send_response(204)
        self._send_cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_static(self, rel_path: str, base_dir: str) -> None:
        safe = posixpath.normpath("/" + rel_path).lstrip("/")
        full = os.path.join(base_dir, safe)
        if not os.path.abspath(full).startswith(os.path.abspath(base_dir)) or not os.path.isfile(full):
            self._send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", _CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    # -- routing -------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_static("index.html", self.frontend_dir)
            return
        if path.startswith("/assets/"):
            self._send_static("assets/" + path[len("/assets/"):], self.frontend_dir)
            return
        if path == "/api/meta":
            self._send_json(self.service.meta())
            return
        if path == "/api/profile":
            self._send_json(self.service.get_profile() or {})
            return
        if path == "/api/profile/parse":
            self._handle_parse_upload()
            return
        if path == "/api/programs":
            def one(name, default=None):
                values = query.get(name)
                return values[0] if values else default

            def number(name, default):
                try:
                    return int(one(name, default))
                except (TypeError, ValueError):
                    return default

            def flag(name):
                value = one(name)
                if value is None:
                    return None
                return value.strip().lower() in {"1", "true", "yes"}

            max_rank_raw = one("max_rank")
            try:
                max_rank = int(max_rank_raw) if max_rank_raw not in (None, "") else None
            except ValueError:
                max_rank = None

            self._send_json(
                self.service.search(
                    q=one("q"),
                    field=query.get("field"),
                    country=query.get("country"),
                    relevance=query.get("relevance"),
                    state=query.get("state"),
                    program_format=query.get("program_format"),
                    degree_type=query.get("degree_type"),
                    analysed=flag("analysed"),
                    max_rank=max_rank,
                    sort=one("sort", "rank"),
                    limit=min(number("limit", 2000), 5000),
                    offset=max(number("offset", 0), 0),
                )
            )
            return
        if path.startswith("/api/programs/"):
            pid = unquote(path[len("/api/programs/"):])
            detail = self.service.program(pid)
            if detail is None:
                self._send_json({"error": "program not found", "program_id": pid}, 404)
            else:
                self._send_json(detail)
            return
        self._send_json({"error": "not found"}, 404)

    # -- mutations -----------------------------------------------------------
    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/profile/parse":
            self._handle_parse_upload()
            return
        if path == "/api/profile":
            self._handle_set_profile()
            return
        self._send_json({"error": "not found"}, 404)

    def do_PUT(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/api/profile":
            self._handle_set_profile()
            return
        self._send_json({"error": "not found"}, 404)

    def _handle_set_profile(self) -> None:
        payload = self._read_json_body()
        profile_doc = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
        try:
            saved = self.service.set_profile(profile_doc)
        except ValueError as exc:
            self._send_json({"error": "invalid profile", "detail": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json({"error": "could not save profile", "detail": str(exc)}, 400)
            return
        self._send_json({"profile": saved, "meta": self.service.meta()})

    def _handle_parse_upload(self) -> None:
        import base64

        from ..parsing import parse_document, parsing_enabled
        from ..parsing.heuristic import merge_profile_dicts

        payload = self._read_json_body()
        filename = str(payload.get("filename") or "")
        kind = str(payload.get("kind") or "resume").lower()
        encoded = payload.get("content") or ""
        if not encoded:
            self._send_json({"error": "no file content"}, 400)
            return
        try:
            data = base64.b64decode(encoded)
        except Exception:
            self._send_json({"error": "invalid base64 content"}, 400)
            return

        parsed = parse_document(filename, data, kind=kind)
        response: dict = {
            "parsed": parsed,
            "kind": kind,
            "filename": filename,
            "parsing_enabled": parsing_enabled(),
        }
        if bool(payload.get("apply")) and parsed:
            merged = merge_profile_dicts(self.service.get_profile(), parsed)
            try:
                response["profile"] = self.service.set_profile(merged)
                response["meta"] = self.service.meta()
            except ValueError as exc:
                response["apply_error"] = str(exc)
        self._send_json(response)


def make_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    service: Optional[ProgramsService] = None,
    frontend_dir: Optional[str] = None,
    cors_origin: Optional[str] = None,
) -> Tuple[ThreadingHTTPServer, ProgramsService]:
    service = service or ProgramsService()
    handler = type(
        "BoundHandler",
        (Handler,),
        {
            "service": service,
            "frontend_dir": frontend_dir or _resolve_frontend_dir(),
            "cors_origin": cors_origin,
        },
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    return httpd, service


def run(
    host: str = "127.0.0.1",
    port: int = 8000,
    service: Optional[ProgramsService] = None,
    frontend_dir: Optional[str] = None,
    cors_origin: Optional[str] = None,
) -> None:
    httpd, svc = make_server(host, port, service, frontend_dir=frontend_dir, cors_origin=cors_origin)
    print(f"Program Intelligence UI running at http://{host}:{httpd.server_address[1]}/")
    print(f"  programs={len(svc.programs)} analyzed={svc.meta()['analyzed']}")
    if cors_origin:
        print(f"  CORS: Access-Control-Allow-Origin={cors_origin}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Program Intelligence UI/API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend-dir", default=None, help="React build to serve at / (default: static/app)")
    parser.add_argument("--cors-origin", default=None, help="Value for Access-Control-Allow-Origin (e.g. * or http://localhost:5173)")
    args = parser.parse_args()
    run(
        args.host,
        args.port,
        frontend_dir=args.frontend_dir,
        cors_origin=args.cors_origin,
    )
