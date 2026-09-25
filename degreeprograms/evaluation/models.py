"""Evaluation report models."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ClassMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    support: int = 0


class EvaluationMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    n: int = 0
    accuracy: float = 0.0
    macro_f1: float = 0.0
    per_class: Dict[str, ClassMetric] = Field(default_factory=dict)
    confusion: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generated_at: str
    evaluation_version: str
    metrics: List[EvaluationMetric] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    artifacts: Dict[str, Optional[str]] = Field(default_factory=dict)
