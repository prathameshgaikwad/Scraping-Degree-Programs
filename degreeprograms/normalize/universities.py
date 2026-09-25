"""Canonical university resolution.

Primary signal: the QS ``university_url`` path encodes the parent university
slug before any organizational-unit slug, e.g.::

    /universities/university-warwick/wmg-warwick-manufacturing-group
                    ^ parent slug        ^ org unit

So ``"WMG - Warwick Manufacturing Group"`` deterministically groups under
``university-warwick`` together with the ``"University of Warwick"`` record.

Secondary signals (in order): curated alias registry, exact normalized-name
match, conservative fuzzy match (same country, high similarity, flagged for
review). Anything uncertain is retained separately and marked ``needs_review``
rather than silently merged.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .io import raw_record_hash
from .models import (
    CanonicalUniversity,
    Ranking,
    ResolutionMethod,
    SourceRef,
    UniversityAlias,
)
from .text import (
    base_university_slug,
    clean_unicode,
    first_multi,
    normalize_name,
    parse_ranking,
    qs_path_segments,
    slugify,
)

_CAMPUS_HINT_WORDS = ("campus", "school", "college", "institute", "faculty", "department", "centre", "center")
_STREET_RE = re.compile(r"\d")
_COUNTRY_CODE_TAIL_RE = re.compile(r",\s*[A-Z]{2}\s*$")


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


@dataclass
class _Record:
    index: int
    name: str
    campus: str
    country: Optional[str]
    city: Optional[str]
    rank_raw: str
    entity_depth: int
    alias_target: Optional[str]
    source: SourceRef


@dataclass
class _Group:
    key: str
    records: List[_Record] = field(default_factory=list)

    def names(self) -> List[str]:
        return [r.name for r in self.records if r.name]

    def base_names(self) -> List[str]:
        return [r.name for r in self.records if r.entity_depth == 1 and r.name]

    def alias_targets(self) -> List[str]:
        return [r.alias_target for r in self.records if r.alias_target]

    def countries(self) -> List[str]:
        return [r.country for r in self.records if r.country]

    def preferred_canonical(self) -> str:
        base = self.base_names()
        if base:
            return Counter(base).most_common(1)[0][0]
        targets = self.alias_targets()
        if targets:
            return Counter(targets).most_common(1)[0][0]
        names = self.names()
        if names:
            return Counter(names).most_common(1)[0][0]
        return self.key.replace("-", " ").title()


class UniversityResolver:
    def __init__(self, alias_registry: Optional[Dict[str, Any]] = None) -> None:
        registry = alias_registry or {}
        self.alias_lookup: Dict[str, str] = {
            normalize_name(k): clean_unicode(v) for k, v in (registry.get("aliases") or {}).items()
        }
        self.domains: Dict[str, str] = {
            normalize_name(k): clean_unicode(v) for k, v in (registry.get("domains") or {}).items()
        }

    # -- public --------------------------------------------------------------
    def resolve(
        self, raw_records: List[Dict[str, Any]]
    ) -> Tuple[List[CanonicalUniversity], Dict[int, str]]:
        groups = self._group(raw_records)
        uf = self._merge_exact(groups)
        uf = self._merge_fuzzy(groups, uf)
        universities, index_map = self._build(groups, uf)
        return universities, index_map

    # -- grouping ------------------------------------------------------------
    def _group(self, raw_records: List[Dict[str, Any]]) -> List[_Group]:
        buckets: Dict[str, _Group] = {}
        for idx, rec in enumerate(raw_records):
            name = clean_unicode(rec.get("university_name"))
            slug = base_university_slug(rec.get("university_url"))
            key = slug or f"name:{slugify(name)}"
            segments = qs_path_segments(rec.get("university_url"))
            entity_depth = len(segments) - 1 if segments and segments[0] == "universities" else 0
            record = _Record(
                index=idx,
                name=name,
                campus=clean_unicode(rec.get("campus_name")),
                country=first_multi(rec.get("country")),
                city=first_multi(rec.get("city")),
                rank_raw=clean_unicode(rec.get("rankings_position")),
                entity_depth=entity_depth,
                alias_target=self.alias_lookup.get(normalize_name(name)),
                source=SourceRef(
                    raw_index=idx,
                    raw_record_hash=raw_record_hash(rec),
                    program_url=rec.get("program_url"),
                    university_url=rec.get("university_url"),
                    source_search_url=rec.get("source_search_url"),
                ),
            )
            buckets.setdefault(key, _Group(key=key)).records.append(record)
        return list(buckets.values())

    # -- merging -------------------------------------------------------------
    def _merge_exact(self, groups: List[_Group]) -> _UnionFind:
        uf = _UnionFind(len(groups))
        by_name: Dict[str, int] = {}
        for i, group in enumerate(groups):
            key = normalize_name(group.preferred_canonical())
            if key in by_name:
                uf.union(i, by_name[key])
            else:
                by_name[key] = i
        return uf

    def _merge_fuzzy(self, groups: List[_Group], uf: _UnionFind, threshold: float = 0.95) -> _UnionFind:
        keys = [normalize_name(g.preferred_canonical()) for g in groups]
        countries = [self._dominant_country(g) for g in groups]
        for i in range(len(groups)):
            if not keys[i]:
                continue
            for j in range(i + 1, len(groups)):
                if uf.find(i) == uf.find(j):
                    continue
                if countries[i] and countries[j] and countries[i] != countries[j]:
                    continue
                if abs(len(keys[i]) - len(keys[j])) > 12:
                    continue
                ratio = difflib.SequenceMatcher(None, keys[i], keys[j]).ratio()
                if ratio >= threshold:
                    uf.union(i, j)
        return uf

    # -- building ------------------------------------------------------------
    def _build(
        self, groups: List[_Group], uf: _UnionFind
    ) -> Tuple[List[CanonicalUniversity], Dict[int, str]]:
        components: Dict[int, List[int]] = defaultdict(list)
        for i in range(len(groups)):
            components[uf.find(i)].append(i)

        universities: List[CanonicalUniversity] = []
        index_map: Dict[int, str] = {}
        for members in components.values():
            records = [r for gi in members for r in groups[gi].records]
            canonical_name, name_method, name_review = self._choose_name(groups, members)
            if len(members) > 1:
                distinct = {normalize_name(groups[gi].preferred_canonical()) for gi in members}
                if len(distinct) > 1:
                    name_method = ResolutionMethod.FUZZY_NAME
                    name_review = list(name_review) + ["fuzzy_merge"]
                else:
                    name_method = ResolutionMethod.EXACT_NAME
            university_id = slugify(canonical_name)
            country = self._mode([r.country for r in records])
            city = self._mode([r.city for r in records])
            domain = self._domain_for(canonical_name, records)
            ranking = self._ranking_for(records)

            review_reasons: List[str] = list(name_review)
            countries = {r.country for r in records if r.country}
            if len(countries) > 1:
                review_reasons.append(f"multiple_countries:{sorted(countries)}")
            if name_method == ResolutionMethod.FUZZY_NAME:
                review_reasons.append("fuzzy_merge")

            university = CanonicalUniversity(
                university_id=university_id,
                canonical_name=canonical_name,
                aliases=self._aliases(canonical_name, records),
                country=country,
                city=city,
                official_domain=domain,
                qs=ranking,
                resolution_method=name_method,
                confidence=self._confidence(name_method, len(countries), bool(domain)),
                needs_review=bool(review_reasons),
                review_reasons=review_reasons,
                source_refs=[r.source for r in records],
            )
            universities.append(university)
            for record in records:
                index_map[record.index] = university_id

        universities.sort(key=lambda u: u.canonical_name)
        return universities, index_map

    def _choose_name(
        self, groups: List[_Group], members: List[int]
    ) -> Tuple[str, ResolutionMethod, List[str]]:
        base_names: List[str] = []
        target_names: List[str] = []
        all_names: List[str] = []
        for gi in members:
            base_names.extend(groups[gi].base_names())
            target_names.extend(groups[gi].alias_targets())
            all_names.extend(groups[gi].names())

        if base_names:
            return Counter(base_names).most_common(1)[0][0], ResolutionMethod.QS_BASE_SLUG, []
        if target_names:
            return Counter(target_names).most_common(1)[0][0], ResolutionMethod.ALIAS_REGISTRY, []
        if all_names:
            return Counter(all_names).most_common(1)[0][0], ResolutionMethod.EXACT_NAME, []
        # No real name available: derive from slug and flag.
        key = groups[members[0]].key.replace("name:", "")
        return key.replace("-", " ").title(), ResolutionMethod.FALLBACK_SLUG, ["name_derived_from_slug"]

    def _aliases(self, canonical_name: str, records: List[_Record]) -> List[UniversityAlias]:
        aliases: Dict[str, UniversityAlias] = {}
        aliases[normalize_name(canonical_name)] = UniversityAlias(
            alias=canonical_name,
            normalized=normalize_name(canonical_name),
            kind="CANONICAL",
            source="curated",
            confidence=1.0,
        )

        def add(alias: str, kind: str, source: str, confidence: float) -> None:
            alias = clean_unicode(alias)
            if not alias:
                return
            norm = normalize_name(alias)
            if not norm or norm in aliases:
                return
            aliases[norm] = UniversityAlias(
                alias=alias, normalized=norm, kind=kind, source=source, confidence=confidence
            )

        for record in records:
            kind = "ORG_UNIT" if record.entity_depth >= 2 else "RAW_UNIVERSITY_NAME"
            add(record.name, kind, "QS", 0.9 if kind == "RAW_UNIVERSITY_NAME" else 0.85)
            if record.alias_target:
                add(record.alias_target, "KNOWN", "curated", 0.95)
            if self._looks_like_campus(record.campus, canonical_name):
                add(record.campus, "CAMPUS", "QS", 0.6)
        return sorted(aliases.values(), key=lambda a: a.alias.lower())

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _looks_like_campus(campus: str, canonical_name: str) -> bool:
        if not campus or len(campus) > 60:
            return False
        if _STREET_RE.search(campus):
            return False
        if _COUNTRY_CODE_TAIL_RE.search(campus):
            return False
        low = campus.lower()
        if any(word in low for word in _CAMPUS_HINT_WORDS):
            return True
        name_tokens = set(normalize_name(canonical_name).split())
        campus_tokens = set(normalize_name(campus).split())
        return bool(name_tokens & campus_tokens)

    @staticmethod
    def _mode(values: List[Optional[str]]) -> Optional[str]:
        cleaned = [v for v in values if v]
        if not cleaned:
            return None
        return Counter(cleaned).most_common(1)[0][0]

    @staticmethod
    def _dominant_country(group: _Group) -> Optional[str]:
        return UniversityResolver._mode(group.countries())

    def _domain_for(self, canonical_name: str, records: List[_Record]) -> Optional[str]:
        candidates = [canonical_name]
        for record in records:
            candidates.append(record.name)
            if record.alias_target:
                candidates.append(record.alias_target)
        for candidate in candidates:
            domain = self.domains.get(normalize_name(candidate))
            if domain:
                return domain
        return None

    @staticmethod
    def _ranking_for(records: List[_Record]) -> Ranking:
        base = [r.rank_raw for r in records if r.entity_depth == 1 and r.rank_raw]
        pool = base or [r.rank_raw for r in records if r.rank_raw]
        if not pool:
            return Ranking()
        raw = Counter(pool).most_common(1)[0][0]
        parsed = parse_ranking(raw)
        return Ranking(
            university_rank=parsed["university_rank"],
            rank_display=parsed["rank_display"],
            rank_low=parsed["rank_low"],
            rank_high=parsed["rank_high"],
            tied=parsed["tied"],
            is_range=parsed["is_range"],
            is_plus=parsed["is_plus"],
        )

    @staticmethod
    def _confidence(method: ResolutionMethod, country_count: int, has_domain: bool) -> float:
        base = {
            ResolutionMethod.QS_BASE_SLUG: 0.95,
            ResolutionMethod.ALIAS_REGISTRY: 0.9,
            ResolutionMethod.EXACT_NAME: 0.85,
            ResolutionMethod.FUZZY_NAME: 0.65,
            ResolutionMethod.FALLBACK_SLUG: 0.5,
        }.get(method, 0.5)
        if country_count > 1:
            base -= 0.15
        if has_domain:
            base += 0.03
        return round(min(max(base, 0.0), 1.0), 3)
