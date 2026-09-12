"""PrecedenceProjector：分層 DAG 投影（Spec §5）。

不得沿用 level.build_output().precedence_edges（實作書 §6#4）。層間邊＝ hi_Y < lo_X 偏序的傳遞縮減，
由 Y 的 sink 連 X 的 source。chain 內相鄰項連邊；tool motion 拆出的 acquire→use→release 是內部鏈。
巢狀 cub 區塊插入位置＝成員最小 seq_no（Spec §5.3）。`a/b` → E_LEVEL_DISCRETE_UNSUPPORTED。
編號：Kahn，就緒集合以 (seq_no, part_index) 最小優先（Spec §5.9）。
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from ddm_v2.lb_projection.errors import (
    E_LEVEL_DISCRETE_UNSUPPORTED,
    E_LEVEL_INVALID,
    ProjectionError,
)
from ddm_v2.lb_projection.models import ProjectionRow
from ddm_v2.lb_projection.tools import MotionPlan

_PART_INDEX = {"acquire": 0, "use": 1, "release": 2}


class PrecedenceError(Exception):
    def __init__(self, err: ProjectionError) -> None:
        super().__init__(err.message)
        self.err = err


@dataclass(frozen=True)
class TaskNode:
    """拆列後的一個 task 節點：motion 的一個 part。"""

    wi_row_id: str
    seq_no: int
    part: str  # acquire/use/release
    part_index: int


@dataclass
class MotionUnit:
    """一個 motion 拆列後的節點串（source=第一列、sink=最後列），及其內部鏈邊。"""

    row: ProjectionRow
    nodes: list[TaskNode]
    internal_edges: list[tuple[TaskNode, TaskNode]] = field(default_factory=list)

    @property
    def source(self) -> TaskNode:
        return self.nodes[0]

    @property
    def sink(self) -> TaskNode:
        return self.nodes[-1]


def _parse_level_set(level: str, wi_row_id: str | None) -> set[int]:
    """'k'→{k}；'a~b'→{a..b}；'a/b'（離散）→ E_LEVEL_DISCRETE_UNSUPPORTED（Spec §5.4）。"""
    s = str(level).strip()
    if "/" in s:
        raise PrecedenceError(ProjectionError(E_LEVEL_DISCRETE_UNSUPPORTED, wi_row_id, f"level 離散跳號不支援：{s}"))
    if "~" in s:
        a, b = s.split("~", 1)
        return set(range(int(a), int(b) + 1))
    return {int(s)}


def build_motion_units(plans: list[MotionPlan]) -> dict[str, MotionUnit]:
    """MotionPlan（WP4）→ 每 motion 的 TaskNode 串 + 內部鏈邊（wi_row_id 索引）。"""
    units: dict[str, MotionUnit] = {}
    for p in plans:
        nodes = [
            TaskNode(p.row.wi_row_id, p.row.seq_no, part, _PART_INDEX[part])
            for part in p.parts
        ]
        edges = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
        units[p.row.wi_row_id] = MotionUnit(row=p.row, nodes=nodes, internal_edges=edges)
    return units


@dataclass
class Chain:
    """一個執行序列：standalone motion 自成一 chain，或群組（含巢狀區塊）依 order 展開。"""

    key: str  # countersignature 或 wi_row_id（standalone）
    ordered_row_ids: list[str]  # 依執行序（含巢狀展開）
    lo: int
    hi: int

    def source_of(self, units: dict[str, MotionUnit]) -> TaskNode:
        return units[self.ordered_row_ids[0]].source

    def sink_of(self, units: dict[str, MotionUnit]) -> TaskNode:
        return units[self.ordered_row_ids[-1]].sink


def build_chains(rows: list[ProjectionRow]) -> list[Chain]:
    """把非 general／非 SIMO-從屬 的 motion 組成頂層 chain（Spec §5.3/§5.4）。"""
    active = [r for r in rows if not r.lb_tags.is_general and not r.simo_group_id]

    # 依 countersignature 分組
    groups: dict[str, list[ProjectionRow]] = {}
    standalones: list[ProjectionRow] = []
    for r in active:
        cs = (r.level.countersignature or "").strip()
        if cs:
            groups.setdefault(cs, []).append(r)
        else:
            standalones.append(r)

    # 頂層項 = standalone main + 無 parent 的群組（巢狀 cub 併入其 parent sub）
    chains: list[Chain] = []

    # standalone：每個自成 chain，層範圍由自身 level
    for r in standalones:
        s = _parse_level_set(r.level.level or "1", r.wi_row_id)
        chains.append(Chain(key=r.wi_row_id, ordered_row_ids=[r.wi_row_id], lo=min(s), hi=max(s)))

    # 群組：只處理無 parent 的（頂層）；巢狀 cub 由其 parent 展開時併入
    top_groups = {cs: mem for cs, mem in groups.items() if not any((m.level.parent_countersignature or "").strip() for m in mem)}
    for cs, members in top_groups.items():
        ordered = _expand_group(cs, members, groups)
        head = next((m for m in members if (m.level.order or 0) == 1), members[0])
        s = _parse_level_set(head.level.level or "1", head.wi_row_id)
        chains.append(Chain(key=cs, ordered_row_ids=ordered, lo=min(s), hi=max(s)))

    return chains


def _expand_group(cs: str, members: list[ProjectionRow], all_groups: dict[str, list[ProjectionRow]]) -> list[str]:
    """群組直接成員依 order 排序；巢狀 cub 區塊以成員最小 seq_no 插入（Spec §5.3）。"""
    direct = sorted(members, key=lambda m: m.level.order or 0)
    # 找巢狀在本 cs 底下的 cub 群組
    nested = {c: mem for c, mem in all_groups.items() if any((m.level.parent_countersignature or "").strip() == cs for m in mem)}
    # 以 (排序鍵 seq_no) 交錯：直接成員用自身 seq_no；巢狀區塊用其成員最小 seq_no
    items: list[tuple[int, list[str]]] = []
    for m in direct:
        items.append((m.seq_no, [m.wi_row_id]))
    for c, mem in nested.items():
        block_ids = [x.wi_row_id for x in sorted(mem, key=lambda z: z.level.order or 0)]
        items.append((min(x.seq_no for x in mem), block_ids))
    items.sort(key=lambda t: t[0])
    out: list[str] = []
    for _seq, ids in items:
        out.extend(ids)
    return out


def _transitive_reduction(chains: list[Chain]) -> list[tuple[int, int]]:
    """頂層項偏序 Y≺X ⟺ hi_Y < lo_X 的傳遞縮減（Spec §5.5），回 (Y_idx, X_idx) list。"""
    n = len(chains)
    rel = [[False] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            if y != x and chains[y].hi < chains[x].lo:
                rel[y][x] = True
    # 傳遞縮減：移除可由中間點推得的邊
    red = [[rel[y][x] for x in range(n)] for y in range(n)]
    for y in range(n):
        for k in range(n):
            if rel[y][k]:
                for x in range(n):
                    if rel[k][x]:
                        red[y][x] = False
    return [(y, x) for y in range(n) for x in range(n) if red[y][x]]


def project_precedence(
    rows: list[ProjectionRow], plans: list[MotionPlan]
) -> tuple[dict[str, int], list[ProjectionError]]:
    """回 (task_id_by_node_key, warnings)。node_key = f'{wi_row_id}:{part}'。

    先跑 level.validate gate；再構 chains、層邊、chain 內邊、內部鏈邊，Kahn 編號。
    """
    warnings: list[ProjectionError] = []
    _level_gate(rows)

    units = build_motion_units(plans)
    chains = build_chains(rows)

    # 節點集合：general/SIMO 之外的所有拆列節點；general 單列節點也要進 Kahn（無邊，Spec §5.7/提醒#1）
    general_units = [build_motion_units([p])[p.row.wi_row_id] for p in plans if p.row.lb_tags.is_general]

    edges: list[tuple[TaskNode, TaskNode]] = []
    for u in units.values():
        edges.extend(u.internal_edges)
    # chain 內相鄰項連邊（前項 sink → 後項 source）
    for ch in chains:
        for a, b in zip(ch.ordered_row_ids, ch.ordered_row_ids[1:]):
            edges.append((units[a].sink, units[b].source))
    # 層間邊：Y.sink → X.source（傳遞縮減）
    for y, x in _transitive_reduction(chains):
        edges.append((chains[y].sink_of(units), chains[x].source_of(units)))

    # 所有節點（含 general 單列）
    all_units = list(units.values()) + general_units
    all_nodes = [nd for u in all_units for nd in u.nodes]

    task_id = _kahn_number(all_nodes, edges)

    # 浮動偵測（W_FLOATING_TASK）由 validator.py 擁有（§5.10；單一權威，note#1）。
    return task_id, warnings


def _level_gate(rows: list[ProjectionRow]) -> None:
    """跑 most_engine.level.validate；任何 issue → E_LEVEL_INVALID（Spec §5.1）。"""
    from ddm_v2.most_engine import level as level_engine

    lrows = [
        level_engine.LevelRow(
            content=r.cycle.narrative_en or r.sub_activity or f"row{r.seq_no}",
            raw_seconds=1.0,
            coefficient=1.0,
            number=r.level.number,
            number_count=r.level.number_count,
            ascription=r.level.ascription,
            level=r.level.level,
            countersignature=r.level.countersignature,
            parent_countersignature=r.level.parent_countersignature,
            order=r.level.order,
        )
        for r in rows
        if not r.lb_tags.is_general and not r.simo_group_id
    ]
    issues = level_engine.validate(lrows)
    if issues:
        codes = ", ".join(f"{i.code}@row{i.row_index}" for i in issues)
        raise PrecedenceError(ProjectionError(E_LEVEL_INVALID, None, f"Level 驗證未過：{codes}"))


def _node_key(nd: TaskNode) -> tuple[str, str]:
    return (nd.wi_row_id, nd.part)


def _kahn_number(nodes: list[TaskNode], edges: list[tuple[TaskNode, TaskNode]]) -> dict[str, int]:
    """Kahn 拓撲排序，就緒集合以 (seq_no, part_index) 最小優先（Spec §5.9）。回 {wi_row_id:part → task_id}。"""
    succ: dict[tuple[str, str], list[tuple[str, str]]] = {}
    indeg: dict[tuple[str, str], int] = {_node_key(n): 0 for n in nodes}
    node_by_key = {_node_key(n): n for n in nodes}
    for a, b in edges:
        ka, kb = _node_key(a), _node_key(b)
        succ.setdefault(ka, []).append(kb)
        indeg[kb] = indeg.get(kb, 0) + 1

    heap: list[tuple[int, int, tuple[str, str]]] = []
    for k, n in node_by_key.items():
        if indeg[k] == 0:
            heapq.heappush(heap, (n.seq_no, n.part_index, k))

    order: dict[str, int] = {}
    tid = 1
    while heap:
        _seq, _pi, k = heapq.heappop(heap)
        order[f"{k[0]}:{k[1]}"] = tid
        tid += 1
        for nb in succ.get(k, []):
            indeg[nb] -= 1
            if indeg[nb] == 0:
                nn = node_by_key[nb]
                heapq.heappush(heap, (nn.seq_no, nn.part_index, nb))
    return order


__all__ = ["project_precedence", "build_chains", "build_motion_units", "TaskNode", "Chain", "PrecedenceError"]
