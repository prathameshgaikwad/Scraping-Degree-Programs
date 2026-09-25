"""Canonical program normalization and deduplication.

Deduplication identity is conservative and explicit::

    canonical university_id
    + normalized program name
    + degree type

Only exact identity matches are merged (``DedupConfidence.HIGH``); near-matches
are deliberately left as separate records so nothing is silently collapsed.
Every canonical program keeps ``merged_sources`` pointing back to each raw
record it was built from.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .io import raw_record_hash
from .models import (
    CanonicalProgram,
    DedupConfidence,
    DegreeLevel,
    DegreeType,
    ProgramFormat,
    ProgramLocation,
    Ranking,
    SourceRef,
)
from .text import (
    clean_unicode,
    extract_degree_tokens,
    first_multi,
    normalize_name,
    parse_degree_type,
    parse_program_format,
    parse_ranking,
    slugify,
)

_LEVEL_BY_DEGREE = {
    DegreeType.PGDIP: DegreeLevel.POSTGRADUATE_DIPLOMA,
    DegreeType.PGCERT: DegreeLevel.POSTGRADUATE_CERTIFICATE,
}


@dataclass
class _Candidate:
    index: int
    program: CanonicalProgram


class ProgramNormalizer:
    def normalize(
        self,
        raw_records: List[Dict[str, Any]],
        index_to_university_id: Dict[int, str],
    ) -> List[CanonicalProgram]:
        groups: Dict[Tuple[str, str, str], List[_Candidate]] = defaultdict(list)
        for idx, record in enumerate(raw_records):
            university_id = index_to_university_id.get(idx)
            if not university_id:
                continue
            program = self._to_program(idx, record, university_id)
            key = (program.university_id, program.normalized_name, program.degree_type.value)
            groups[key].append(_Candidate(index=idx, program=program))

        canonical: List[CanonicalProgram] = []
        used_ids: Dict[str, int] = {}
        for key, candidates in groups.items():
            candidates.sort(key=lambda c: self._primary_score(c), reverse=True)
            primary = candidates[0].program
            sources = [c.program.source for c in candidates]
            primary.merged_sources = sources
            primary.is_primary = True
            primary.duplicate_of = None
            primary.dedup_confidence = DedupConfidence.HIGH
            primary.program_id = self._unique_program_id(primary, used_ids)
            primary.dedup_group_id = primary.program_id
            canonical.append(primary)

        canonical.sort(key=lambda p: (p.university_id, p.normalized_name))
        return canonical

    # -- helpers -------------------------------------------------------------
    def _to_program(self, idx: int, record: Dict[str, Any], university_id: str) -> CanonicalProgram:
        raw_name = clean_unicode(record.get("name"))
        normalized = normalize_name(raw_name)
        degree_type = parse_degree_type(raw_name)
        tokens = extract_degree_tokens(raw_name)
        level = _LEVEL_BY_DEGREE.get(DegreeType(degree_type), DegreeLevel.MASTER)

        location = ProgramLocation(
            campus=clean_unicode(record.get("campus_name")) or None,
            city=first_multi(record.get("city")),
            country=first_multi(record.get("country")),
            region=first_multi(record.get("region")),
        )
        ranking = Ranking(**parse_ranking(record.get("rankings_position")))
        source = SourceRef(
            raw_index=idx,
            raw_record_hash=raw_record_hash(record),
            program_url=record.get("program_url"),
            university_url=record.get("university_url"),
            source_search_url=record.get("source_search_url"),
        )
        return CanonicalProgram(
            program_id="",  # assigned after dedup
            university_id=university_id,
            name=raw_name,
            normalized_name=normalized,
            degree_level=level,
            degree_type=DegreeType(degree_type),
            degree_tokens=tokens,
            program_format=ProgramFormat(parse_program_format(raw_name)),
            location=location,
            source=source,
            ranking=ranking,
            dedup_group_id="",
            raw_name=record.get("name"),
        )

    @staticmethod
    def _primary_score(candidate: _Candidate) -> Tuple:
        program = candidate.program
        return (
            int(bool(program.location.country)),
            int(bool(program.location.city)),
            int(program.ranking.university_rank is not None or bool(program.ranking.rank_display)),
            int(bool(program.source.program_url)),
            -candidate.index,
        )

    @staticmethod
    def _unique_program_id(program: CanonicalProgram, used: Dict[str, int]) -> str:
        base = f"{program.university_id}__{slugify(program.normalized_name)}"
        if program.degree_type not in (DegreeType.UNKNOWN, DegreeType.MASTER):
            base = f"{base}__{program.degree_type.value.lower()}"
        if base not in used:
            used[base] = 1
            return base
        used[base] += 1
        suffix = hashlib.sha1(program.source.raw_record_hash.encode("utf-8")).hexdigest()[:6]
        return f"{base}__{suffix}"
