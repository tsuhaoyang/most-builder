"""LB 投影層（`lb_projection`）：MOST worksheet → LB task CSV 的確定性翻譯。

最高原則：`docs/lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md`（`most-lb-csv-v1.1`）。
邊界：`docs/decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md`。

本層**不 import** SQLAlchemy／FastAPI；唯一外部相依是 `most_engine`（TMU 重算）與
`most_engine.level.validate`（實作書 §1）。DB 存取（load_vocab）留在 `services/v2/export_service.py`。

WP0：僅公開表頭凍結所需的 `COLUMNS`／`CONTRACT_VERSION`。其餘公開 API（project_worksheet、
project_rows）於後續 WP 落地。
"""
from __future__ import annotations

from ddm_v2.lb_projection.emit import COLUMNS, CONTRACT_VERSION

__all__ = ["COLUMNS", "CONTRACT_VERSION"]
