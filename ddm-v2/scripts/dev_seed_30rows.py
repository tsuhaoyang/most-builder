"""dev seed：把 30 筆「一般移動(GM) + 控制移動(CM)」工序灌進 worksheet，供試流程。

用真 save_worksheet 服務寫入 → TMU / 敘述 / total 全部一致地由引擎算出。
worksheet = dev_seed_v2.py 種的 55555555…（draft）。先跑 dev_seed_v2.py 確保階層存在。

執行：
  DATABASE_URL=postgresql+asyncpg://howard:111111@localhost:5432/ddm_v2_most \
  PYTHONPATH=src .venv/bin/python scripts/dev_seed_30rows.py
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from ddm_v2.database import get_db_session
from ddm_v2.models.v2.vocab import WorkVocabItem
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
from ddm_v2.schemas.v2.worksheet import LevelFieldsIn, WiRowSaveIn, WorksheetSaveIn
from ddm_v2.services.v2 import worksheet_service as svc

_VOCAB_NS = uuid.UUID("a1b2c3d4-0000-0000-0000-000000000000")


async def ensure_object(session, name: str) -> uuid.UUID:
    """idempotent：依名稱建/取得 object 詞彙，回傳 id。"""
    code = f"DEMOOBJ-{name}"
    row = (await session.execute(select(WorkVocabItem).where(WorkVocabItem.external_code == code))).scalar_one_or_none()
    if row:
        return row.id
    vid = uuid.uuid5(_VOCAB_NS, name)
    session.add(WorkVocabItem(id=vid, external_code=code, kind="object", name_zh=name))
    await session.flush()
    return vid

WS = uuid.UUID("55555555-5555-5555-5555-555555555555")
V_OBJ = uuid.UUID("66666666-6666-6666-6666-666666666666")
V_FROM = uuid.UUID("77777777-7777-7777-7777-777777777777")
V_TO = uuid.UUID("88888888-8888-8888-8888-888888888888")
HANDS = ["RH", "LH", "BH"]


def gm(reach0: float, g: str, reach3: float, p_base: str, addons=None, precision=False) -> CycleIn:
    """一般移動 GM：A B G A B P A（取 a0/g2/a3/p5）。"""
    return CycleIn(
        seq="GM",
        a0=ASlot(reach_cm=reach0),
        g2=GSlot(g_code=g),
        a3=ASlot(reach_cm=reach3),
        p5=PSlot(p_base_code=p_base, p_addon_codes=addons or [], precision=precision),
    )


def cm(reach0: float, g: str, verb: str, dist: float, x: str, x_sec: float, i: str,
       rev: int = 1, dia: float = 0, angle: float = 0) -> CycleIn:
    """控制移動 CM：A B G M X I A（取 a0/g2/m3/x4/i5）。

    M 計價由 verb 種類決定：ladder=距離(distance_cm)、rotate=直徑+圈數、hand=角度、fixed(m_btn/m_screw)=固定。
    `verb=""` → M 格留空（`m_components=[]`）：工作全在 X 的動作（例如刷條碼）沒有受控移動，
    M0 是合法輸入，不必塞佔位分量。
    """
    comps = [MComponent(verb_code=verb, distance_cm=dist, angle_deg=angle,
                        revolutions=rev, diameter_cm=dia)] if verb else []
    return CycleIn(
        seq="CM",
        a0=ASlot(reach_cm=reach0),
        g2=GSlot(g_code=g),
        m3=MSlot(m_components=comps),
        x4=XSlot(x_code=x, x_seconds=x_sec),
        i5=ISlot(i_code=i),
    )


# 30 筆：(描述, 關鍵零件, cycle) —— 模擬一條主機板/模組組裝線，GM 與 CM 交錯
STEPS: list[tuple[str, str, CycleIn]] = [
    # ── 一般移動 GM（拿取、放置、組裝）──
    ("自料盒拿取主機板", "主機板", gm(30, "g_grasp", 25, "p_place_single")),
    ("拿取 DIMM 記憶體模組", "DIMM", gm(20, "g_pick_sel", 15, "p_asm_single", ["a_align"], precision=True)),
    ("放置散熱片於 CPU 上", "散熱片", gm(25, "g_grasp", 20, "p_place_single", ["a_align"], precision=True)),
    ("拿取 M.2 SSD", "SSD", gm(15, "g_pick_small", 10, "p_asm_single", ["a_insert"])),
    ("拿取螺絲 x1", "螺絲", gm(10, "g_pick_small", 8, "p_hold")),
    ("放置擋板至機殼後方", "I/O 擋板", gm(35, "g_grasp", 30, "p_place_single", ["a_snap"])),
    ("拿取排線並對準接頭", "SATA 排線", gm(20, "g_grab", 15, "p_asm_single", ["a_align"], precision=True)),
    ("拿取風扇模組", "風扇", gm(25, "g_grasp", 20, "p_place_multi")),
    ("放置主機板入機殼", "主機板", gm(40, "g_grab", 35, "p_asm_single", ["a_align"], precision=True)),
    ("拿取電源供應器", "PSU", gm(45, "g_grasp", 40, "p_place_single", ["a_press"])),
    ("拿取顯示卡", "顯示卡", gm(30, "g_grasp", 25, "p_asm_single", ["a_align", "a_press"], precision=True)),
    ("整理機殼內線材", "線束", gm(20, "g_pick_collect", 15, "p_toss")),
    ("拿取側板", "側板", gm(50, "g_grab", 45, "p_place_single", ["a_snap"])),
    ("貼上序號標籤", "標籤", gm(15, "g_pick_small", 12, "p_place_single", ["a_align"], precision=True)),
    ("拿取防靜電袋", "防靜電袋", gm(25, "g_grasp", 20, "p_hold")),
    ("放置成品入緩衝棧板", "成品", gm(40, "g_grab", 35, "p_place_multi")),
    ("拿取保護泡棉", "泡棉", gm(20, "g_grasp", 15, "p_place_single")),
    ("拿取出貨外箱", "外箱", gm(45, "g_grab", 40, "p_place_single")),
    # ── 控制移動 CM（鎖附、按壓、製程、檢查）──
    ("電動起子鎖附 CPU 散熱片螺絲 x4", "螺絲x4", cm(20, "g_grasp", "m_screw", 0, "x_none", 0, "i_check", rev=8)),
    ("鎖附主機板固定螺絲 x6", "螺絲x6", cm(18, "g_grasp", "m_screw", 0, "x_none", 0, "i_none", rev=12)),
    ("按壓 DIMM 卡扣到定位", "DIMM 卡扣", cm(15, "g_touch", "m_push", 4, "x_none", 0, "i_check")),
    ("下壓 CPU 拉桿鎖定", "CPU 拉桿", cm(20, "g_grasp", "m_pull", 6, "x_none", 0, "i_check", angle=90)),
    ("按下電源測試按鈕", "測試鈕", cm(25, "g_touch", "m_btn", 2, "x_none", 0, "i_none")),
    ("撕除螢幕保護膜", "保護膜", cm(20, "g_pick_sel", "m_teartape", 15, "x_none", 0, "i_none")),
    # X 用 `x_scan_bar`（刷條形碼）：舊碼 `x_scan` 不在 V2 認證字典裡，會被引擎擋成
    # X_UNKNOWN 讓整份 seed 掛掉。此碼 mode='fixed'，秒數取自字典，故這裡傳 0。
    # M 格留空（verb=""）：刷條碼的工作在 X，手沒有受控移動。原本填的 `m_hand` 是計價維度
    # （pricing_kind='hand'，按手轉角度查表）不是動作動詞，且 angle_deg=0 → M 恆 0 TMU，
    # 純佔位卻讓敘事長出「以手度實施移動」的假句子。tech_line 不變：A10 B0 G3 M0 X6 I6 A0。
    ("掃描條碼建檔", "條碼", cm(25, "g_touch", "", 0, "x_scan_bar", 0, "i_check")),
    ("熱壓導熱膠固化", "導熱膠", cm(15, "g_touch", "m_push", 3, "x_heat", 3.0, "i_none")),
    ("按壓功能測試治具", "測試治具", cm(30, "g_grasp", "m_push", 5, "x_press", 2.0, "i_check")),
    ("旋緊天線接頭", "天線", cm(15, "g_grasp", "m_rotate", 0, "x_none", 0, "i_align1", rev=3, dia=1)),
    ("折合上蓋扣合", "上蓋", cm(25, "g_grab", "m_fold", 10, "x_none", 0, "i_check", angle=120)),
    ("擦拭外殼指紋", "無塵布", cm(20, "g_grasp", "m_wipe", 20, "x_none", 0, "i_none")),
]


# ── Level System 結構示範（讓 export 看得到關係）──
# (label, 型別, 母組, [成員 seq_no])；成員第一個＝頭(帶 main+level)，其餘繼承
GROUPS = [
    ("sub1", "sub", None, [2, 3, 4]),    # DIMM→散熱片→SSD：可移動子序（內部定序）
    ("cub1", "cub", None, [19, 20]),     # 兩道鎖附：同站不可拆
    ("sub2", "sub", None, [26, 27]),     # 熱壓→功能測試：可移動段
    ("cub2", "cub", "sub2", [28, 29]),   # 巢狀：旋天線+折上蓋 同站，且整組在 sub2 內
]
VARIABLE = {6: "6/8", 24: "23~25"}       # 變動主序：/ 列舉(6 或 8)、~ 範圍(23..25) → LB 自由度
NB = [("nb1", 1, [11, 19])]              # 顯卡 與 CPU 鎖附 不可同站（每站≤1）


def build_level_fields() -> dict[int, dict]:
    f = {i: {"ascription": "main", "level": str(i)} for i in range(1, 31)}
    for seq, lvl in VARIABLE.items():
        f[seq]["level"] = lvl
    for label, _typ, parent, members in GROUPS:
        for pos, seq in enumerate(sorted(members), start=1):
            f[seq]["countersignature"] = label
            f[seq]["order"] = pos
            if parent:
                f[seq]["parent_countersignature"] = parent
            if pos == 1:
                f[seq]["ascription"] = "main"          # 頭：保留 main + level
            else:
                f[seq]["ascription"] = None            # 成員：繼承頭
                f[seq]["level"] = None
    for label, cnt, members in NB:
        for seq in members:
            f[seq]["number"] = label
            f[seq]["number_count"] = cnt
    return f


async def main() -> None:
    assert len(STEPS) == 30, f"預期 30 筆，實際 {len(STEPS)}"
    lf = build_level_fields()

    async for session in get_db_session():
        rows: list[WiRowSaveIn] = []
        for i, (desc, parts, cyc) in enumerate(STEPS, start=1):
            obj_id = await ensure_object(session, parts)  # 每步真實零件 → 敘述讀得通
            rows.append(WiRowSaveIn(
                id=uuid.uuid4(), seq_no=i,
                sub_activity=desc, key_parts=parts, hand=HANDS[i % 3],
                object_vocab_id=obj_id, from_vocab_id=V_FROM, to_vocab_id=V_TO,
                frequency=1,
                cycle=cyc,
                level=LevelFieldsIn(coefficient=1, **lf[i]),
            ))
        result = await svc.save_worksheet(session, WS, WorksheetSaveIn(rows=rows))
        await session.commit()
        gm_n = sum(1 for _, _, c in STEPS if c.seq == "GM")
        cm_n = len(STEPS) - gm_n
        print(f"✓ 已寫入 worksheet {WS}")
        print(f"  共 {len(result['rows'])} 列（GM 一般移動 {gm_n} 筆、CM 控制移動 {cm_n} 筆）")
        print(f"  worksheet 合計 = {result['total_tmu']:.1f} TMU")
        print("  前 5 列：")
        for r in result["rows"][:5]:
            c = r["cycle"]
            print(f"    列{r['seq_no']:>2} {c['seq_kind']} {c['total_tmu']:>5.1f}TMU {c['tech_line']:<14} | {c['narrative']}")
        break


if __name__ == "__main__":
    asyncio.run(main())
