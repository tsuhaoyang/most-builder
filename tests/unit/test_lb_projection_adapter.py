"""WP2 關卡：fixture 24 列全數 validate；read_worksheet dict → ProjectionRow 對齊。

出處：Spec §1、§2；實作書 WP2。
"""
from __future__ import annotations

import pathlib

import pytest

from ddm_v2.lb_projection.adapter import load_fixture, rows_from_worksheet
from ddm_v2.lb_projection.models import ProjectionRow

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[2]
_GOLDEN_JSON = _REPO / "docs" / "lb-integration" / "fixtures" / "server_node_worksheet.json"


def test_fixture_24_rows_validate() -> None:
    rows, vocab, meta = load_fixture(_GOLDEN_JSON)
    assert len(rows) == 24
    assert all(isinstance(r, ProjectionRow) for r in rows)
    # vocab 含三個工具（Spec §4 tool-held 判準 kind='tool'）
    tools = {k for k, v in vocab.items() if v.kind == "tool"}
    assert tools == {"scanner", "electric_driver", "torque_driver"}
    assert meta["contract_version"] == "most-lb-csv-v1.1"


def test_fixture_row_shapes() -> None:
    rows, _, _ = load_fixture(_GOLDEN_JSON)
    by_seq = {r.seq_no: r for r in rows}
    # general row (A)：is_general + take_unit
    r1 = by_seq[1]
    assert r1.lb_tags.is_general is True
    assert r1.lb_tags.general_role == "take_unit"
    assert r1.cycle.seq_kind == "GM"
    assert len(r1.cycle.slot_tmus) == 7
    # WI-I（electric_driver, repeat）：repeat_counts on slots 3/4/5, tool_vocab set
    r9 = by_seq[9]
    assert r9.tool_vocab == "electric_driver"
    assert r9.cycle.repeat_counts == {"3": 8, "4": 8, "5": 8}
    assert r9.cycle.total_tmu == 190
    assert r9.level.countersignature == "cub40"


def test_rows_from_worksheet_mapping() -> None:
    """read_worksheet() 形狀（computed.breakdown + slot_inputs + level LB 欄）→ ProjectionRow。"""
    data = {
        "rows": [
            {
                "wi_row_id": "00000000-0000-4000-8000-0000000000aa",
                "seq_no": 1,
                "sub_activity": "sub act",
                "key_parts": "KP",
                "hand": "RH",
                "object_vocab_id": "scanner",
                "tool_vocab_id": None,
                "frequency": 2,
                "simo_group_id": None,
                "cycle": {
                    "seq_kind": "CM",
                    "computed": {"breakdown": [
                        {"letter": "A", "tmu": 16}, {"letter": "B", "tmu": 0}, {"letter": "G", "tmu": 6},
                        {"letter": "M", "tmu": 24}, {"letter": "X", "tmu": 48}, {"letter": "I", "tmu": 80},
                        {"letter": "A", "tmu": 16},
                    ]},
                    "total_tmu": 190,
                    "tech_line": "A16 B0 G6 M24 X48 I80 A16",
                    "narrative": "fasten screw",
                    "narrative_en": "fasten screw",
                    "slot_inputs": {"x4": {"x_seconds": 0.216}},
                },
                "level": {
                    "ascription": "main", "level": "2", "countersignature": "cub40",
                    "parent_countersignature": None, "order": 1, "number": None, "number_count": None,
                    "offline": False, "is_general": False, "segment": "screw",
                },
            }
        ]
    }
    rows = rows_from_worksheet(data, vocab={})
    assert len(rows) == 1
    r = rows[0]
    assert r.wi_row_id == "00000000-0000-4000-8000-0000000000aa"
    assert r.object_vocab == "scanner"
    assert r.frequency == 2
    assert r.cycle.slot_tmus == [16, 0, 6, 24, 48, 80, 16]
    assert r.cycle.total_tmu == 190
    assert r.cycle.x_seconds == pytest.approx(0.216)
    assert r.cycle.narrative_en == "fasten screw"
    assert r.level.countersignature == "cub40"
    assert r.lb_tags.segment == "screw"
