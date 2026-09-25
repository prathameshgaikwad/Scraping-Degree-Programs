"""Phase 2 pipeline: raw QS records -> canonical universities + programs.

Idempotent: if the raw input hash and normalizer version are unchanged since the
last run, the existing output is reused unless ``force`` is set. Raw data is
only ever read.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from .io import (
    file_sha256,
    load_alias_registry,
    read_json,
    read_jsonl,
    utcnow,
    write_json,
    write_jsonl,
)
from .models import CanonicalProgram, CanonicalUniversity, NormalizationManifest
from .programs import ProgramNormalizer
from .universities import UniversityResolver
from .versions import NORMALIZE_SCHEMA_VERSION, NORMALIZER_VERSION

_DEFAULT_ALIASES = os.path.join(os.path.dirname(__file__), "data", "university_aliases.json")


@dataclass
class NormalizeConfig:
    input_path: str = "degreeprograms/qs-spidy.jsonl"
    out_dir: str = "data/normalized"
    alias_registry_path: str = _DEFAULT_ALIASES
    force: bool = False


class NormalizationPipeline:
    def __init__(self, config: Optional[NormalizeConfig] = None) -> None:
        self.config = config or NormalizeConfig()

    def run(self) -> NormalizationManifest:
        cfg = self.config
        os.makedirs(cfg.out_dir, exist_ok=True)
        manifest_path = os.path.join(cfg.out_dir, "manifest.json")
        input_hash = file_sha256(cfg.input_path)
        registry_hash = (
            file_sha256(cfg.alias_registry_path) if os.path.exists(cfg.alias_registry_path) else ""
        )

        if not cfg.force and os.path.exists(manifest_path):
            try:
                previous = NormalizationManifest(**read_json(manifest_path))
                if (
                    previous.input_sha256 == input_hash
                    and previous.alias_registry_sha256 == registry_hash
                    and previous.normalizer_version == NORMALIZER_VERSION
                ):
                    return previous
            except Exception:
                pass

        raw_records = read_jsonl(cfg.input_path)
        alias_registry = load_alias_registry(cfg.alias_registry_path)

        universities, index_map = UniversityResolver(alias_registry).resolve(raw_records)
        programs = ProgramNormalizer().normalize(raw_records, index_map)

        self._write_outputs(cfg.out_dir, universities, programs)
        manifest = self._build_manifest(cfg, input_hash, registry_hash, len(raw_records), universities, programs)
        write_json(manifest_path, manifest)
        return manifest

    # -- output --------------------------------------------------------------
    def _write_outputs(
        self,
        out_dir: str,
        universities: List[CanonicalUniversity],
        programs: List[CanonicalProgram],
    ) -> None:
        write_jsonl(os.path.join(out_dir, "universities.jsonl"), universities)
        write_jsonl(os.path.join(out_dir, "programs.jsonl"), programs)
        index = {
            u.university_id: {
                "canonical_name": u.canonical_name,
                "country": u.country,
                "city": u.city,
                "official_domain": u.official_domain,
                "qs_rank": u.qs.university_rank,
                "qs_rank_display": u.qs.rank_display,
                "aliases": [a.alias for a in u.aliases],
                "needs_review": u.needs_review,
            }
            for u in universities
        }
        write_json(os.path.join(out_dir, "universities.json"), index)

    @staticmethod
    def _build_manifest(
        cfg: NormalizeConfig,
        input_hash: str,
        registry_hash: str,
        input_rows: int,
        universities: List[CanonicalUniversity],
        programs: List[CanonicalProgram],
    ) -> NormalizationManifest:
        by_degree = Counter(p.degree_type.value for p in programs)
        by_format = Counter(p.program_format.value for p in programs)
        by_country = Counter(
            (p.location.country or "UNKNOWN") for p in programs
        )
        return NormalizationManifest(
            input_path=cfg.input_path,
            input_sha256=input_hash,
            alias_registry_sha256=registry_hash,
            input_rows=input_rows,
            normalizer_version=NORMALIZER_VERSION,
            schema_version=NORMALIZE_SCHEMA_VERSION,
            generated_at=utcnow(),
            universities=len(universities),
            programs=len(programs),
            programs_deduplicated=input_rows - len(programs),
            universities_needing_review=sum(1 for u in universities if u.needs_review),
            programs_by_degree=dict(by_degree.most_common()),
            programs_by_format=dict(by_format.most_common()),
            programs_by_country=dict(by_country.most_common(30)),
        )
