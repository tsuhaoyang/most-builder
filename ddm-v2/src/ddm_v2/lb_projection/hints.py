"""hints：確定性提示（ADR-035 D10 §7.2）。純函式，只看投影結構（parts／tool_id／frequency／
segment／countersignature／x_seconds），不看敘述文字、不猜語意。看不出來就不提示。

四種 kind：
- H_TOOL_EPISODE_SAME_STATION（ask）：同 chain 一個工具 episode 跨 ≥2 列且不全在同一 cub → 建議同站
- H_LOT_RUN_SEGMENT（ask）：同 chain 連續、frequency>1 整數且相等、≥2 列、至少一列無 segment → 建議同批人
- H_TOOL_DECOMPOSED（info）：parts>1 的列，依 tool_id 分組
- H_MACHINE_TIME（info）：CM 且 x_seconds ≥ 1
key = f"{kind}:{','.join(sorted(wi_row_ids))}"；同 key 只出一條；順序依第一列 seq_no。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ddm_v2.lb_projection.models import ProjectionRow


@dataclass(frozen=True)
class Hint:
    kind: str
    key: str
    wi_row_ids: list[str]
    params: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "key": self.key, "wi_row_ids": self.wi_row_ids, "params": self.params}

    # 別名（實作書快照測試用 to_dict；report.py 用 as_dict）
    to_dict = as_dict


def _mk(kind: str, ids: list[str], params: dict[str, Any]) -> Hint:
    sid = sorted(ids)
    return Hint(kind=kind, key=f"{kind}:{','.join(sid)}", wi_row_ids=ids, params=params)


def hints(result: Any, rows: list[ProjectionRow]) -> list[Hint]:
    row_by_id = {r.wi_row_id: r for r in rows}
    seq_by_id = {r.wi_row_id: r.seq_no for r in rows}
    plan_by_id = {p.row.wi_row_id: p for p in result.plans}
    # chain 成員（依 chain.ordered_row_ids，chain 順序）
    chains = result.chains

    out: list[Hint] = []
    seen: set[str] = set()

    def _add(h: Hint) -> None:
        if h.key not in seen:
            seen.add(h.key)
            out.append(h)

    def _cs(rid: str) -> str:
        r = row_by_id.get(rid)
        return (r.level.countersignature or "").strip() if r else ""

    def _all_same_cub(ids: list[str]) -> bool:
        cubs = [_cs(i) for i in ids]
        return all(c.startswith("cub") for c in cubs) and len(set(cubs)) == 1

    # ── H_TOOL_EPISODE_SAME_STATION：Pattern A episode 狀態機（§7.2）──
    # 沿 chain 順序：acquire（不含 release）開始一段 → use 延續 → release 結束；
    # 只看 MotionPlan.parts（resolve_chain 已算好）。Pattern B 單列（acquire+release 同列）不參與。
    for ch in chains:
        open_ep: dict[str, list[str]] = {}   # tool_id → 開啟中的段
        for rid in getattr(ch, "ordered_row_ids", []):
            p = plan_by_id.get(rid)
            if p is None or not getattr(p, "tool_id", None):
                continue
            parts, tool_id = set(p.parts), p.tool_id
            if "acquire" in parts and "release" in parts:
                continue                          # Pattern B 單列：已閉合，不參與
            if "acquire" in parts:
                open_ep[tool_id] = [rid]          # 開始（含 ['acquire','use']）
                continue
            if tool_id not in open_ep:
                continue                          # 孤兒 use/release：resolve_chain 已報 E，hints 忽略
            open_ep[tool_id].append(rid)
            if "release" in parts:
                seg = open_ep.pop(tool_id)
                if len(seg) >= 2 and not _all_same_cub(seg):
                    _add(_mk("H_TOOL_EPISODE_SAME_STATION", seg, {"tool_id": tool_id}))

    # ── H_LOT_RUN_SEGMENT：同 chain 連續、frequency>1 整數相等、≥2 列、至少一列無 segment ──
    for ch in chains:
        ids = list(getattr(ch, "ordered_row_ids", []))
        run: list[str] = []
        run_freq: float | None = None

        def _flush(run_ids: list[str], freq: float | None) -> None:
            if len(run_ids) >= 2 and freq is not None:
                if any(not (row_by_id[i].lb_tags.segment or "").strip() for i in run_ids):
                    _add(_mk("H_LOT_RUN_SEGMENT", run_ids, {"frequency": freq}))

        for rid in ids:
            r = row_by_id.get(rid)
            f = r.frequency if r else 1
            is_lot = f is not None and f > 1 and float(f) == int(f)
            if is_lot and (run_freq is None or f == run_freq):
                run.append(rid)
                run_freq = f
            else:
                _flush(run, run_freq)
                run = [rid] if is_lot else []
                run_freq = f if is_lot else None
        _flush(run, run_freq)

    # ── H_TOOL_DECOMPOSED（info）：parts>1 的列依 tool_id 分組 ──
    dec_by_tool: dict[str, list[str]] = {}
    for p in result.plans:
        if len(getattr(p, "parts", [])) > 1 and getattr(p, "tool_id", None):
            dec_by_tool.setdefault(p.tool_id, []).append(p.row.wi_row_id)
    for tool_id, ids in dec_by_tool.items():
        _add(_mk("H_TOOL_DECOMPOSED", ids, {"tool_id": tool_id}))

    # ── H_MACHINE_TIME（info）：CM 且 x_seconds ≥ 1 ──
    for r in rows:
        if r.cycle.seq_kind == "CM" and (r.cycle.x_seconds or 0) >= 1:
            _add(_mk("H_MACHINE_TIME", [r.wi_row_id], {}))

    out.sort(key=lambda h: min(seq_by_id.get(i, 1_000_000) for i in h.wi_row_ids))
    return out


__all__ = ["Hint", "hints"]
