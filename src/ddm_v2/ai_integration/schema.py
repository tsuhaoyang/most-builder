"""ai_service 輸出 schema 的 MOST 端複本（ADR-037 D2）。

ai_service 的 `structured-completion` 要求呼叫端送 `json_schema`（服務端用來驗證模型輸出，
不送給模型；ai_service ADR-002 D3）。MOST 持有一份複本 `schemas/wi-motion-parse.schema.json`，
來源與版本：

- 來源：`~/workspace/ai_service` 的 `packs/most/schemas/` 下對應 bundle 的檔案（見 `SCHEMAS`）
- poc003：`wi-motion-parse.schema.json`，commit `df399fc`（2026-11-14 複製）
- poc004：`wi-motion-parse.constrained.schema.json`，commit `7560d0d`（2026-11-27 複製；S-086 約束解碼）

複本是漂移風險：ai_service 改 schema＝發新 bundle code（ai_service ADR-011 D5）。換 bundle 時
必須在 `SCHEMAS` 加上該 bundle 的複本、sha256 與來源 commit；`tests/contract/ai_service/` 會在 hash 不符時變紅。
已向 ai_service 提出「bundle 改用內建 schema 或提供 schema hash 查詢」（實作計畫 §7 第 3 項）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VendoredSchema:
    path: Path
    sha256: str
    source_commit: str


_DIR = Path(__file__).parent / "schemas"

# bundle code → 送給 ai_service 的 json_schema 複本。約束解碼（poc004 起）用的是**呼叫端送的** schema，
# 送錯 bundle 的 schema 會被拒（ai_service 2026-11-27 通知：poc004 收舊 schema 會拒；schema 送錯時 Ollama 回 400，
# ai_service 轉成 502 PROVIDER_UNREACHABLE，不要誤認成 Ollama 掉線）。換 bundle 只改 `DDM_AI_SERVICE_BUNDLE_CODE`，複本由這張表依 bundle 選。
# 新增 bundle：從 ai_service `main` 複製 pack 檔、填 sha256 與 commit；`tests/contract/ai_service/` 會驗 hash 與 code 清單。
SCHEMAS: dict[str, VendoredSchema] = {
    "most-wi-motion-parse-poc003": VendoredSchema(
        _DIR / "wi-motion-parse.schema.json",
        "180c72803551c50192f596dc5974a8595362a65aa077ef603fea7845ca5442a3",
        "df399fc",
    ),
    # S-086：motion 改 oneOf（GM／CM 分開），response_format=json_schema 約束解碼；輸出形狀與 poc003 相同
    "most-wi-motion-parse-poc004": VendoredSchema(
        _DIR / "wi-motion-parse.constrained.schema.json",
        "71d2157ded5d364c3144635f02c630f8ddbb2e2586df411e9ab7eb5df3828a5c",
        "7560d0d",
    ),
}

# 相容舊名（poc003）：既有測試與量測腳本引用
SCHEMA_PATH = SCHEMAS["most-wi-motion-parse-poc003"].path
SCHEMA_SHA256 = SCHEMAS["most-wi-motion-parse-poc003"].sha256
SCHEMA_SOURCE_COMMIT = SCHEMAS["most-wi-motion-parse-poc003"].source_commit
DEFAULT_SCHEMA_BUNDLE = "most-wi-motion-parse-poc003"


class UnknownSchemaBundle(LookupError):
    """設定的 bundle code 沒有對應的 schema 複本（不猜、不退回別的 schema）。"""


def _entry(bundle_code: str) -> VendoredSchema:
    try:
        return SCHEMAS[bundle_code]
    except KeyError:
        raise UnknownSchemaBundle(bundle_code) from None


def schema_sha256(bundle_code: str = DEFAULT_SCHEMA_BUNDLE) -> str:
    return hashlib.sha256(_entry(bundle_code).path.read_bytes()).hexdigest()


@lru_cache(maxsize=8)
def _load(bundle_code: str) -> str:
    e = _entry(bundle_code)
    raw = e.path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != e.sha256:
        # fail-fast：複本被改過卻沒更新釘值，送出去的 schema 與宣稱的不是同一份
        raise RuntimeError(f"wi-motion-parse schema hash mismatch for {bundle_code}: {actual} != pinned {e.sha256}")
    return raw.decode("utf-8")


def wi_motion_parse_schema(bundle_code: str = DEFAULT_SCHEMA_BUNDLE) -> dict[str, Any]:
    """每次回傳新的 dict（呼叫端可修改，不影響快取）。"""
    return json.loads(_load(bundle_code))
