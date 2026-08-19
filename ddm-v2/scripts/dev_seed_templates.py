"""dev seed：動作範本庫起手式（涵蓋 Touchtime 常見動詞）。idempotent（依 name_zh）。

執行：
  DATABASE_URL=... PYTHONPATH=src .venv/bin/python scripts/dev_seed_templates.py
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from ddm_v2.database import get_db_session
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.schemas.v2.most import (
    ASlot,
    CycleIn,
    GSlot,
    ISlot,
    MComponent,
    MSlot,
    PSlot,
    XSlot,
)


def dump_cycle_template(cyc: CycleIn) -> dict:
    """範本的 cycle 快照一律不含 rule_set_code（ADR-024 §3-2）。

    範本是「怎麼填七格」的樣板，不是回放快照——套用時必須解析 active rule-set
    （ADR-023 §3.5）。既有 16 筆存的是 legacy 的 MINIMOST_FACTORY_V1，
    P2 接上匯入後會用 V1 的值算出靜默錯誤的 TMU，故 migration v2_0022 已把它拔除；
    此處同步排除，否則重跑 seed 會把 key（值為 null）加回去，新舊環境不一致。
    """
    return cyc.model_dump(mode="json", exclude={"rule_set_code"})


def gm(reach0, g, reach3, p_base, addons=None, precision=False):
    return CycleIn(seq="GM", a0=ASlot(reach_cm=reach0), g2=GSlot(g_code=g),
                   a3=ASlot(reach_cm=reach3), p5=PSlot(p_base_code=p_base, p_addon_codes=addons or [], precision=precision))


def cm(reach0, g, verb, dist=0, x="x_none", x_sec=0.0, i="i_none", rev=1, dia=0, angle=0):
    """`verb=""`／None → M 格留空（`m_components=[]`）。

    M0 是引擎的合法輸入，不必塞佔位分量；同 `gm()` 用 `g=""` 表示 B/G 留空的寫法。
    """
    comps = [MComponent(verb_code=verb, distance_cm=dist, angle_deg=angle, revolutions=rev, diameter_cm=dia)] if verb else []
    return CycleIn(seq="CM", a0=ASlot(reach_cm=reach0), g2=GSlot(g_code=g),
                   m3=MSlot(m_components=comps),
                   x4=XSlot(x_code=x, x_seconds=x_sec), i5=ISlot(i_code=i))


# (name_zh, name_en, category, seq, keywords, cycle)
TEMPLATES = [
    ("拿取", "take", "取放", "GM", ["take", "grab", "get", "pick", "拿", "取"], gm(20, "g_grasp", 15, "p_hold")),
    ("放置", "place", "取放", "GM", ["place", "put", "put on", "放", "置"], gm(20, "g_grasp", 20, "p_place_single")),
    ("移動/走步", "move", "搬運", "GM", ["move", "go", "transport", "walk", "trolley", "cart", "走", "移"], gm(0, "", 0, "")),
    ("貼標籤", "stick label", "貼附", "GM", ["stick", "label", "sticker", "貼", "標籤"], gm(15, "g_pick_small", 12, "p_place_single", ["a_align"], precision=True)),
    ("插入/組裝", "insert", "組裝", "GM", ["insert", "assemble", "插", "組"], gm(15, "g_pick_sel", 10, "p_asm_single", ["a_insert"])),
    ("鎖附螺絲", "screw", "鎖附", "CM", ["screw", "lock", "tighten", "fasten", "鎖", "螺絲"], cm(18, "g_grasp", "m_screw", i="i_check")),
    ("撕開/移除", "open/remove", "拆解", "CM", ["open", "remove", "unpack", "tear", "pulltab", "pull tab", "撕", "拆", "移除"], cm(20, "g_pick_sel", "m_tearopen", dist=15)),
    ("按壓/按鈕", "press", "操作", "CM", ["press", "push", "button", "按", "壓"], cm(20, "g_touch", "m_push", dist=4)),
    # X 用 `x_scan_bar`（刷條形碼）：V1 的 `x_scan`（刷條碼(固定)）在 V2 認證字典裡改名分家為
    # x_scan_bar / x_scan_ppid / x_scan_wo，舊碼不存在 → 引擎擋成 X_UNKNOWN。三者同為
    # mode='fixed' 0.216 秒（TMU 相同），本範本是通用「掃描」故取條碼版；PPID／工單二維碼
    # 是特定標籤，語意較窄。fixed 模式的秒數由字典提供、x_seconds 不參與計算，故傳 0
    # （與 dev_seed_30rows.py 一致；留著非零值只會誤導讀者）。
    # M 格留空（`verb=""`）：這個動作的工作全在 X（刷條碼），手沒有受控移動。原本填 `m_hand`
    # 是誤用——`m_hand` 的 pricing_kind='hand' 是**計價維度**（按手轉角度查表）而非動作動詞，
    # 且 angle_deg=0 → M 恆為 0 TMU，只是一顆佔位；敘事還會生出「以手度實施移動」的假句子。
    # 拿掉後 tech_line 不變：A10 B0 G3 M0 X6 I6 A0（M 本來就是 0）。
    ("掃描/檢查", "scan/check", "檢測", "CM", ["scan", "check", "test", "inspect", "掃", "檢查", "測"], cm(25, "g_touch", "", x="x_scan_bar", x_sec=0, i="i_check")),
    ("插接線材", "plug cable", "組裝", "CM", ["plug", "connect", "cable", "接線", "插接"], cm(20, "g_grasp", "m_push", dist=6, i="i_align1")),
    # ── 成品化常見 pattern（含距離分級/精度，降低冷啟動）──
    ("小範圍拿取(≤50cm)", "take short reach", "取放", "GM", ["take short", "近距", "小範圍", "拿近件"], gm(30, "g_grasp", 30, "p_place_single")),
    ("拆箱取件", "unpack take out", "取放", "GM", ["unpack", "take out of box", "拆箱", "取出"], gm(35, "g_grab", 30, "p_hold")),
    ("精密對準裝配", "precision fit", "組裝", "GM", ["fit precisely", "align fit", "精密", "對準裝"], gm(30, "g_pick_sel", 25, "p_asm_single", ["a_align"], precision=True)),
    ("壓合卡扣", "snap fit", "組裝", "GM", ["snap", "clip", "卡扣", "壓合"], gm(25, "g_grasp", 20, "p_asm_single", ["a_snap"])),
    ("電動鎖附(多顆)", "power driver screws", "鎖附", "CM", ["driver", "power screw", "電動鎖", "多螺絲"], cm(18, "g_grasp", "m_screw", i="i_check")),
    ("功能測試(治具)", "function test fixture", "檢測", "CM", ["function test", "fixture", "治具", "測試"], cm(30, "g_grasp", "m_push", dist=5, x="x_press", x_sec=2.0, i="i_check")),
]


async def main() -> None:
    async for s in get_db_session():
        added = 0
        for name_zh, name_en, cat, seq, kws, cyc in TEMPLATES:
            exists = (await s.execute(select(MotionTemplate).where(MotionTemplate.name_zh == name_zh))).scalar_one_or_none()
            if exists:
                continue
            s.add(MotionTemplate(id=uuid.uuid4(), name_zh=name_zh, name_en=name_en, category=cat,
                                 keywords=kws, seq_kind=seq, cycle_template=dump_cycle_template(cyc),
                                 status="standard", created_by="IEC141289"))
            added += 1
        await s.commit()
        print(f"✓ 動作範本：新增 {added} 筆（總定義 {len(TEMPLATES)} 筆）")
        break


if __name__ == "__main__":
    asyncio.run(main())
