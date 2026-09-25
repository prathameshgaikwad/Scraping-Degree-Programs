"""Phase 6 pipeline: extract structured requirements + evidence per program.

Reads crawled pages and merges per-page extractions using the intelligence
layer's source-priority merge, then maps to the strict requirement schema.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..crawl.models import CrawledPage, CrawlStatus, PageType as CrawlPageType
from ..intelligence.merge import Merger
from ..intelligence.schema import ProgramIntelligence
from ..normalize.io import ensure_dir, read_jsonl, utcnow, write_json, write_jsonl
from .extractor import PageExtractionCache, RequirementsPageExtractor, make_source
from .mapping import build_requirements
from .models import ProgramRequirements, RequirementsManifest
from .versions import REQUIREMENTS_EXTRACTOR_VERSION, REQUIREMENTS_SCHEMA_VERSION

_SKIP_PAGE_TYPES = {CrawlPageType.IRRELEVANT}


@dataclass
class RequirementsConfig:
    pages_path: str = "data/enriched/university_pages/pages.jsonl"
    programs_path: str = "data/normalized/programs.jsonl"
    universities_path: str = "data/normalized/universities.jsonl"
    out_dir: str = "data/enriched/requirements"
    use_llm: bool = False
    force: bool = False
    limit: int = 0


class RequirementsPipeline:
    def __init__(self, config: Optional[RequirementsConfig] = None) -> None:
        self.config = config or RequirementsConfig()

    def run(self) -> RequirementsManifest:
        cfg = self.config
        ensure_dir(cfg.out_dir)
        cache_path = os.path.join(cfg.out_dir, "page_extraction_cache.json")
        cache = PageExtractionCache(cache_path)
        extractor = RequirementsPageExtractor(cache=cache, use_llm=cfg.use_llm)

        pages = [CrawledPage(**row) for row in read_jsonl(cfg.pages_path)]
        programs = {p["program_id"]: p for p in read_jsonl(cfg.programs_path)}
        universities = {u["university_id"]: u for u in read_jsonl(cfg.universities_path)}

        by_program: Dict[str, List[CrawledPage]] = defaultdict(list)
        for page in pages:
            if page.crawl_status != CrawlStatus.SUCCESS or page.page_type in _SKIP_PAGE_TYPES:
                continue
            if page.depth == 0:
                # Skip the university homepage: it is a marketing landing page and
                # produces false requirement matches (e.g. "undergraduate degree").
                continue
            if not (page.text or "").strip():
                continue
            for pid in (page.program_ids or [page.program_id]):
                if pid:
                    by_program[pid].append(page)

        program_ids = sorted(by_program.keys())
        if cfg.limit:
            program_ids = program_ids[: cfg.limit]

        results: List[ProgramRequirements] = []
        pages_considered = 0
        pages_extracted = 0
        cache_hits = 0

        for index, pid in enumerate(program_ids, start=1):
            program = programs.get(pid, {})
            university = universities.get(program.get("university_id", ""), {})
            program_hint = dict(program)
            program_hint["university_name"] = university.get("canonical_name")

            program_pages = by_program[pid]
            pages_considered += len(program_pages)
            sources = {page.page_id: make_source(page) for page in program_pages}

            merged = ProgramIntelligence()
            merger = Merger(sources)
            for page in program_pages:
                partial = extractor.extract(page, program_hint)
                if extractor.last_from_cache:
                    cache_hits += 1
                else:
                    pages_extracted += 1
                merger.merge(merged, partial)

            requirements = build_requirements(
                program_id=pid,
                university_id=program.get("university_id", ""),
                merged=merged,
                sources=sources,
                program_name=program.get("name"),
                university_name=university.get("canonical_name"),
                used_page_ids=[p.page_id for p in program_pages],
            )
            requirements.extracted_at = utcnow()
            results.append(requirements)

            if index % 10 == 0:
                cache.save()

        cache.save()
        write_jsonl(os.path.join(cfg.out_dir, "requirements.jsonl"), results)
        manifest = self._manifest(cfg, results, pages_considered, pages_extracted, cache_hits)
        write_json(os.path.join(cfg.out_dir, "manifest.json"), manifest)
        return manifest

    @staticmethod
    def _manifest(
        cfg: RequirementsConfig,
        results: List[ProgramRequirements],
        pages_considered: int,
        pages_extracted: int,
        cache_hits: int,
    ) -> RequirementsManifest:
        by_completeness = Counter()
        for req in results:
            for section, done in req.completeness.model_dump().items():
                if done:
                    by_completeness[section] += 1
        with_evidence = sum(
            1 for req in results if any(src.url for src in req.sources)
        )
        return RequirementsManifest(
            pages_path=cfg.pages_path,
            programs_path=cfg.programs_path,
            extractor_version=REQUIREMENTS_EXTRACTOR_VERSION,
            schema_version=REQUIREMENTS_SCHEMA_VERSION,
            generated_at=utcnow(),
            programs=len(results),
            pages_considered=pages_considered,
            pages_extracted=pages_extracted,
            cache_hits=cache_hits,
            by_completeness=dict(by_completeness.most_common()),
            programs_with_evidence=with_evidence,
        )
