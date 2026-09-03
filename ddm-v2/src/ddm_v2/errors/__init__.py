"""Central error-code registry package (ADR-034 §D3).

Re-exports :class:`ErrorCode` so callers can do ``from ddm_v2.errors import ErrorCode``.
"""

from __future__ import annotations

from ddm_v2.errors.registry import ErrorCode

__all__ = ["ErrorCode"]
