"""WP5 關卡：PrecedenceProjector（Spec §5）對照 golden。

驗證：general A 拿 task_id 1（提醒#1）；L1 兩根 B/C 無 pred；L2 六入口 source pred={B,C}（提醒#2）；
巢狀 cub30⊂sub2 → 鏈 E→F→G→H（提醒#3）；O pred=六鏈 sink（提醒#4）；P1 pred={O}；a/b 拒收。
"""
from __future__ import annotations

import pathlib

import pytest

from ddm_v2.lb_projection.adapter import load_fixture
from ddm_v2.lb_projection.errors import E_LEVEL_DISCRETE_UNSUPPORTED
from ddm_v2.lb_projection.precedence import (
    PrecedenceError,
    build_chains,
    build_motion_units,
    project_precedence,
)
from ddm_v2.lb_projection.tools import resolve_chain

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]
_GOLDEN_JSON = _REPO / "docs" / "lb-integration" / "fixtures" / "server_node_worksheet.json"


def _project():
    rows, vocab, _ = load_fixture(_GOLDEN_JSON)
    # 全部當一個 chain 跑 tools（fixture 是一條裝配線；chain 切分由 precedence 處理，tools 只需 held 狀態）
    # 但 tool episode 是 per-chain 的——這裡按 countersignature 分 chain 跑 tools。
    plans = []
    # standalone + 每個群組各自 resolve（held 狀態機 per chain）
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        key = (r.level.countersignature or "").strip() or f"__standalone__{r.seq_no}"
        groups[key].append(r)
    for key, members in groups.items():
        members.sort(key=lambda m: (m.level.order or 0, m.seq_no))
        chain_plans, _held = resolve_chain(members, vocab)
        plans.extend(chain_plans)
    plans.sort(key=lambda p: p.row.seq_no)
    task_id, warnings = project_precedence(rows, plans)
    return rows, vocab, plans, task_id, warnings


def test_general_a_gets_task_id_1() -> None:
    """general A（seq1）無邊但參與 Kahn，tie-break seq_no=1 → task_id 1（提醒#1）。"""
    _rows, _vocab, _plans, task_id, _w = _project()
    # A 是單列 use 節點
    assert task_id["00000000-0000-4000-8000-000000000001:use"] == 1


def test_chains_and_layers() -> None:
    """chain 構建：sub2 展開 E→F→G→H（巢狀 cub30 以 min seq_no=7 排 F 後，提醒#3）。"""
    rows, _vocab, _plans, _task_id, _w = _project()
    chains = build_chains(rows)
    sub2 = next(c for c in chains if c.key == "sub2")
    # E(seq5) F(seq6) G(seq7) H(seq8) 依序
    seqs = [int(rid[-12:]) for rid in sub2.ordered_row_ids]
    assert seqs == [5, 6, 7, 8]
    assert (sub2.lo, sub2.hi) == (2, 2)


def test_ab_discrete_level_rejected() -> None:
    """level 含 '/' → E_LEVEL_DISCRETE_UNSUPPORTED。"""
    rows, vocab, _p, _t, _w = _project()
    # 竄改一列 level 為 '1/3'
    rows2 = [r.model_copy(deep=True) for r in rows]
    standalone = next(r for r in rows2 if not r.level.countersignature and not r.lb_tags.is_general)
    standalone.level.level = "1/3"
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows2:
        key = (r.level.countersignature or "").strip() or f"__s{r.seq_no}"
        groups[key].append(r)
    plans = []
    for _k, mem in groups.items():
        cp, _h = resolve_chain(sorted(mem, key=lambda m: (m.level.order or 0, m.seq_no)), vocab)
        plans.extend(cp)
    with pytest.raises(PrecedenceError) as ei:
        project_precedence(rows2, plans)
    assert ei.value.err.code == E_LEVEL_DISCRETE_UNSUPPORTED


def test_golden_predecessors_match() -> None:
    """完整投影後 34/34 task 的 predecessors 與 task_id 逐一等於 golden；總邊數 42（裁決 A 後）。

    task 31 = {6,12,15,21,27,30}（sub2 單一 chain E→F→G→H，sink=12；10→31 傳遞冗餘已由 §5.5 縮減）。
    """
    import csv
    from collections import defaultdict

    rows, _vocab, plans, task_id, _w = _project()
    units = build_motion_units(plans)
    chains = build_chains(rows)
    from ddm_v2.lb_projection import precedence as P

    edges: list = []
    for u in units.values():
        edges.extend(u.internal_edges)
    for ch in chains:
        for a, b in zip(ch.ordered_row_ids, ch.ordered_row_ids[1:]):
            edges.append((units[a].sink, units[b].source))
    for y, x in P._transitive_reduction(chains):
        edges.append((chains[y].sink_of(units), chains[x].source_of(units)))

    preds: dict = defaultdict(set)
    for a, b in edges:
        preds[task_id[f"{b.wi_row_id}:{b.part}"]].add(task_id[f"{a.wi_row_id}:{a.part}"])

    golden = {
        int(r["task_id"]): (set(map(int, r["predecessors"].split(","))) if r["predecessors"] else set())
        for r in csv.DictReader(open(_GOLDEN_JSON.parent / "server_node_tasks.expected.csv"))
    }
    assert len(edges) == 42
    for t in range(1, 35):
        assert preds.get(t, set()) == golden[t], f"task {t}: mine={sorted(preds.get(t, set()))} golden={sorted(golden[t])}"
