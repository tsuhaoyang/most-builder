"""B7-6（ADR-035 D10 §3.4）：mappers.role_type 依 machine_unattended 三態。

machine ⇔ CM ∧ x_seconds≥1 ∧ machine_unattended==True；null／false → human。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.mappers import role_type
from ddm_v2.lb_projection.models import ProjectionRow

pytestmark = pytest.mark.unit


def _cm(x_seconds, machine_unattended):
    return ProjectionRow.model_validate({
        "wi_row_id": "00000000-0000-4000-8000-000000000001", "seq_no": 1,
        "cycle": {"seq_kind": "CM", "slot_tmus": [0, 0, 0, 0, 0, 0, 0], "total_tmu": 0, "x_seconds": x_seconds},
        "level": {"ascription": "main", "level": "1"},
        "lb_tags": {"machine_unattended": machine_unattended},
    })


def test_role_type_machine_when_unattended_true():
    assert role_type(_cm(2.0, True)) == "machine"


def test_role_type_human_when_unattended_none():
    assert role_type(_cm(2.0, None)) == "human"   # 未回答 → human


def test_role_type_human_when_unattended_false():
    assert role_type(_cm(2.0, False)) == "human"  # 人要顧 → human


def test_role_type_human_when_x_below_1():
    assert role_type(_cm(0.2, True)) == "human"   # x<1 → human（不論三態）
