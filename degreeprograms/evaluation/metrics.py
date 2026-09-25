"""Classification metrics: accuracy, per-class precision/recall/F1, confusion.

Distinguishes a correct value from a correct source by being applied separately
to value-level predictions (classification, eligibility) and source-level
predictions (evidence attachment).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .models import ClassMetric, EvaluationMetric


def compute_metric(name: str, pairs: List[Tuple[str, str]], errors: List[str] = None) -> EvaluationMetric:
    """``pairs`` is a list of (expected, predicted) labels."""
    n = len(pairs)
    labels = sorted({label for pair in pairs for label in pair})
    confusion: Dict[str, Dict[str, int]] = {label: {} for label in labels}
    correct = 0
    tp: Dict[str, int] = {label: 0 for label in labels}
    fp: Dict[str, int] = {label: 0 for label in labels}
    fn: Dict[str, int] = {label: 0 for label in labels}

    for expected, predicted in pairs:
        confusion.setdefault(expected, {})
        confusion[expected][predicted] = confusion[expected].get(predicted, 0) + 1
        if expected == predicted:
            correct += 1
            tp[expected] += 1
        else:
            fp[predicted] = fp.get(predicted, 0) + 1
            fn[expected] = fn.get(expected, 0) + 1

    per_class: Dict[str, ClassMetric] = {}
    f1s: List[float] = []
    for label in labels:
        precision = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) else 0.0
        recall = tp[label] / (tp[label] + fn[label]) if (tp[label] + fn[label]) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        support = tp[label] + fn[label]
        per_class[label] = ClassMetric(
            precision=round(precision, 4), recall=round(recall, 4), f1=round(f1, 4), support=support
        )
        if support > 0:
            f1s.append(f1)

    macro_f1 = round(sum(f1s) / len(f1s), 4) if f1s else 0.0
    return EvaluationMetric(
        name=name,
        n=n,
        accuracy=round(correct / n, 4) if n else 0.0,
        macro_f1=macro_f1,
        per_class=per_class,
        confusion=confusion,
        errors=errors or [],
    )
