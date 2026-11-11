"""ToolLifecycleResolver：chain 內工具事件與 held 狀態機（Spec §4）。

判準唯一訊號＝ vocab `kind='tool'`（不看敘事文字，實作書 §6#2）：
- `tool_vocab == T` 且 T∉held → IMPLICIT_ACQUIRE（Pattern B）：§4.3 決 3 或 2 列。
- `tool_vocab == T` 且 T∈held → USE。
- `object_vocab == T`(kind=tool)、tool_vocab 空、T∉held → ACQUIRE（Pattern A）。
- `object_vocab == T`、T∈held、GM → RELEASE；CM → USE（Pattern A）。
- tool_vocab 與 object_vocab 都是不同工具 → E_TOOL_TWO_TOOLS。

chain 結束 held 非空 → E_TOOL_NOT_RELEASED；跨 chain 持有 → E_TOOL_CROSS_CHAIN（不放寬）。
MotionPlan 帶 `block`（Decomposed.RepeatBlock）供 WP6 quantity 決定 use 列的 N。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from ddm_v2.lb_projection.errors import (
    E_TOOL_TWO_TOOLS,
    W_GENERAL_WITH_TOOL,
    W_TOOL_NAME_EN_MISSING,
    ProjectionError,
)
from ddm_v2.lb_projection.models import ProjectionRow, ProjectionVocab
from ddm_v2.lb_projection.tmu import Decomposed, TmuDecompositionError, decompose_static

Part = Literal["acquire", "use", "release"]


class ToolEvent(Enum):
    ACQUIRE = "ACQUIRE"
    IMPLICIT_ACQUIRE = "IMPLICIT_ACQUIRE"
    USE = "USE"
    RELEASE = "RELEASE"
    NONE = "NONE"


class ToolResolveError(Exception):
    def __init__(self, err: ProjectionError) -> None:
        super().__init__(err.message)
        self.err = err


@dataclass
class MotionPlan:
    """一個 motion 的投影計畫：拆成幾列（parts）、工具、分解結果（含 block 供 WP6）。"""

    row: ProjectionRow
    parts: list[Part]  # 1–3 列，順序即 acquire→use→release 子集
    tool_id: str | None = None
    tool_vocab_key: str | None = None
    decomposed: Decomposed | None = None
    two_row_setup_post_into: Literal["use", "acquire"] | None = None  # §4.3 2 列時 setup_post 落點
    warnings: list[ProjectionError] = field(default_factory=list)


def tool_id_of(vocab: ProjectionVocab | None, key: str) -> tuple[str, list[ProjectionError]]:
    """name_en → snake_case；缺 name_en → tool_<key[:8]> + W_TOOL_NAME_EN_MISSING（Spec §4.4）。"""
    warns: list[ProjectionError] = []
    name_en = (vocab.name_en if vocab else None) or ""
    if not name_en.strip():
        warns.append(ProjectionError(W_TOOL_NAME_EN_MISSING, None, f"工具詞彙 {key} 無 name_en", params={"tool_id": f"tool_{key[:8]}"}))
        return f"tool_{key[:8]}", warns
    snake = re.sub(r"[^a-z0-9]+", "_", name_en.strip().lower()).strip("_")
    return snake, warns


def _is_tool(vocab: dict[str, ProjectionVocab], key: str | None) -> bool:
    return bool(key) and key in vocab and vocab[key].kind == "tool"


def _decompose(row: ProjectionRow) -> Decomposed:
    """以 fixture 靜態路徑分解（引擎路徑在 project.py 有 slot_inputs 時改走 decompose_engine）。"""
    return decompose_static(
        list(row.cycle.slot_tmus), row.cycle.repeat_counts, row.cycle.total_tmu, row.wi_row_id
    )


def resolve_chain(chain: list[ProjectionRow], vocab: dict[str, ProjectionVocab]) -> tuple[list[MotionPlan], set[str]]:
    """對一個 chain 逐 motion 判定工具事件，回 (plans, held_at_end)。

    held_at_end 非空由呼叫端（project.py）判 E_TOOL_NOT_RELEASED / E_TOOL_CROSS_CHAIN。
    """
    held: set[str] = set()
    plans: list[MotionPlan] = []

    for idx, row in enumerate(chain):
        obj, tool = row.object_vocab, row.tool_vocab
        obj_is_tool = _is_tool(vocab, obj)
        tool_is_tool = _is_tool(vocab, tool)

        # 一列兩工具 → 拒絕（Spec §4.1）
        if tool_is_tool and obj_is_tool and obj != tool:
            raise ToolResolveError(
                ProjectionError(E_TOOL_TWO_TOOLS, row.wi_row_id, f"一個 motion 兩工具：object={obj}, tool={tool}")
            )

        # general motion 不進 resolver（Spec §4）；持工具 → 警告，單列輸出（工具欄丟棄）
        if row.lb_tags.is_general:
            warns = []
            if tool_is_tool or obj_is_tool:
                _tk = tool if tool_is_tool else obj
                warns.append(ProjectionError(W_GENERAL_WITH_TOOL, row.wi_row_id, "general motion 持工具，工具欄丟棄", params={"tool_id": _tk}))
            plans.append(MotionPlan(row=row, parts=["use"], warnings=warns))
            continue

        # Pattern B：tool_vocab 指向工具
        if tool_is_tool:
            T = tool
            if T not in held:  # IMPLICIT_ACQUIRE
                plan = _pattern_b(row, chain, idx, T, vocab, held)
                plans.append(plan)
            else:  # USE
                plans.append(_use_plan(row, T, vocab))
            continue

        # Pattern A：object_vocab 是工具
        if obj_is_tool:
            T = obj
            if T not in held:  # ACQUIRE
                held.add(T)
                plans.append(_single_tool_plan(row, T, "acquire", vocab))
            elif row.cycle.seq_kind == "GM":  # RELEASE
                held.discard(T)
                plans.append(_single_tool_plan(row, T, "release", vocab))
            else:  # CM held → USE
                plans.append(_use_plan(row, T, vocab))
            continue

        # 非工具列：單列
        plans.append(MotionPlan(row=row, parts=["use"], decomposed=_safe_decompose(row)))

    return plans, held


def _pattern_b(row: ProjectionRow, chain: list[ProjectionRow], idx: int, T: str, vocab: dict[str, ProjectionVocab], held: set[str]) -> MotionPlan:
    """IMPLICIT_ACQUIRE：向後看同一 chain 決定 3 或 2 列（Spec §4.3）。"""
    tool_id, warns = tool_id_of(vocab.get(T), T)
    dec = _safe_decompose(row)
    two_row = _release_later_in_chain(chain, idx, T, vocab)
    if two_row:
        # 2 列：acquire + use；T 持續 held 到後面的 RELEASE
        held.add(T)
        # §4.3：setup_post 落點 N>1→acquire、N=1→use
        into = "acquire" if (dec and dec.n > 1) else "use"
        return MotionPlan(row=row, parts=["acquire", "use"], tool_id=tool_id, tool_vocab_key=T,
                          decomposed=dec, two_row_setup_post_into=into, warnings=warns)
    # 3 列：acquire + use + release；T 出 held（本 motion 內完成）
    return MotionPlan(row=row, parts=["acquire", "use", "release"], tool_id=tool_id, tool_vocab_key=T,
                      decomposed=dec, warnings=warns)


def _release_later_in_chain(chain: list[ProjectionRow], idx: int, T: str, vocab: dict[str, ProjectionVocab]) -> bool:
    """向後看：下一次 T 的 ACQUIRE/IMPLICIT_ACQUIRE 之前，是否出現 T 的 RELEASE（GM、object=T）（Spec §4.3）。"""
    for later in chain[idx + 1 :]:
        # 再次取得（Pattern B 或 Pattern A acquire）→ 停止（本 episode 在此 motion 內就該收）
        if later.tool_vocab == T and _is_tool(vocab, later.tool_vocab):
            return False
        if later.object_vocab == T and _is_tool(vocab, later.object_vocab):
            if later.cycle.seq_kind == "GM":  # RELEASE 事件
                return True
            # CM held → USE，繼續向後看
    return False


def _single_tool_plan(row: ProjectionRow, T: str, part: Part, vocab: dict[str, ProjectionVocab]) -> MotionPlan:
    tool_id, warns = tool_id_of(vocab.get(T), T)
    return MotionPlan(row=row, parts=[part], tool_id=tool_id, tool_vocab_key=T,
                      decomposed=_safe_decompose(row), warnings=warns)


def _use_plan(row: ProjectionRow, T: str, vocab: dict[str, ProjectionVocab]) -> MotionPlan:
    tool_id, warns = tool_id_of(vocab.get(T), T)
    return MotionPlan(row=row, parts=["use"], tool_id=tool_id, tool_vocab_key=T,
                      decomposed=_safe_decompose(row), warnings=warns)


def _safe_decompose(row: ProjectionRow) -> Decomposed | None:
    """分解；TmuDecompositionError 讓它向上冒泡（由 project.py 收集為 E 碼）。"""
    try:
        return _decompose(row)
    except TmuDecompositionError:
        raise


__all__ = ["ToolEvent", "MotionPlan", "ToolResolveError", "resolve_chain", "tool_id_of"]
