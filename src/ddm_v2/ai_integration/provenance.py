"""外部 ai_service 的 `provenance` 落 DB／回 API 前的鍵 allow-list（ADR-037 D7）。

`ai_parse_runs.provenance` 是無 schema 的 JSONB：欄位本身不會替我們擋下不該存的東西，所以寫入端必須自己有
**鍵的 allow-list**。金鑰、員工編號、原文、ai_service 的 `error.message` 一律不得進來。

兩組鍵、來源不同，處理也不同：

- **ai_service 的出處**（`AI_SERVICE_KEYS`）：來自 adapter／guard 的輸出，再逐鍵過濾——只收純量
  （str／int／float／None），字串限長。其他一律丟掉，並回報被丟的鍵名（鍵名是 adapter 固定的，不是外部字串）。
- **MOST 自己組的**（`MOST_OWNED_KEYS`）：`motion_labels`、`dropped`。內容由 `plan_adapter` 組出，文字已經
  mapper 清理並限長；這裡只驗形狀，不接受任何來自外部 provenance 的同名鍵。
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

MAX_TEXT_LEN = 200  # 審核用的語意文字（mapper 已清理並限長）
MAX_IDENT_LEN = 128  # ai_service 出處的識別類字串（與 client 的 `_SAFE_TEXT_RE` 同一個規則）
MAX_MOTION_LABELS = 20  # 與 mapper.MAX_MOTIONS 一致
MAX_DROPPED = 100

# 出處的字串值只准識別字元：換掉 port 實作也不能經它帶進 HTML、控制字元或 log 注入
_IDENT_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{1,128}$")
_ACTION_ID_RE = re.compile(r"^a\d{1,3}$")
_DROPPED_RE = re.compile(r"^a\d{1,3}:[A-Za-z0-9_.]{1,40}$")
_HANDS = frozenset({"LH", "RH", "BH"})

# 與 `adapter.py`（成功／失敗）與 `guard.py`（等待者、本地拒絕）實際輸出的鍵一致
AI_SERVICE_KEYS: frozenset[str] = frozenset(
    {
        "request_id",
        "run_id",
        "shared_run_id",
        "bundle_code",
        "bundle_status",
        "model_served",
        "prompt_variant",
        "prompt_version",
        "retry_count",
        "attempts",
        "latency_ms",
        "upstream_code",
        "http_status",
    }
)
MOST_OWNED_KEYS: frozenset[str] = frozenset({"motion_labels", "dropped"})
ALLOWED_KEYS: frozenset[str] = AI_SERVICE_KEYS | MOST_OWNED_KEYS

_LABEL_KEYS = frozenset({"action_id", "sub_activity", "object_text", "hand_hint"})


def _clean_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return not (isinstance(value, float) and not math.isfinite(value))  # NaN／Inf 寫不進 JSONB
    return isinstance(value, str) and _IDENT_RE.fullmatch(value) is not None


def sanitize_ai_service_provenance(raw: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """回傳 (乾淨的出處, 被丟掉的鍵名)。不在 allow-list、值不是純量、字串不是識別字元或過長、非有限數值的都丟。"""
    clean: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in (raw or {}).items():
        if key not in AI_SERVICE_KEYS or not _clean_value(value):
            dropped.append(str(key)[:64])
            continue
        clean[key] = value
    return clean, dropped


def validate_provenance(prov: Mapping[str, Any]) -> None:
    """寫入前的最後一道（Fail-Fast）：不在 allow-list 的鍵、值不乾淨、或 MOST 自組欄位形狀不對，都是 bug → `ValueError`。

    即使上游（mapper、client）已經清理過也再驗一次：`WiParserPort` 是 Protocol，換掉實作就繞過它們。
    """
    extra = set(prov) - ALLOWED_KEYS
    if extra:
        raise ValueError(f"provenance keys not in allow-list: {sorted(extra)}")
    for key in AI_SERVICE_KEYS & set(prov):
        if not _clean_value(prov[key]):
            raise ValueError(f"provenance.{key} is not a clean scalar")
    labels = prov.get("motion_labels", [])
    if not isinstance(labels, list) or len(labels) > MAX_MOTION_LABELS or any(not _label_ok(x) for x in labels):
        raise ValueError("provenance.motion_labels has an unexpected shape")
    dropped = prov.get("dropped", [])
    if (
        not isinstance(dropped, list)
        or len(dropped) > MAX_DROPPED
        or any(not (isinstance(x, str) and _DROPPED_RE.fullmatch(x)) for x in dropped)
    ):
        raise ValueError("provenance.dropped has an unexpected shape")


def _label_ok(x: Any) -> bool:
    if not isinstance(x, dict) or set(x) - _LABEL_KEYS:
        return False
    aid = x.get("action_id")
    if not (isinstance(aid, str) and _ACTION_ID_RE.fullmatch(aid)):
        return False
    for k in ("sub_activity", "object_text"):
        v = x.get(k)
        if v is not None and not (isinstance(v, str) and len(v) <= MAX_TEXT_LEN):
            return False
    hand = x.get("hand_hint")
    return hand is None or hand in _HANDS
