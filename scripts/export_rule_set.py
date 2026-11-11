"""匯出一套 MOST rule-set 的完整參數→index 對照表（A/B/G/P/M/X/I）。

讀 DB 的 rule_* 系列表（版本化資料），輸出：
  - <out>.csv ：長格式（position, group, code, label_zh, label_en, index_tmu, condition, note）
  - <out>.md  ：給 agent 讀的分段對照表

index/tmu 口徑（most_engine）：cycle 合計 = Σ(各 slot index) ；1 TMU = 0.036 秒。
A：max_value = 檔位上界（<= 落該帶）；M 動詞依 pricing_kind 查 fixed/ladder/rotate/hand/foot。
用法：
    PYTHONPATH=src DATABASE_URL=... python scripts/export_rule_set.py MINIMOST_FACTORY_V2 [out_prefix]
"""
from __future__ import annotations

import asyncio
import csv
import sys

from sqlalchemy import text

from ddm_v2.database import get_session_maker


def _band_cond(max_val, unit: str) -> str:
    if max_val is None:
        return f"> 上一檔 ({unit})"
    return f"<= {float(max_val):g} {unit}"


async def fetch(session, rsid: str) -> list[dict]:
    out: list[dict] = []

    # A：三分量距離帶
    rows = (await session.execute(text(
        "SELECT component, max_value, index_value, sort_order FROM rule_a_bands "
        "WHERE rule_set_id=:r AND is_active ORDER BY component, sort_order"), {"r": rsid})).all()
    unit = {"reach": "cm", "foot": "cm", "twist": "deg"}
    for component, max_value, index_value, _ in rows:
        out.append({"position": "A", "group": f"A/{component}", "code": "",
                    "label_zh": f"{component} {_band_cond(max_value, unit.get(component,''))}",
                    "label_en": "", "index_tmu": index_value,
                    "condition": _band_cond(max_value, unit.get(component, "")), "note": "距離帶"})

    # B：身體動作選項
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, index_value FROM rule_b_options "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, idx in rows:
        out.append({"position": "B", "group": "B", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": idx, "condition": "", "note": ""})

    # G：取得控制
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, base_tmu, requires_modifier, modifier_key FROM rule_g_actions "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, tmu, reqmod, modkey in rows:
        note = f"需 modifier={modkey}" if reqmod else ""
        out.append({"position": "G", "group": "G", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": tmu, "condition": "", "note": note})

    # P base
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, base_tmu, category, direction_mode FROM rule_p_bases "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, tmu, cat, dmode in rows:
        note = " / ".join([x for x in [cat, dmode] if x])
        out.append({"position": "P", "group": "P/base", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": tmu, "condition": "", "note": note})
    # P addon
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, delta_tmu, needs_precision, max_select FROM rule_p_addons "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, delta, prec, maxsel in rows:
        note = f"max_select={maxsel}" + ("，需精度" if prec else "")
        out.append({"position": "P", "group": "P/addon", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": f"+{delta}", "condition": "附加項", "note": note})

    # M verbs
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, pricing_kind, fixed_tmu FROM rule_m_verbs "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, kind, fixed in rows:
        idx = fixed if kind == "fixed" else f"(查{kind}表)"
        out.append({"position": "M", "group": "M/verb", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": idx, "condition": "", "note": f"pricing={kind}"})
    # M bands
    for tbl, grp, col, unit in [
        ("rule_m_hand_bands", "M/hand", "max_deg", "deg"),
        ("rule_m_foot_bands", "M/foot", "max_cm", "cm"),
        ("rule_m_ladder_bands", "M/ladder(距離)", "max_cm", "cm"),
    ]:
        rows = (await session.execute(text(
            f"SELECT {col}, tmu, sort_order FROM {tbl} WHERE rule_set_id=:r AND is_active ORDER BY sort_order"),
            {"r": rsid})).all()
        for maxv, tmu, _ in rows:
            out.append({"position": "M", "group": grp, "code": "", "label_zh": _band_cond(maxv, unit),
                        "label_en": "", "index_tmu": tmu, "condition": _band_cond(maxv, unit), "note": ""})
    # M rotation
    rows = (await session.execute(text(
        "SELECT max_diameter_cm, revolutions, tmu, sort_order FROM rule_m_rotation_bands "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for diam, rev, tmu, _ in rows:
        out.append({"position": "M", "group": "M/rotate", "code": "",
                    "label_zh": f"{_band_cond(diam,'cm')} × {rev}圈", "label_en": "",
                    "index_tmu": tmu, "condition": f"{_band_cond(diam,'cm')} rev={rev}", "note": ""})

    # X
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, mode, fixed_seconds FROM rule_x_options "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, mode, secs in rows:
        idx = f"{float(secs):g}s→TMU" if secs is not None else f"({mode})"
        out.append({"position": "X", "group": "X", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": idx, "condition": f"mode={mode}",
                    "note": "X 口徑：秒→TMU，half-up 3 位"})

    # I
    rows = (await session.execute(text(
        "SELECT code, label_zh, label_en, index_value, vision_scope FROM rule_i_options "
        "WHERE rule_set_id=:r AND is_active ORDER BY sort_order"), {"r": rsid})).all()
    for code, zh, en, idx, scope in rows:
        out.append({"position": "I", "group": "I", "code": code, "label_zh": zh,
                    "label_en": en or "", "index_tmu": idx, "condition": "",
                    "note": f"vision_scope={scope}" if scope else ""})

    return out


def write_csv(rows: list[dict], path: str) -> None:
    fields = ["position", "group", "code", "label_zh", "label_en", "index_tmu", "condition", "note"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_md(rows: list[dict], path: str, code: str) -> None:
    lines = [f"# MOST Rule-set 參數對照表：`{code}`", "",
             "TMU 口徑：cycle 合計 = Σ(各 slot index)；1 TMU = 0.036 秒。",
             "A 的 `max_value` = 檔位上界（`<=` 落該帶，超過落下一帶）。",
             "M 動詞依 `pricing_kind` 查 fixed/ladder(距離)/rotate/hand/foot 對應表。",
             "X 以秒數經 half-up 3 位轉 TMU。", ""]
    # 依 position 再 group 分段
    order = ["A", "B", "G", "P", "M", "X", "I"]
    by_pos: dict[str, list[dict]] = {}
    for r in rows:
        by_pos.setdefault(r["position"], []).append(r)
    for pos in order:
        if pos not in by_pos:
            continue
        lines.append(f"## {pos}")
        groups: dict[str, list[dict]] = {}
        for r in by_pos[pos]:
            groups.setdefault(r["group"], []).append(r)
        for grp, items in groups.items():
            lines.append(f"\n### {grp}\n")
            lines.append("| code | label_zh | label_en | index/TMU | 條件 | 備註 |")
            lines.append("|---|---|---|---|---|---|")
            for r in items:
                lines.append(f"| {r['code']} | {r['label_zh']} | {r['label_en']} | "
                             f"{r['index_tmu']} | {r['condition']} | {r['note']} |")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


async def main(code: str, out_prefix: str) -> None:
    sessionmaker = get_session_maker()
    async with sessionmaker() as session:
        rsid = (await session.execute(text(
            "SELECT id FROM rule_sets WHERE code=:c"), {"c": code})).scalar_one_or_none()
        if rsid is None:
            print(f"rule-set 不存在：{code}")
            sys.exit(1)
        rows = await fetch(session, str(rsid))

    write_csv(rows, f"{out_prefix}.csv")
    write_md(rows, f"{out_prefix}.md", code)
    from collections import Counter
    cnt = Counter(r["position"] for r in rows)
    print(f"rule-set={code}  rows={len(rows)}  "
          + "  ".join(f"{k}={cnt[k]}" for k in ['A','B','G','P','M','X','I']))
    print(f"CSV: {out_prefix}.csv\nMD : {out_prefix}.md")


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "MINIMOST_FACTORY_V2"
    prefix = sys.argv[2] if len(sys.argv) > 2 else f"ruleset_{code}"
    asyncio.run(main(code, prefix))
