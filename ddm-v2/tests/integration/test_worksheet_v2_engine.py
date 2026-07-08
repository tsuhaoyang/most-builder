"""worksheet 儲存 × V2 引擎行為（impl-02 E4/E5/E7）：SIMO 配對正規化 + repeat/override 全程走通。

與 test_worksheet.py（roundtrip/versions/clone/publish/RBAC）互補；本檔鎖：
- E5：simo_with_row_id 配對 → service union-find 正規化為 simo_group_id、合計取群組 max；
      配對指向不存在列/自指 → 422 SIMO_PAIR_INVALID（detail.code）。
- E4/E7：repeat_count 與 manual_override 經 CycleIn 存→讀回 slot_inputs 保留欄位、
      computed.tech_line 標 *、narrative 顯示 ×N、TMU 覆寫/乘算正確。
用 clone 隔離，不動 demo 表（沿用 test_worksheet.py 的 skip 機制）。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"   # dev_seed_v2 demo worksheet
OBJ = "66666666-6666-6666-6666-666666666666"  # dev_seed_v2 vocab「DIMM 內存」
V2 = "MINIMOST_FACTORY_V2"


def _gm_row(seq_no: int, *, frequency: float = 1, **extra) -> dict:
    """GM 黃金列（V2 rule-set，28 TMU）。extra 直接併入 row（simo_* 等）。"""
    return {"id": str(uuid.uuid4()), "seq_no": seq_no, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": frequency, "narrative": "ut v2 engine",
            "cycle": {"seq": "GM", "rule_set_code": V2,
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}, **extra}


async def _fresh_ws(client) -> str:
    """clone demo 表取得隔離 draft；demo 未種則 skip。"""
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    return (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]


# ── E5：SIMO 配對 → 群組正規化 ──
async def test_simo_pair_normalized_to_group_and_total_takes_max(client):
    new = await _fresh_ws(client)
    r1 = _gm_row(1, frequency=1)                 # eff 28
    r2 = _gm_row(2, frequency=2, simo_with_row_id=r1["id"])  # eff 56，與 r1 同步
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [r1, r2]})
    assert r.status_code == 200, r.text
    body = r.json()
    # 正規化：兩列同一 simo_group_id（儲存形式），配對欄不落列
    gids = {row["simo_group_id"] for row in body["rows"]}
    assert len(gids) == 1 and gids != {None}, body["rows"]
    # 合計＝群組取 max(28×1, 28×2)=56，不是相加 84
    assert body["total_tmu"] == 56
    # 讀回持久化一致
    rd = (await client.get(f"/api/v2/worksheets/{new}")).json()
    assert {row["simo_group_id"] for row in rd["rows"]} == gids
    assert rd["total_tmu"] == 56


async def test_simo_pair_to_missing_row_422(client):
    new = await _fresh_ws(client)
    row = _gm_row(1, simo_with_row_id=str(uuid.uuid4()))  # 指向不存在列
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "SIMO_PAIR_INVALID"


async def test_simo_pair_self_reference_422(client):
    new = await _fresh_ws(client)
    row = _gm_row(1)
    row["simo_with_row_id"] = row["id"]  # 自指
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "SIMO_PAIR_INVALID"


# ── E4/E7：repeat + 覆寫 經 CycleIn 存→讀回全程走通 ──
async def test_repeat_and_override_roundtrip(client):
    """CM：推45cm ×3（M=48，E4 只乘動詞分量）+ G 覆寫 3→10（E7）：
    a0(25)=10 + G*=10 + M=48 → 68；slot_inputs 保留欄位；tech_line 標 *；narrative 帶 ×3。"""
    new = await _fresh_ws(client)
    row = {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
           "frequency": 1,
           "cycle": {"seq": "CM", "rule_set_code": V2,
                     "a0": {"reach_cm": 25},
                     "g2": {"g_code": "g_touch",
                            "manual_override": {"tmu": 10, "reason": "IE 實測", "by": "IEC141289"}},
                     "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 45}], "repeat_count": 3},
                     "x4": {"x_code": "x_none"}, "i5": {"i_code": "i_none"}},
           "level": {"ascription": "main", "level": "1"}}
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})
    assert r.status_code == 200, r.text

    rd = (await client.get(f"/api/v2/worksheets/{new}")).json()
    assert len(rd["rows"]) == 1
    cyc = rd["rows"][0]["cycle"]
    assert cyc["total_tmu"] == 68  # 10 + 10(覆寫) + 16×3
    # slot_inputs＝權威原始輸入：repeat 與覆寫欄位原樣保留（可重算/留痕）
    si = cyc["slot_inputs"]
    assert si["m3"]["repeat_count"] == 3
    assert si["g2"]["manual_override"] == {"tmu": 10.0, "reason": "IE 實測", "by": "IEC141289"}
    # computed 快取：tech_line 反映乘算結果與覆寫標記 *
    assert "M48" in cyc["tech_line"]
    assert "G10*" in cyc["tech_line"]
    # narrative（E6/E4）：×N 顯示
    assert "×3" in cyc["narrative"]


async def test_worksheet_save_repeat_out_of_range_422(client):
    """E4 邊界經 worksheet 路徑：repeat_count=0 → 422（CycleIn schema 攔）。"""
    new = await _fresh_ws(client)
    row = _gm_row(1)
    row["cycle"]["g2"]["repeat_count"] = 0
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": [row]})
    assert r.status_code == 422, r.text
