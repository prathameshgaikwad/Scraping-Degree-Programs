"""Program relevance taxonomy (Phase 3).

Deterministic, applicant-independent. Fields are the spec's AI/ML/CS/Data
taxonomy plus DATA_ANALYTICS. Weights: STRONG=4, MEDIUM=2, WEAK=1.

Classification considers the program title in this phase. Later phases can
re-classify using official descriptions/curriculum (``basis`` records what was
used), and the rules below are intentionally explicit so they can be audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

STRONG = 4
MEDIUM = 2
WEAK = 1

# Field codes (kept stable; used in output and matching).
F_AI = "ARTIFICIAL_INTELLIGENCE"
F_ML = "MACHINE_LEARNING"
F_DS = "DATA_SCIENCE"
F_DA = "DATA_ANALYTICS"
F_CS = "COMPUTER_SCIENCE"
F_ROB = "ROBOTICS"
F_CV = "COMPUTER_VISION"
F_NLP = "NLP"
F_IS = "INTELLIGENT_SYSTEMS"
F_AENG = "AI_ENGINEERING"
F_COMP = "COMPUTATIONAL_SCIENCE"
F_UNKNOWN = "UNKNOWN"

# Order doubles as tie-break priority (lower index wins).
FIELD_ORDER: List[str] = [F_AI, F_ML, F_DS, F_DA, F_CS, F_ROB, F_CV, F_NLP, F_IS, F_AENG, F_COMP]

CORE_FIELDS = {F_AI, F_ML, F_DS, F_DA, F_CS}
RELATED_FIELDS = {F_ROB, F_CV, F_NLP, F_IS, F_AENG, F_COMP}

FIELD_LABELS: Dict[str, str] = {
    F_AI: "Artificial Intelligence",
    F_ML: "Machine Learning",
    F_DS: "Data Science",
    F_DA: "Data Analytics",
    F_CS: "Computer Science",
    F_ROB: "Robotics",
    F_CV: "Computer Vision",
    F_NLP: "Natural Language Processing",
    F_IS: "Intelligent Systems",
    F_AENG: "AI Engineering",
    F_COMP: "Computational Science",
    F_UNKNOWN: "Unknown",
}


@dataclass(frozen=True)
class FieldSpec:
    code: str
    keywords: Tuple[Tuple[str, int], ...]


TAXONOMY: Tuple[FieldSpec, ...] = (
    FieldSpec(
        F_AI,
        (
            ("artificial intelligence", STRONG),
            ("generative ai", STRONG),
            ("applied ai", STRONG),
            ("ai", STRONG),
            ("ai and", STRONG),
            ("and ai", STRONG),
            ("ai for", STRONG),
            ("ai with", STRONG),
            ("ai systems", MEDIUM),
            ("ai strategy", MEDIUM),
            ("ai ethics", MEDIUM),
            ("ai applications", MEDIUM),
            ("machine intelligence", MEDIUM),
            ("knowledge based systems", MEDIUM),
        ),
    ),
    FieldSpec(
        F_ML,
        (
            ("machine learning", STRONG),
            ("deep learning", STRONG),
            ("neural networks", STRONG),
            ("neural network", STRONG),
            ("reinforcement learning", STRONG),
            ("statistical learning", STRONG),
            ("pattern recognition", STRONG),
            ("representation learning", STRONG),
            ("transfer learning", STRONG),
            ("machine intelligence", MEDIUM),
        ),
    ),
    FieldSpec(
        F_DS,
        (
            ("data science", STRONG),
            ("big data", STRONG),
            ("data mining", STRONG),
            ("data engineering", STRONG),
            ("data visualisation", STRONG),
            ("data visualization", STRONG),
            ("data analysis", STRONG),
            ("data driven", STRONG),
            ("data science for", STRONG),
            ("applied data", MEDIUM),
            ("data", WEAK),
        ),
    ),
    FieldSpec(
        F_DA,
        (
            ("analytics", STRONG),
            ("business intelligence", STRONG),
            ("business analytics", STRONG),
            ("data analytics", STRONG),
        ),
    ),
    FieldSpec(
        F_CS,
        (
            ("computer science", STRONG),
            ("computing science", STRONG),
            ("computer engineering", STRONG),
            ("informatics", STRONG),
            ("software engineering", STRONG),
            ("information technology", STRONG),
            ("computer applications", STRONG),
            ("computer information systems", STRONG),
            ("computing", MEDIUM),
            ("computer", MEDIUM),
            ("software", MEDIUM),
            ("information systems", MEDIUM),
            ("programming", MEDIUM),
        ),
    ),
    FieldSpec(
        F_ROB,
        (
            ("robotics", STRONG),
            ("robot", STRONG),
            ("mechatronics", STRONG),
            ("autonomous systems", STRONG),
            ("autonomous vehicles", STRONG),
            ("unmanned", STRONG),
            ("advanced robotics", STRONG),
            ("automation", MEDIUM),
            ("control", MEDIUM),
            ("autonomous", MEDIUM),
            ("embedded", WEAK),
        ),
    ),
    FieldSpec(
        F_CV,
        (
            ("computer vision", STRONG),
            ("image processing", STRONG),
            ("image analysis", STRONG),
            ("visual computing", STRONG),
            ("machine vision", STRONG),
            ("vision", MEDIUM),
            ("imaging", MEDIUM),
            ("graphics", MEDIUM),
        ),
    ),
    FieldSpec(
        F_NLP,
        (
            ("natural language processing", STRONG),
            ("computational linguistics", STRONG),
            ("language technology", STRONG),
            ("natural language", STRONG),
            ("speech processing", STRONG),
            ("language", WEAK),
            ("linguistics", WEAK),
            ("speech", WEAK),
        ),
    ),
    FieldSpec(
        F_IS,
        (
            ("intelligent systems", STRONG),
            ("intelligent technology", STRONG),
            ("intelligent autonomous", STRONG),
            ("intelligent agents", STRONG),
            ("multi agent", STRONG),
            ("autonomous intelligent", STRONG),
            ("cognitive systems", STRONG),
            ("intelligent control", STRONG),
            ("intelligent", MEDIUM),
            ("autonomous", MEDIUM),
            ("cognitive", MEDIUM),
        ),
    ),
    FieldSpec(
        F_AENG,
        (
            ("ai engineering", STRONG),
            ("machine learning engineering", STRONG),
            ("mlops", STRONG),
            ("ai systems", STRONG),
            ("ai software", STRONG),
        ),
    ),
    FieldSpec(
        F_COMP,
        (
            ("computational science", STRONG),
            ("scientific computing", STRONG),
            ("computational engineering", STRONG),
            ("computational mathematics", STRONG),
            ("high performance computing", STRONG),
            ("computational physics", STRONG),
            ("computational chemistry", STRONG),
            ("computational biology", STRONG),
            ("simulation", MEDIUM),
            ("computational", MEDIUM),
            ("modelling", WEAK),
            ("modeling", WEAK),
        ),
    ),
)


def field_priority(code: str) -> int:
    try:
        return FIELD_ORDER.index(code)
    except ValueError:
        return len(FIELD_ORDER)
