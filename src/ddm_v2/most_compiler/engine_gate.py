"""Engine gate：對 complete drafts 呼叫 compute_cycle；失敗不擋其他 draft。"""
from __future__ import annotations

from typing import Any

from ddm_v2.most_engine.calculate import SequenceError, compute_cycle
from ddm_v2.most_engine.narrative import build_narrative
from ddm_v2.most_engine.rule_set_data import RuleSetData
from ddm_v2.nlp.contracts import CycleDraft
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine


class EnFieldInTmuPath(RuntimeError):
    """ADR-032 I3：英文欄位被帶進決定 TMU 的路徑。"""

    code = "EN_FIELD_IN_TMU_PATH"


def _assert_no_en_fields(lab: dict[str, dict[str, Any]]) -> None:
    """執行期不變式：labels 的任何 entry 都不得帶英文欄（鍵以 `_en` 結尾）。

    為什麼不能只靠 CI 的字面 grep 守衛（`tests/unit/test_i18n_en_field_isolation.py`）：
    那支守衛掃的是**呼叫端檔案的字面**，而呼叫端可以間接取得同一個 builder——
    `getattr(providers, "build_label" + "_map")(opts)` 就完全穿透它（實測：守衛 6 passed、
    parity 14 passed，英文欄照樣進到這裡）。這裡改守**實際傳進來的資料形狀**，
    不依賴任何名單，也不管呼叫端怎麼寫。

    用 `raise` 而不是 `assert`：`python -O` 會把 `assert` 整條拿掉，而這是承重防線。
    正當路徑（`wi_ai_service._option_labels()`）是逐鍵白名單投影、不含英文欄，照常通過。
    """
    for param, entries in lab.items():
        for code, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            bad = sorted(k for k in entry if k.endswith("_en"))
            if bad:
                raise EnFieldInTmuPath(
                    f"ADR-032 I3：TMU 路徑的 labels 不得帶英文欄 {bad}"
                    f"（{param}/{code}）——請傳純中文的 label map"
                )


def apply_engine_gate(
    drafts: list[CycleDraft],
    rs: RuleSetData,
    *,
    labels: dict[str, dict[str, Any]] | None = None,
) -> list[CycleDraft]:
    """僅對 complete=True 且 cycle 非空者算 TMU；partial 跳過（A5）。"""
    out: list[CycleDraft] = []
    empty_vocab = {"object": "", "from": "", "to": "", "hand": ""}
    lab = labels or {}
    _assert_no_en_fields(lab)
    for draft in drafts:
        if not draft.complete or not draft.cycle:
            out.append(draft)
            continue
        try:
            cin = CycleIn.model_validate(draft.cycle)
            result = compute_cycle(cycle_in_to_engine(cin), rs)
            engine_result = {
                "total_tmu": result.total_tmu,
                "total_seconds": result.total_seconds,
                "tech_line": result.tech_line,
                "breakdown": [
                    {"letter": L, "tmu": t} for L, t in zip(result.letters, result.slot_tmus)
                ],
            }
            narrative = build_narrative(cin.model_dump(mode="json"), lab, empty_vocab)
            # strip compile-only soft issues that don't invalidate engine success
            soft = {
                "quantity_policy_review",
                "next_operation",
                "i_range_assumed",
            }
            remaining = [i for i in draft.issues if i not in soft and not i.startswith("missing_core_")]
            # keep soft reasons for routing visibility
            issues = [i for i in draft.issues if i in soft] + remaining
            out.append(
                draft.model_copy(
                    update={
                        "engine_result": engine_result,
                        "narrative": narrative,
                        "issues": issues,
                    }
                )
            )
        except SequenceError as exc:
            out.append(
                draft.model_copy(
                    update={
                        "engine_result": None,
                        "narrative": None,
                        "issues": list(draft.issues) + [f"engine_reject_{exc.code}"],
                        # completeness stays True but invalid for routing
                    }
                )
            )
    return out
