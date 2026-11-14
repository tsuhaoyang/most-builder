"""ai_service 輸出 schema 的 MOST 端複本（ADR-037 D2）。

ai_service 的 `structured-completion` 要求呼叫端送 `json_schema`（服務端用來驗證模型輸出，
不送給模型；ai_service ADR-002 D3）。MOST 持有一份複本 `schemas/wi-motion-parse.schema.json`，
來源與版本：

- 來源：`~/workspace/ai_service` 的 `packs/most/schemas/wi-motion-parse.schema.json`
- 取自：ai_service `main` 上最後修改該檔的 commit `df399fc`（2026-11-14 複製）
- sha256：見 `SCHEMA_SHA256`

複本是漂移風險：ai_service 改 schema＝發新 bundle code（ai_service ADR-011 D5）。換 bundle 時
必須同步更新這份檔案與 `SCHEMA_SHA256`；`tests/contract/ai_service/` 會在 hash 不符時變紅。
已向 ai_service 提出「bundle 改用內建 schema 或提供 schema hash 查詢」（實作計畫 §7 第 3 項）。
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "schemas" / "wi-motion-parse.schema.json"
SCHEMA_SHA256 = "180c72803551c50192f596dc5974a8595362a65aa077ef603fea7845ca5442a3"
SCHEMA_SOURCE_COMMIT = "df399fc"


def schema_sha256() -> str:
    return hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _load() -> str:
    raw = SCHEMA_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SCHEMA_SHA256:
        # fail-fast：複本被改過卻沒更新釘值，送出去的 schema 與宣稱的不是同一份
        raise RuntimeError(f"wi-motion-parse schema hash mismatch: {actual} != pinned {SCHEMA_SHA256}")
    return raw.decode("utf-8")


def wi_motion_parse_schema() -> dict[str, Any]:
    """每次回傳新的 dict（呼叫端可修改，不影響快取）。"""
    return json.loads(_load())
