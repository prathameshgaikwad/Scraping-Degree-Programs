"""Phase 2 normalization layer.

Turns raw QS discovery records into canonical universities and programs.
Raw data is read-only; normalized output lives under ``data/normalized``.
"""

from .versions import NORMALIZE_SCHEMA_VERSION, NORMALIZER_VERSION

__all__ = ["NORMALIZER_VERSION", "NORMALIZE_SCHEMA_VERSION"]
