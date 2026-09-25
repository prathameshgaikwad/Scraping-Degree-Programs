"""Tests for the Phase 9 web app (service + HTTP API).

    python -m unittest discover -s degreeprograms/webapp/tests -t .
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from degreeprograms.webapp.app import make_server
from degreeprograms.webapp.service import ProgramsService


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _fixtures(tmp):
    programs = os.path.join(tmp, "programs.jsonl")
    classifications = os.path.join(tmp, "classifications.jsonl")
    requirements = os.path.join(tmp, "requirements.jsonl")
    eligibility = os.path.join(tmp, "eligibility.jsonl")
    universities = os.path.join(tmp, "universities.jsonl")
    profile = os.path.join(tmp, "applicant.json")

    _write(programs, [
        {"program_id": "p1", "university_id": "u1", "name": "MSc Artificial Intelligence",
         "degree_type": "MSC", "program_format": "FULL_TIME",
         "location": {"city": "London", "country": "United Kingdom"},
         "ranking": {"university_rank": 9, "rank_display": "9"},
         "source": {"program_url": "https://www.topuniversities.com/x"}},
        {"program_id": "p2", "university_id": "u1", "name": "MSc Materials Science",
         "degree_type": "MSC", "program_format": "UNKNOWN",
         "location": {"city": "London", "country": "United Kingdom"},
         "ranking": {}, "source": {}},
    ])
    _write(classifications, [
        {"program_id": "p1", "primary_field": "ARTIFICIAL_INTELLIGENCE", "secondary_fields": ["MACHINE_LEARNING"],
         "relevance": "HIGH", "confidence": 0.87, "reason": "matched artificial intelligence"},
        {"program_id": "p2", "primary_field": "UNKNOWN", "secondary_fields": [], "relevance": "NONE",
         "confidence": 0.8, "reason": "no taxonomy terms"},
    ])
    _write(requirements, [
        {"program_id": "p1", "academic_requirements": {
            "minimum_degree_level": {"value": "BACHELOR", "status": "KNOWN",
                                     "evidence": [{"url": "https://u1.edu/admissions", "page_title": "Admissions", "quote": "bachelor's degree"}]},
            "accepted_backgrounds": [], "related_degree_allowed": {"status": "UNKNOWN"},
            "minimum_gpa": {"status": "UNKNOWN"}, "minimum_gpa_scale": {"status": "UNKNOWN"},
            "minimum_percentage": {"status": "UNKNOWN"}, "minimum_grade": {"status": "UNKNOWN"}},
         "language_requirements": {"english_required": {"value": True, "status": "KNOWN"},
                                   "ielts": {"value": 6.5, "status": "KNOWN",
                                             "evidence": [{"url": "https://u1.edu/admissions", "quote": "IELTS 6.5"}]},
                                   "toefl": {"status": "NOT_MENTIONED"}, "pte": {"status": "NOT_MENTIONED"},
                                   "duolingo": {"status": "NOT_MENTIONED"}, "cambridge": {"status": "NOT_MENTIONED"}},
         "tests": {"gre_required": {"status": "NOT_MENTIONED"}, "gmat_required": {"status": "NOT_MENTIONED"}},
         "experience": {"required": {"status": "NOT_MENTIONED"}, "preferred": {"status": "NOT_MENTIONED"},
                        "minimum_years": {"status": "UNKNOWN"}},
         "application": {"deadline": {"value": "2027-03-31", "status": "KNOWN"}, "opens": {"status": "UNKNOWN"},
                         "international_deadline": {"status": "UNKNOWN"}, "application_fee": {"status": "UNKNOWN"},
                         "rolling_admission": {"status": "UNKNOWN"}},
         "financial": {"tuition": {"value": 20000, "status": "KNOWN"}, "currency": {"value": "GBP", "status": "KNOWN"},
                       "period": {"value": "per_year", "status": "KNOWN"}},
         "prerequisites": [{"category": "PROGRAMMING", "requirement": "programming", "credits": 15}],
         "sources": []},
    ])
    _write(eligibility, [
        {"program_id": "p1", "university_id": "u1", "applicant_id": "dev",
         "state": "LIKELY_ELIGIBLE",
         "dimensions": {
             "degree_level": {"name": "degree_level", "status": "PASS", "reason": "holds BACHELOR",
                              "evidence": [{"url": "https://u1.edu/admissions", "quote": "bachelor's degree"}]},
             "english": {"name": "english", "status": "UNKNOWN", "reason": "no test score"}},
         "reasons": ["LIKELY_ELIGIBLE: no failures"], "evidence": [], "prerequisite_gaps": [], "uncertain": ["english"],
         "failed": []},
    ])
    _write(universities, [
        {"university_id": "u1", "canonical_name": "Example University", "country": "United Kingdom",
         "city": "London", "official_domain": "u1.edu", "qs": {"university_rank": 9}, "aliases": [{"alias": "Example University"}]},
    ])
    with open(profile, "w", encoding="utf-8") as fh:
        json.dump({"applicant": {"applicant_id": "dev",
                                 "education": {"degree": "B.Tech", "field": "Metallurgy", "cgpa": 7.67},
                                 "experience": [{"title": "Software Engineer", "years": 2}],
                                 "target_fields": ["Artificial Intelligence"],
                                 "technical_background": ["Java"]}}, fh)
    return programs, classifications, requirements, eligibility, universities, profile


def _service(tmp):
    paths = _fixtures(tmp)
    return ProgramsService(
        programs_path=paths[0], classifications_path=paths[1], requirements_path=paths[2],
        eligibility_path=paths[3], universities_path=paths[4], profile_path=paths[5],
    )


class ServiceTests(unittest.TestCase):
    def test_meta_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            meta = svc.meta()
            self.assertEqual(meta["total_programs"], 2)
            self.assertEqual(meta["analyzed"], 1)
            fields = {f["value"]: f["count"] for f in meta["facets"]["primary_field"]}
            self.assertEqual(fields.get("ARTIFICIAL_INTELLIGENCE"), 1)

            self.assertEqual(svc.search(q="artificial")["total"], 1)
            self.assertEqual(svc.search(state="LIKELY_ELIGIBLE")["total"], 1)
            self.assertEqual(svc.search(relevance="NONE")["total"], 1)
            self.assertEqual(svc.search(field="MACHINE_LEARNING")["total"], 0)

    def test_program_detail_and_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            detail = svc.program("p1")
            self.assertEqual(detail["summary"]["university_name"], "Example University")
            self.assertEqual(detail["classification"]["relevance"], "HIGH")
            self.assertEqual(detail["requirements"]["language_requirements"]["ielts"]["value"], 6.5)
            self.assertEqual(detail["eligibility"]["state"], "LIKELY_ELIGIBLE")
            self.assertIsNone(svc.program("missing"))
            profile = svc.profile_summary()
            self.assertEqual(profile["education"]["field"], "Metallurgy")


    def test_multivalue_filters_sort_and_analysed(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            self.assertEqual(svc.search(field=["ARTIFICIAL_INTELLIGENCE", "UNKNOWN"])["total"], 2)
            self.assertEqual(svc.search(relevance="HIGH")["total"], 1)
            self.assertEqual(svc.search(analysed=True)["total"], 1)
            self.assertEqual(svc.search(analysed=False)["total"], 1)
            self.assertEqual(svc.search(max_rank=10)["total"], 1)   # p1 rank 9
            self.assertEqual(svc.search(max_rank=5)["total"], 0)
            names = [r["program_id"] for r in svc.search(sort="name")["results"]]
            self.assertEqual(names, ["p1", "p2"])  # "AI" < "Materials"

    def test_summary_enriched_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            item = svc.search(q="artificial")["results"][0]
            self.assertEqual(item["tuition_amount"], 20000)
            self.assertEqual(item["tuition_currency"], "GBP")
            self.assertEqual(item["deadline"], "2027-03-31")
            self.assertTrue(item["analysed"])
            self.assertGreaterEqual(item["evidence_count"], 0)
            other = svc.search(q="materials")["results"][0]
            self.assertFalse(other["analysed"])


class ApiTests(unittest.TestCase):
    def test_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            httpd, _ = make_server("127.0.0.1", 0, svc)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{port}"

            def get(path):
                with urllib.request.urlopen(base + path, timeout=5) as resp:
                    return resp.status, resp.read().decode("utf-8")

            try:
                status, body = get("/")
                self.assertEqual(status, 200)
                self.assertIn('id="root"', body)  # React SPA shell

                status, body = get("/api/meta")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["total_programs"], 2)

                status, body = get("/api/programs?q=artificial")
                self.assertEqual(json.loads(body)["total"], 1)

                status, body = get("/api/programs?relevance=HIGH&relevance=NONE")
                self.assertEqual(json.loads(body)["total"], 2)

                status, body = get("/api/programs?state=LIKELY_ELIGIBLE&sort=name")
                payload = json.loads(body)
                self.assertEqual(payload["total"], 1)
                self.assertEqual(payload["results"][0]["program_id"], "p1")

                status, body = get("/api/programs/p1")
                self.assertEqual(json.loads(body)["classification"]["primary_field"], "ARTIFICIAL_INTELLIGENCE")

                try:
                    get("/api/programs/nope")
                    self.fail("expected 404")
                except urllib.error.HTTPError as exc:
                    self.assertEqual(exc.code, 404)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_cors_headers_and_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            httpd, _ = make_server("127.0.0.1", 0, svc, cors_origin="*")
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{port}"
            try:
                req = urllib.request.Request(base + "/api/meta")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["total_programs"], 2)

                preflight = urllib.request.Request(base + "/api/meta", method="OPTIONS")
                with urllib.request.urlopen(preflight, timeout=5) as resp:
                    self.assertEqual(resp.status, 204)
                    self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
                    self.assertIn("GET", resp.headers.get("Access-Control-Allow-Methods", ""))
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_no_cors_header_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            svc = _service(tmp)
            httpd, _ = make_server("127.0.0.1", 0, svc)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=5) as resp:
                    self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))
            finally:
                httpd.shutdown()
                httpd.server_close()


class ProfileEndpointTests(unittest.TestCase):
    """Editable applicant profile + resume/transcript parsing endpoints."""

    def _server(self, tmp):
        svc = _service(tmp)
        httpd, _ = make_server("127.0.0.1", 0, svc)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, f"http://127.0.0.1:{port}"

    def test_get_and_put_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            httpd, base = self._server(tmp)
            try:
                with urllib.request.urlopen(base + "/api/profile", timeout=5) as resp:
                    self.assertIn("education", json.loads(resp.read().decode("utf-8")))

                doc = {"profile": {"applicant_id": "edited", "education": [
                    {"degree": "MSc", "field": "Data Science", "cgpa": 8.0, "cgpa_scale": 10}],
                    "technical_background": ["Python"]}}
                req = urllib.request.Request(
                    base + "/api/profile", data=json.dumps(doc).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="PUT")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(payload["profile"]["applicant_id"], "edited")
                    self.assertIn("meta", payload)

                with urllib.request.urlopen(base + "/api/profile", timeout=5) as resp:
                    self.assertEqual(json.loads(resp.read().decode("utf-8"))["applicant_id"], "edited")
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_put_invalid_profile_returns_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            httpd, base = self._server(tmp)
            try:
                req = urllib.request.Request(
                    base + "/api/profile", data=json.dumps({"profile": {"education": [{"cgpa": -5}]}}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="PUT")
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(req, timeout=10)
                self.assertEqual(ctx.exception.code, 400)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_parse_endpoint_default_provider_extracts_nothing(self):
        # Parsing is abstracted; the default provider is disabled by design.
        with tempfile.TemporaryDirectory() as tmp:
            httpd, base = self._server(tmp)
            try:
                text = "Jane Doe\nEDUCATION\nB.Tech in Computer Science\nCGPA: 8.0/10\n"
                body = {
                    "filename": "jane.txt",
                    "kind": "resume",
                    "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                    "apply": True,
                }
                req = urllib.request.Request(
                    base + "/api/profile/parse", data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(payload["parsed"], {})
                self.assertFalse(payload["parsing_enabled"])
                self.assertNotIn("profile", payload)  # nothing to apply
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_parse_endpoint_extracts_with_heuristic_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            httpd, base = self._server(tmp)
            try:
                text = "Jane Doe\nEDUCATION\nB.Tech in Computer Science\nCGPA: 8.0/10\nSKILLS\nPython, SQL\n"
                body = {
                    "filename": "jane.txt",
                    "kind": "resume",
                    "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
                    "apply": True,
                }
                # Swap the default provider to the heuristic implementation.
                import degreeprograms.parsing as parsing

                original = parsing.DEFAULT_PROVIDER
                parsing.DEFAULT_PROVIDER = "heuristic"
                try:
                    req = urllib.request.Request(
                        base + "/api/profile/parse", data=json.dumps(body).encode("utf-8"),
                        headers={"Content-Type": "application/json"}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        payload = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(payload["parsed"]["education"][0]["degree"], "B.Tech")
                    self.assertTrue(payload["parsing_enabled"])
                    self.assertIn("profile", payload)
                finally:
                    parsing.DEFAULT_PROVIDER = original
            finally:
                httpd.shutdown()
                httpd.server_close()


class FrontendTests(unittest.TestCase):

    def test_frontend_dir_serves_react_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            fe = os.path.join(tmp, "app")
            os.makedirs(os.path.join(fe, "assets"))
            with open(os.path.join(fe, "index.html"), "w", encoding="utf-8") as fh:
                fh.write('<!doctype html><div id="root">REACT_BUILD</div>')
            with open(os.path.join(fe, "assets", "marker.txt"), "w", encoding="utf-8") as fh:
                fh.write("asset-ok")

            svc = _service(tmp)
            httpd, _ = make_server("127.0.0.1", 0, svc, frontend_dir=fe)
            port = httpd.server_address[1]
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{port}"
            try:
                with urllib.request.urlopen(base + "/", timeout=5) as resp:
                    self.assertIn("REACT_BUILD", resp.read().decode("utf-8"))
                with urllib.request.urlopen(base + "/assets/marker.txt", timeout=5) as resp:
                    self.assertEqual(resp.read().decode("utf-8"), "asset-ok")
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
