"""v2_0042 migration 驗證：拔掉範本庫 M 格的計價維度佔位（`m_hand`／`m_foot` 且量值為 0）。

直接執行 migration 模組匯出的**同一份 SQL 常數**（不是測試裡另抄一份的近似品），
全程在 conftest 的 rollback transaction 內，不落真實 DB。

涵蓋：
1. 孤兒零角度 `m_hand` → M 格清空；
2. **TMU 恆等**——清空後仍是 A10 B0 G3 M0 X6 I6 A0＝25 TMU，且零角度手度本來就貢獻 0
   （修前的 payload 已被引擎判非法，故以合法的伴隨組合舉證）；
3. 不誤傷：真動詞、真動詞＋手度的複合 M、非零角度的手度、GM 範本（m3 為 null）都原封不動；
4. 冪等：再跑一次 no-op；
5. 真實 DB 現況：全表沒有任何範本拿 `m_hand`／`m_foot` 當唯一 m_component；
6. 真實 DB 的「掃描/檢查」範本 M 格為空，且照樣算出 A10 B0 G3 M0 X6 I6 A0。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import uuid

import pytest
from sqlalchemy import text

from ddm_v2.most_engine import build_from_seed_v2, compute_cycle
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

pytestmark = pytest.mark.integration


def _load_migration():
    p = (
        pathlib.Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions_v2"
        / "v2_0042_motion_template_m_placeholder.py"
    )
    spec = importlib.util.spec_from_file_location("_v2_0042", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()
RS_V2 = build_from_seed_v2()

# 缺陷本尊：M 格只有一顆 `m_hand`、角度 0（＝計價維度當動詞用的佔位，恆 0 TMU）。
_SCAN_CYCLE = {
    "seq": "CM",
    "a0": {"reach_cm": 25},
    "b1": {},
    "g2": {"g_code": "g_touch"},
    "m3": {"m_components": [
        {"verb_code": "m_hand", "angle_deg": 0.0, "distance_cm": 0.0, "revolutions": 1, "diameter_cm": 0.0},
    ]},
    "x4": {"x_code": "x_scan_bar", "x_seconds": 0.0},
    "i5": {"i_code": "i_check"},
    "a6": {},
}
_GM_CYCLE = {
    "seq": "GM",
    "a0": {"reach_cm": 20},
    "b1": {},
    "g2": {"g_code": "g_grasp"},
    "a3": {"reach_cm": 15},
    "b4": {},
    "p5": {"p_base_code": "p_hold"},
    "a6": {},
}


def _with_m(components: list[dict]) -> dict:
    return {**_SCAN_CYCLE, "m3": {"m_components": components}}


async def _insert_template(session, cycle: dict, *, seq_kind: str) -> uuid.UUID:
    """繞過 ORM 直接 INSERT，確保測到的是 migration 的 SQL 而非應用層行為。"""
    tid = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO motion_templates
                (id, name_zh, seq_kind, keywords, cycle_template, status,
                 created_at, updated_at)
            VALUES (:id, :name, :seq, '{}'::text[], CAST(:cyc AS jsonb), 'draft', NOW(), NOW())
            """
        ),
        {"id": tid, "name": f"mig42-{tid.hex[:8]}", "seq": seq_kind, "cyc": json.dumps(cycle)},
    )
    return tid


async def _cycle_of(session, tid: uuid.UUID) -> dict:
    return (await session.execute(
        text("SELECT cycle_template FROM motion_templates WHERE id = :i"), {"i": tid},
    )).scalar_one()


def _compute(payload: dict):
    """走與 import_service 完全相同的路徑：dict → CycleIn → engine。"""
    return compute_cycle(cycle_in_to_engine(CycleIn.model_validate(payload)), RS_V2)


async def test_strip_empties_lone_zero_angle_hand_placeholder(db_session):
    tid = await _insert_template(db_session, _SCAN_CYCLE, seq_kind="CM")

    await db_session.execute(text(MIG.SQL_STRIP_M_PLACEHOLDER))

    m3 = (await _cycle_of(db_session, tid))["m3"]
    assert m3["m_components"] == [], "計價維度佔位應被整顆拔掉，M 格留空（M0 是合法輸入）"


async def test_stripped_template_keeps_its_tech_line(db_session):
    """清空後照樣是原本的 A10 B0 G3 M0 X6 I6 A0＝25 TMU（M 本來就是 0）。

    修前的 payload **不能**拿去 `compute_cycle` 對照：引擎已加上
    `M_COMPANION_WITHOUT_VERB`（孤兒計價維度非法），那正是這條 migration 要清掉的東西。
    「拔掉不改值」的舉證改由 `test_zero_angle_hand_contributes_nothing` 用合法的
    伴隨組合（真動詞＋零角度手度）證明。
    """
    tid = await _insert_template(db_session, _SCAN_CYCLE, seq_kind="CM")

    await db_session.execute(text(MIG.SQL_STRIP_M_PLACEHOLDER))

    after = _compute(await _cycle_of(db_session, tid))
    assert after.tech_line == "A10 B0 G3 M0 X6 I6 A0"
    assert after.total_tmu == 25
    assert after.slot_tmus[3] == 0, "M 格本來就是 0，拔掉佔位不該讓它變成別的值"


def test_zero_angle_hand_contributes_nothing():
    """本 migration 對 TMU 恆等的依據：零角度手度貢獻 0 TMU（M 取各分量 max）。

    用合法的伴隨組合（`m_push` ＋ 零角度 `m_hand`）對照純動詞——兩者相等，
    代表被拔掉的那顆佔位從來沒有進到 max 裡。
    """
    verb_only = [{"verb_code": "m_push", "angle_deg": 0.0, "distance_cm": 45.0,
                  "revolutions": 1, "diameter_cm": 0.0}]
    with_hand = verb_only + [{"verb_code": "m_hand", "angle_deg": 0.0, "distance_cm": 0.0,
                              "revolutions": 1, "diameter_cm": 0.0}]

    # 先釘死前提：`max()` 相等只證明「沒超過動詞」，migration 的 TMU 恆等要的是「這顆＝0」。
    assert RS_V2.hand_tmu(0) == 0
    assert _compute(_with_m(with_hand)).slot_tmus[3] == _compute(_with_m(verb_only)).slot_tmus[3]


@pytest.mark.parametrize(
    "label, components",
    [
        # 真動詞：這是正常的 M 格，碰不得。
        ("real_verb", [{"verb_code": "m_push", "angle_deg": 0.0, "distance_cm": 4.0,
                        "revolutions": 1, "diameter_cm": 0.0}]),
        # 真動詞＋手度的複合 M：合法（手度是其中一個計價維度），拔了會改 TMU。
        ("verb_plus_hand", [
            {"verb_code": "m_push", "angle_deg": 0.0, "distance_cm": 45.0,
             "revolutions": 1, "diameter_cm": 0.0},
            {"verb_code": "m_hand", "angle_deg": 0.0, "distance_cm": 0.0,
             "revolutions": 1, "diameter_cm": 0.0},
        ]),
        # 非零角度的手度：那是真的有值的一格，拔了就是竄改工時。
        ("hand_with_angle", [{"verb_code": "m_hand", "angle_deg": 180.0, "distance_cm": 0.0,
                              "revolutions": 1, "diameter_cm": 0.0}]),
        # 已經是空的：no-op。
        ("already_empty", []),
    ],
)
async def test_strip_does_not_touch_other_m_slots(db_session, label, components):
    tid = await _insert_template(db_session, _with_m(components), seq_kind="CM")

    await db_session.execute(text(MIG.SQL_STRIP_M_PLACEHOLDER))

    assert (await _cycle_of(db_session, tid))["m3"]["m_components"] == components, label


async def test_strip_does_not_touch_gm_templates(db_session):
    """GM 範本沒有 m3（值為 null）→ 型別守衛擋掉，不該被 jsonb_set 生出欄位。"""
    tid = await _insert_template(db_session, _GM_CYCLE, seq_kind="GM")

    await db_session.execute(text(MIG.SQL_STRIP_M_PLACEHOLDER))

    assert (await _cycle_of(db_session, tid)).get("m3") is None


async def test_strip_is_idempotent(db_session):
    tid = await _insert_template(db_session, _SCAN_CYCLE, seq_kind="CM")

    await db_session.execute(text(MIG.SQL_STRIP_M_PLACEHOLDER))
    first = await _cycle_of(db_session, tid)
    second_run = await db_session.execute(text(MIG.SQL_STRIP_M_PLACEHOLDER))

    assert second_run.rowcount == 0, "跑過一次後應選不到列"
    assert await _cycle_of(db_session, tid) == first


async def test_no_lone_pricing_dimension_component_left_in_real_db(db_session):
    """環境見證：全表沒有任何範本拿 `m_hand`／`m_foot` 當唯一 m_component。

    比 migration 的 WHERE 更嚴（不限角度／距離為 0）是刻意的：引擎即將要求
    `pricing_kind='hand'/'foot'` 的分量必須有真動詞作伴，所以**任何**孤兒計價維度分量
    都是未來的 422，不只是零量值那種。
    """
    left = (await db_session.execute(text(
        """
        SELECT count(*) FROM motion_templates
        WHERE  CASE
                   WHEN jsonb_typeof(cycle_template -> 'm3' -> 'm_components') <> 'array' THEN false
                   ELSE jsonb_array_length(cycle_template -> 'm3' -> 'm_components') = 1
                        AND cycle_template -> 'm3' -> 'm_components' -> 0 ->> 'verb_code'
                            IN ('m_hand', 'm_foot')
               END
        """
    ))).scalar_one()
    assert left == 0, f"仍有 {left} 筆範本以計價維度當唯一 M 分量——該環境沒跑到 v2_0042"


async def test_seeded_scan_template_has_empty_m_and_same_tech_line(db_session):
    """實裝見證：真實 DB 的「掃描/檢查」範本 M 格為空，且照樣算出原本的 tech_line。"""
    cyc = (await db_session.execute(text(
        "SELECT cycle_template FROM motion_templates WHERE name_zh = '掃描/檢查'"
    ))).scalar_one_or_none()
    if cyc is None:
        pytest.skip("此環境未跑 dev_seed_templates.py")

    assert cyc["m3"]["m_components"] == []
    result = _compute(cyc)
    assert result.tech_line == "A10 B0 G3 M0 X6 I6 A0"
    assert result.total_tmu == 25
