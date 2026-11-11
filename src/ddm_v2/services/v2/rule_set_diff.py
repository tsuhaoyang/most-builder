"""rule-set 值差異計算（ADR-023 D7 / H-1）。

輸入輸出都是 `rule_set_service.load_full()` 的形狀，**不碰 DB、不碰框架**——
所以同一份實作可以同時服務兩個用途：

1. `GET /rule-sets/{code}/diff`：讓 approver 在按 publish 之前看得到「被覆核的是什麼」。
   在此之前 publish 只回 `{"code":..., "status":"published"}`，覆核者對「這一版跟現在
   線上的版本差在哪」零資訊——兩人覆核形同盲簽。
2. `PUT /full`（`replace_children`）的稽核 payload：整份 12 張子表替換無法只靠
   「哪些區塊、幾列」還原（資安席已指出 delete 只存列數同樣還原不了值），
   存逐選項的前後值才回答得了「改了哪個參數的哪個選項、從什麼變成什麼」。

## 列的識別鍵（key）

- **選項型**（b/g/p_bases/p_addons/m_verbs/x/i）：`code`（DB 有 UNIQUE(rule_set_id, code)，
  跨版本可比）。
- **帶型**：沒有「選項代碼」這種東西（ADR-023 §2），唯一穩定的身分是**組內位置**——
  帶表本來就是「第幾帶」的有序序列，改第 3 帶的上界就是改第 3 帶。
  - `a_bands` 依 `component` 分組 → `reach[0]`
  - `m_rotation` 依 `revolutions` 分組（引擎查表先比對圈數）→ `rev2[1]`
  - 其餘 → `[0]`

  位置鍵的已知取捨：在中間**插入**一帶會讓其後所有帶顯示為 changed。這是誠實的呈現
  （引擎確實會對那些位置取到不同的值），不是誤報。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# 有 `code` 欄、以 code 為身分的區塊；其餘為帶型（以組內位置為身分）。
OPTION_SECTIONS: frozenset[str] = frozenset(
    {"b", "g", "p_bases", "p_addons", "m_verbs", "x", "i"}
)

# 帶型區塊的分組欄（同一張表內各自成序者）。None＝整張表一個序列。
BAND_GROUP_FIELD: dict[str, str | None] = {
    "a_bands": "component",
    "m_rotation": "revolutions",
    "m_ladder": None,
    "m_foot": None,
    "m_hand": None,
}

# 版本表頭上會影響計算/識別的欄位。`multiplier` 尤其關鍵：它等比縮放該版本每一個 TMU。
HEADER_FIELDS: tuple[str, ...] = ("name_zh", "multiplier")

SECTION_KEYS: tuple[str, ...] = (
    "a_bands", "b", "g", "p_bases", "p_addons", "m_ladder", "m_foot",
    "m_verbs", "m_rotation", "m_hand", "x", "i",
)

assert set(BAND_GROUP_FIELD) | OPTION_SECTIONS == set(SECTION_KEYS)


def _keyed(section: str, rows: list[Any]) -> dict[str, dict[str, Any]]:
    """一個區塊的列 → {key: row}。非 dict 的列一律忽略（此處只做比對，驗證是別人的職責）。"""
    out: dict[str, dict[str, Any]] = {}
    counters: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if section in OPTION_SECTIONS:
            key = str(row.get("code"))
        else:
            group_field = BAND_GROUP_FIELD[section]
            group = "" if group_field is None else str(row.get(group_field))
            pos = counters.get(group, 0)
            counters[group] = pos + 1
            prefix = "rev" if section == "m_rotation" else ""
            key = f"{prefix}{group}[{pos}]"
        out[key] = row
    return out


def _field_deltas(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in sorted(set(before) | set(after))
        if before.get(field) != after.get(field)
    }


def section_row_counts(full: dict[str, Any]) -> dict[str, int]:
    """12 個區塊各自的列數（稽核摘要用；**不足以還原值**，故永遠與 diff 併用）。"""
    return {key: len(full.get(key) or []) for key in SECTION_KEYS}


def snapshot_digest(full: dict[str, Any]) -> str:
    """`load_full()` 內容的 sha256（不含 id/status 等非值欄）。

    用途是「釘住當時的值」而不是還原值——凡是靠它的地方（clone-draft）都必須有
    另一條路能取回值本身，見 `rule_set_service.clone_draft` 的註解。
    """
    payload: dict[str, Any] = {key: full.get(key) or [] for key in SECTION_KEYS}
    payload["_header"] = {field: full.get(field) for field in HEADER_FIELDS}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_full(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """兩份 `load_full()` 的值差異：新增／刪除／值變更，逐區塊逐列。

    `sections` **只列出有差異的區塊**（沒差異的區塊放進去只是噪音）；
    `row_counts` 則 12 個區塊全給，讓「哪些區塊被整批換掉」一眼可見。
    """
    header = {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in HEADER_FIELDS
        if before.get(field) != after.get(field)
    }

    sections: dict[str, Any] = {}
    totals = {"added": 0, "removed": 0, "changed": 0}
    for section in SECTION_KEYS:
        b = _keyed(section, before.get(section) or [])
        a = _keyed(section, after.get(section) or [])
        added = [{"key": k, "after": a[k]} for k in a if k not in b]
        removed = [{"key": k, "before": b[k]} for k in b if k not in a]
        changed = [
            {"key": k, "fields": _field_deltas(b[k], a[k])}
            for k in a
            if k in b and _field_deltas(b[k], a[k])
        ]
        if added or removed or changed:
            sections[section] = {"added": added, "removed": removed, "changed": changed}
            totals["added"] += len(added)
            totals["removed"] += len(removed)
            totals["changed"] += len(changed)

    return {
        "header": header,
        "sections": sections,
        "row_counts": {
            key: {"before": len(before.get(key) or []), "after": len(after.get(key) or [])}
            for key in SECTION_KEYS
        },
        "summary": {
            **totals,
            "changed_sections": sorted(sections),
            "header_changed": sorted(header),
            "identical": not sections and not header,
        },
    }
