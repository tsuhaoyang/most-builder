"""v3 → v2 使用者資料搬遷腳本（WI 庫：MI statements / 動作模組 / WI 模板 / WI Set 專案）。

ADR-022 批次 A-4 擴充（2026-07-14）：
- (b2) v3 most_sequence_items（29 條）→ 各建一個單列模組 category='action'
  （status='standard'、keywords=['v3-import','v3-sequence']、名稱=句子截 60 字）；冪等查重。
- (f) 既有 v3-import 模組（17 筆）重發佈一版，讓版本 rows 帶上每列 computed
  （ADR-022 A-1）；冪等：current version rows 已有 computed 即跳過；
  重發佈後 total 與舊版對帳（TOL 內），漂移即中止。

背景（ADR-014 / ADR-020）：
- 兩邊值權威同源（v2 rule-set = v3 字典經 scripts/import_v3_dictionary.py 轉出），
  故搬遷 = 「v3 slot 碼 → v2 code 轉換 → v2 引擎（most_engine）重算 → 數值對帳」。
- TMU 一律由 most_engine 重算；v3 存的 tmu 只作對帳基準，絕不直接落庫（單一引擎鐵則）。
- SIMO（ADR-020）：v3 `is_simo=1` 的列貢獻 0 → v2 `simo_pair_index` 指向主列（從屬列標記）。
  v3 的 simo_with_row_id 全為 NULL，配對主列採啟發式：取其後最近的非 SIMO 列，無則取其前。

用法：
  cd ddm-v2
  # 1) 對帳（不落庫；rule-set 從 v2 DB 載入 = 走正式 runtime 路徑）
  PYTHONPATH=src DATABASE_URL=postgresql+asyncpg://... \
      .venv/bin/python scripts/migrate_v3_user_data.py            # 預設 --dry-run
  # 2) 落庫（僅在協調者核可對帳表後執行）
  PYTHONPATH=src DATABASE_URL=... .venv/bin/python scripts/migrate_v3_user_data.py --execute

選項：
  --v3-db PATH   v3 SQLite 路徑（預設 ../ddm-v3/apps/api/minimost.db；唯讀開啟）
  --user NO      落庫時的 owner / published_by / created_by 員工編號（預設 IEC141289）

字典漂移碼（X_BLOW_CLEAN / M_PRESS）已依 IE 裁決於 2026-07-14 補進 v2 權威字典
（docs/v3/reference/minimost_ai_dictionary_v1.json）並重生 seed → 正式對映
x_blow_clean / m_press，無相容模式。live DB 需先跑 scripts/sync_rule_set_v2_options.py。

不變式：
- v3 SQLite 以 mode=ro 開啟（絕不寫入來源）。
- 對映不到的 option_code → 該列 FAIL 並列入報告尾端（no-error-bypass）；--execute 遇任何 FAIL 即中止。
- 冪等：模組以 (name_zh, category) 查重、專案以 project_code 查重、詞彙以 (kind, name_zh) 查重，重跑不重建。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_V3_DB = ROOT.parent / "ddm-v3/apps/api/minimost.db"
RULE_SET_CODE = "MINIMOST_FACTORY_V2"
TOL = 0.0015  # v3 存 3 位小數；引擎 total 亦 round 3 位

# ═════════════════════ v3 option_code → v2 對映（值權威：import_v3_dictionary.py 同一套） ═════════════════════

# A 三分量：option_code → (CycleIn ASlot 欄位, 代表物理量)＝檔位上界（<= 語義，落同一帶）；GT 檔用上界+1 落 overflow 帶。
A_VALUE_MAP: dict[str, tuple[str, float]] = {
    "A_REACH_LE_1_2_5CM": ("reach_cm", 2.5),
    "A_REACH_LE_2_5CM": ("reach_cm", 5),
    "A_REACH_LE_4_10CM": ("reach_cm", 10),
    "A_REACH_LE_8_20CM": ("reach_cm", 20),
    "A_REACH_LE_14_35CM": ("reach_cm", 35),
    "A_REACH_LE_24_60CM": ("reach_cm", 60),
    "A_REACH_GT_24_60CM": ("reach_cm", 61),
    "A_HAND_LE_30": ("twist_deg", 30),
    "A_HAND_LE_60": ("twist_deg", 60),
    "A_HAND_LE_120": ("twist_deg", 120),
    "A_HAND_LE_180": ("twist_deg", 180),
    "A_STEP_LE_8_20CM": ("foot_cm", 20),
    "A_STEP_LE_12_30CM": ("foot_cm", 30),
    "A_STEP_LE_18_45CM_1STEP": ("foot_cm", 45),
    "A_STEP_LE_26_65CM": ("foot_cm", 65),
    "A_STEP_GT_26_65CM_2STEP": ("foot_cm", 66),
}
B_MAP = {"B_EYE_MOVE": "b_eye", "B_BEND_OR_SIT": "b_bend", "B_STAND": "b_stand"}
G_MAP = {
    "G_LIGHT_PRESS": "g_tap", "G_TOUCH": "g_touch", "G_LIGHT_TAP": "g_pat",
    "G_GRASP": "g_grasp", "G_PICK": "g_grab", "G_REGRASP": "g_regrasp",
    "G_TRANSFER_HAND": "g_handchange", "G_SELECT": "g_pick_sel",
    "G_SELECT_SMALL": "g_pick_small", "G_SEPARATE": "g_pullout", "G_COLLECT": "g_pick_collect",
}
P_BASE_MAP = {
    "P_THROW": "p_toss", "P_HOLD": "p_hold",
    "P_PLACE_NO_DIRECTION": "p_place_none", "P_PLACE_MULTI_DIRECTION": "p_place_multi",
    "P_PLACE_ONE_DIRECTION": "p_place_single",
    "P_ASSEMBLE_MULTI_DIRECTION": "p_asm_multi", "P_ASSEMBLE_ONE_DIRECTION": "p_asm_single",
}
P_ADDON_MAP = {
    "P_ALIGN_LT_4MM": "a_align", "P_INSERT": "a_insert", "P_DIFFICULT_HANDLE": "a_hard",
    "P_SNAP_FIT": "a_snap", "P_APPLY_PRESSURE": "a_press",
}
# M 距離動詞（option_code = M_<動詞zh>_LE_<吋>_<cm>CM）：動詞 zh → v2 ladder verb code
M_VERB_ZH_MAP = {
    "理": "m_li", "穿": "m_through", "推": "m_push", "拉": "m_pull", "貼附": "m_attach",
    "去除": "m_remove", "撕除": "m_teartape", "折": "m_fold", "擦拭": "m_wipe", "撕開": "m_tearopen",
}
# 距離檔位後綴 → 代表 cm（檔位上界；引擎 ladder <= 語義落同帶）
M_DIST_SUFFIX = {"1_2_5": 2.5, "4_10": 10.0, "10_25": 25.0, "18_45": 45.0, "30_75": 75.0}
M_FIXED_MAP = {"M_PRESS_BUTTON": "m_btn", "M_SLIDE_OUT_SCREW": "m_screw",
               "M_PRESS": "m_press"}  # M_PRESS：v3 字典同步 2026-07-14（IE 裁決補齊）
M_ROTATE_MAP = {  # option_code → (diameter_cm, revolutions)
    "M_ROTATE_D12_1": (12.5, 1), "M_ROTATE_D12_2": (12.5, 2), "M_ROTATE_D12_3": (12.5, 3),
    "M_ROTATE_D50_1": (50.0, 1), "M_ROTATE_D50_2": (50.0, 2),
}
X_MAP = {
    "X_PRESS_MACHINE": "x_press", "X_SNAP_PRESS_MACHINE": "x_snap_press",
    "X_HOT_MELT_MACHINE": "x_heat", "X_DISPENSE_GLUE": "x_glue", "X_SCREW_FIX": "x_screw_fix",
    "X_LASER_MARK": "x_laser", "X_SCAN_PPID": "x_scan_ppid",
    "X_SCAN_WORK_ORDER_QR": "x_scan_wo", "X_SCAN_BARCODE": "x_scan_bar",
    "X_BLOW_CLEAN": "x_blow_clean",  # v3 字典同步 2026-07-14（IE 裁決補齊；user-input-seconds 模式）
}
I_MAP = {
    "I_CHECK_NORMAL": "i_check", "I_CONFIRM_NORMAL": "i_confirm",
    "I_ALIGN_POINT_NORMAL": "i_align1", "I_ALIGN_TWO_POINTS_NORMAL": "i_align2",
    "I_CHECK_OUTSIDE": "i_check_out", "I_CONFIRM_OUTSIDE": "i_confirm_out",
    "I_ALIGN_POINT_OUTSIDE": "i_align1_out", "I_ALIGN_TWO_POINTS_OUTSIDE": "i_align2_out",
}
HAND_MAP = {"right": "RH", "left": "LH", "both": "BH"}
CTX_VOCAB_KIND = {"target_object": "object", "from_location": "from", "to_location": "to"}
VOCAB_REF_KEY = {"object": "object_vocab_id", "from": "from_vocab_id", "to": "to_vocab_id"}


# ═════════════════════ 轉換 ═════════════════════

@dataclass
class ConvertedRow:
    """一列 v3 動作 → v2 ModuleRowIn 素材＋對帳欄。"""
    source: str                       # 出處（statement 名/模板名 + index）
    order_index: int
    seq: str                          # GM / CM
    hand: str                         # LH/RH/BH
    frequency: int
    is_simo: bool
    sentence: str | None
    context_fields: dict[str, str]
    cycle: dict[str, Any] = field(default_factory=dict)   # CycleIn dict
    errors: list[str] = field(default_factory=list)       # 對映失敗（→ FAIL）
    v3_base_tmu: float = 0.0
    v3_contrib_tmu: float = 0.0
    engine_tmu: float | None = None   # v2 引擎重算
    engine_error: str | None = None   # 引擎拒算（SequenceError）

    @property
    def ok(self) -> bool:
        return not self.errors and self.engine_error is None and \
            self.engine_tmu is not None and abs(self.engine_tmu - self.v3_base_tmu) <= TOL

    @property
    def status(self) -> str:
        if self.errors:
            return "FAIL(unmapped)"
        if self.engine_error:
            return "FAIL(engine)"
        if self.engine_tmu is None:
            return "FAIL"
        if abs(self.engine_tmu - self.v3_base_tmu) > TOL:
            return "DIFF"
        return "OK"

    @property
    def v2_contrib_tmu(self) -> float | None:
        if self.engine_tmu is None:
            return None
        return 0.0 if self.is_simo else round(self.engine_tmu * self.frequency, 3)


def _norm_slots(raw: str) -> tuple[list[dict], dict[str, str]]:
    """v3 slot_selections_json 兩種形狀：list 或 {slot_selections, context_fields}。"""
    data = json.loads(raw)
    if isinstance(data, dict):
        return data.get("slot_selections") or [], data.get("context_fields") or {}
    return data, {}


def _a_slot(selections: dict, row: ConvertedRow, slot_name: str, *, return_slot: bool = False) -> dict:
    out: dict[str, Any] = {}
    for key in ("reach_distance", "hand_degree", "foot_step"):
        opt = selections.get(key)
        if not isinstance(opt, dict) or not opt.get("option_code"):
            continue
        code = opt["option_code"]
        mapped = A_VALUE_MAP.get(code)
        if mapped is None:
            row.errors.append(f"{slot_name}: 未知 A option_code {code}")
            continue
        fname, value = mapped
        if return_slot and fname != "reach_cm":
            row.errors.append(f"{slot_name}: 返回格僅計伸手，v3 卻含 {code}")
            continue
        out[fname] = value
    if selections.get("repeat_count") not in (None, 1):
        row.errors.append(f"{slot_name}: A 格不支援 repeat_count={selections['repeat_count']}")
    return out


def _b_slot(selections: dict, row: ConvertedRow, slot_name: str) -> dict:
    opt = selections.get("option")
    if not isinstance(opt, dict) or not opt.get("option_code"):
        return {}
    code = B_MAP.get(opt["option_code"])
    if code is None:
        row.errors.append(f"{slot_name}: 未知 B option_code {opt['option_code']}")
        return {}
    return {"b_code": code}


def _rep(selections: dict) -> dict:
    rc = selections.get("repeat_count")
    return {"repeat_count": int(rc)} if isinstance(rc, (int, float)) and rc != 1 else {}


def _g_slot(selections: dict, row: ConvertedRow) -> dict:
    opt = selections.get("option")
    if not isinstance(opt, dict) or not opt.get("option_code"):
        return {}
    code = G_MAP.get(opt["option_code"])
    if code is None:
        row.errors.append(f"G: 未知 G option_code {opt['option_code']}")
        return {}
    return {"g_code": code, **_rep(selections)}


def _p_slot(selections: dict, row: ConvertedRow) -> dict:
    base = selections.get("base_action")
    out: dict[str, Any] = {}
    if isinstance(base, dict) and base.get("option_code"):
        code = P_BASE_MAP.get(base["option_code"])
        if code is None:
            row.errors.append(f"P: 未知 P base option_code {base['option_code']}")
        else:
            out["p_base_code"] = code
    addons: list[str] = []
    for mod in selections.get("modifiers") or []:
        mc = P_ADDON_MAP.get(mod.get("option_code"))
        if mc is None:
            row.errors.append(f"P: 未知 P addon option_code {mod.get('option_code')}")
        else:
            addons.append(mc)
    if addons:
        out["p_addon_codes"] = addons
    out.update(_rep(selections))
    return out


def _m_component(code: str, row: ConvertedRow) -> dict | None:
    if code in M_FIXED_MAP:
        return {"verb_code": M_FIXED_MAP[code]}
    if code in M_ROTATE_MAP:
        dia, rev = M_ROTATE_MAP[code]
        return {"verb_code": "m_rotate", "diameter_cm": dia, "revolutions": rev}
    # 距離動詞 M_<zh>_LE_<suffix>CM
    if code.startswith("M_") and "_LE_" in code and code.endswith("CM"):
        verb_zh, _, suffix = code[2:-2].partition("_LE_")
        v2c = M_VERB_ZH_MAP.get(verb_zh)
        cm = M_DIST_SUFFIX.get(suffix)
        if v2c is not None and cm is not None:
            return {"verb_code": v2c, "distance_cm": cm}
    row.errors.append(f"M: 未知 M option_code {code}")
    return None


def _m_slot(selections: dict, row: ConvertedRow) -> dict:
    verb = selections.get("verb")
    if not isinstance(verb, dict) or not verb.get("option_code"):
        return {}
    comp = _m_component(verb["option_code"], row)
    out: dict[str, Any] = {"m_components": [comp]} if comp else {}
    out.update(_rep(selections))
    return out


def _x_slot(selections: dict, row: ConvertedRow) -> dict:
    opt = selections.get("x_option")
    if not isinstance(opt, dict) or not opt.get("option_code"):
        return {}
    v3c = opt["option_code"]
    code = X_MAP.get(v3c)
    if code is None:
        row.errors.append(f"X: 未知 X option_code {v3c}")
        return {}
    out: dict[str, Any] = {"x_code": code}
    secs = selections.get("user_input_seconds")
    if secs is not None:
        out["x_seconds"] = float(secs)
    out.update(_rep(selections))
    return out


def _i_slot(selections: dict, row: ConvertedRow) -> dict:
    opt = selections.get("option")
    if not isinstance(opt, dict) or not opt.get("option_code"):
        return {}
    code = I_MAP.get(opt["option_code"])
    if code is None:
        row.errors.append(f"I: 未知 I option_code {opt['option_code']}")
        return {}
    return {"i_code": code, **_rep(selections)}


def convert_row(
    *, source: str, order_index: int, action_type: str, hand_type: str,
    slots_raw: str, context_raw: str | None, sentence: str | None,
    frequency: float, is_simo: bool, base_tmu: float, contrib_tmu: float,
) -> ConvertedRow:
    """一列 v3 動作 → CycleIn dict（碼轉換；TMU 之後由引擎算）。"""
    seq = "GM" if action_type == "GENERAL_MOVE" else "CM"
    row = ConvertedRow(
        source=source, order_index=order_index, seq=seq,
        hand=HAND_MAP.get(hand_type, "BH"), frequency=1, is_simo=is_simo,
        sentence=sentence, context_fields={}, v3_base_tmu=base_tmu, v3_contrib_tmu=contrib_tmu,
    )
    if hand_type not in HAND_MAP:
        row.errors.append(f"未知 hand_type {hand_type!r}")
    if float(frequency) != int(frequency) or int(frequency) < 1:
        row.errors.append(f"frequency={frequency} 非正整數（v2 ModuleRowIn.frequency 為 int≥1）")
    else:
        row.frequency = int(frequency)

    slots, ctx = _norm_slots(slots_raw)
    if context_raw:
        ctx = {**ctx, **(json.loads(context_raw) or {})}
    row.context_fields = {k: (v or "").strip() for k, v in ctx.items()}

    by_key = {s.get("slot_key"): (s.get("selections") or {}) for s in slots}
    cycle: dict[str, Any] = {
        "seq": seq,
        "rule_set_code": RULE_SET_CODE,
        "a0": _a_slot(by_key.get("A1", {}), row, "A1"),
        "b1": _b_slot(by_key.get("B1", {}), row, "B1"),
        "g2": _g_slot(by_key.get("G", {}), row),
        "a6": _a_slot(by_key.get("A3", {}), row, "A3", return_slot=True),
    }
    if seq == "GM":
        cycle["a3"] = _a_slot(by_key.get("A2", {}), row, "A2")
        cycle["b4"] = _b_slot(by_key.get("B2", {}), row, "B2")
        cycle["p5"] = _p_slot(by_key.get("P", {}), row)
    else:
        cycle["m3"] = _m_slot(by_key.get("M", {}), row)
        cycle["x4"] = _x_slot(by_key.get("X", {}), row)
        cycle["i5"] = _i_slot(by_key.get("I", {}), row)
    row.cycle = cycle
    return row


def assign_simo_pairs(rows: list[ConvertedRow]) -> list[int | None]:
    """ADR-020：v3 is_simo 列 → v2 simo_pair_index（從屬列指向主列）。

    v3 的 simo_with_row_id 全為 NULL → 啟發式配對：取其後最近的非 SIMO 列
    （同時動作的主列通常緊隨其後），無則取其前最近的非 SIMO 列。
    """
    out: list[int | None] = [None] * len(rows)
    non_simo = [i for i, r in enumerate(rows) if not r.is_simo]
    for i, r in enumerate(rows):
        if not r.is_simo:
            continue
        after = [j for j in non_simo if j > i]
        before = [j for j in non_simo if j < i]
        if after:
            out[i] = after[0]
        elif before:
            out[i] = before[-1]
        else:
            r.errors.append("SIMO 列找不到可配對的非 SIMO 主列")
    return out


# ═════════════════════ v3 讀取 ═════════════════════

@dataclass
class V3Statement:
    id: str
    name: str
    total_tmu: float
    rows: list[ConvertedRow]


@dataclass
class V3Module:
    """獨立動作模組（action_module_templates 去重後）。"""
    id: str
    name: str
    rows: list[ConvertedRow]
    v3_total: float


@dataclass
class V3WiTemplate:
    id: str
    name: str
    rows: list[ConvertedRow]
    v3_total: float


@dataclass
class V3Project:
    id: str
    code: str
    name: str
    site: str
    bu: str
    process: str
    family: str
    model: str
    description: str
    status: str
    total_tmu: float
    items: list[dict]  # {order_index, source_wi_id, name_snapshot, tmu_snapshot, ...}


def load_v3(
    v3_path: Path,
) -> tuple[list[V3Statement], list[V3Module], list[V3WiTemplate], V3Project | None, list[V3Module]]:
    db = sqlite3.connect(f"file:{v3_path}?mode=ro", uri=True)  # 唯讀
    db.row_factory = sqlite3.Row

    # (a) MI statements + items（主要資產：每 statement = 一個 WI）
    statements: list[V3Statement] = []
    for s in db.execute("SELECT * FROM most_mi_statements ORDER BY created_at"):
        rows = []
        for it in db.execute(
            "SELECT * FROM most_mi_statement_items WHERE statement_id=? ORDER BY order_index", (s["id"],)
        ):
            rows.append(convert_row(
                source=s["name"], order_index=it["order_index"],
                action_type=it["action_type"], hand_type=it["hand_type"],
                slots_raw=it["slot_selections_json"], context_raw=it["context_fields_json"],
                sentence=it["sentence_zh"], frequency=it["frequency"],
                is_simo=bool(it["is_simo"]), base_tmu=it["base_tmu"],
                contrib_tmu=it["total_contribution_tmu"],
            ))
        statements.append(V3Statement(s["id"], s["name"], s["total_tmu"], rows))

    # (b) 獨立動作模組（去重：同 action_type+hand+句子+slot 內容 視為同一模組）
    modules: list[V3Module] = []
    seen: set[tuple] = set()
    for t in db.execute("SELECT * FROM action_module_templates ORDER BY order_index"):
        slots, _ = _norm_slots(t["slot_selections_json"])
        key = (t["action_type"], t["hand_type"], t["generated_sentence_zh"],
               json.dumps(slots, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        row = convert_row(
            source=f"動作模組:{t['generated_sentence_zh']}", order_index=0,
            action_type=t["action_type"], hand_type=t["hand_type"],
            slots_raw=t["slot_selections_json"], context_raw=t["context_fields_json"],
            sentence=t["generated_sentence_zh"], frequency=t["frequency"],
            is_simo=bool(t["is_simo"]), base_tmu=t["base_tmu"],
            contrib_tmu=t["contribution_tmu"],
        )
        modules.append(V3Module(t["id"], t["generated_sentence_zh"], [row], t["effective_tmu"]))

    # (c) WI 模板（items 已是展開快照，逐列轉）
    wi_templates: list[V3WiTemplate] = []
    for w in db.execute("SELECT * FROM wi_templates ORDER BY created_at"):
        rows = []
        for it in db.execute(
            "SELECT * FROM wi_template_items WHERE wi_template_id=? ORDER BY order_index", (w["id"],)
        ):
            rows.append(convert_row(
                source=f"WI模板:{w['wi_name']}", order_index=it["order_index"],
                action_type=it["action_type"], hand_type=it["hand_type"],
                slots_raw=it["slot_selections_json"], context_raw=it["context_fields_json"],
                sentence=it["generated_sentence_zh"], frequency=it["frequency"],
                is_simo=bool(it["is_simo"]), base_tmu=it["base_tmu"],
                contrib_tmu=it["contribution_tmu"],
            ))
        wi_templates.append(V3WiTemplate(w["id"], w["wi_name"], rows, w["total_tmu"]))

    # (b2) ADR-022 A-4：most_sequence_items（29 條）→ 單列 category='action' 模組素材
    actions: list[V3Module] = []
    for t in db.execute("SELECT * FROM most_sequence_items ORDER BY created_at"):
        sent = t["user_edited_sentence_zh"] or t["system_generated_sentence_zh"] or ""
        row = convert_row(
            source=f"動作:{sent[:30]}", order_index=0,
            action_type=t["action_type"], hand_type=t["hand_type"],
            slots_raw=t["selected_slots_json"], context_raw=None,
            sentence=sent or None, frequency=t["frequency"],
            is_simo=bool(t["is_simo"]), base_tmu=t["tmu"],
            contrib_tmu=t["total_contribution_tmu"],
        )
        actions.append(V3Module(t["id"], sent[:60], [row], t["tmu"]))

    # (d) WI Set 專案
    project: V3Project | None = None
    p = db.execute("SELECT * FROM wi_set_projects LIMIT 1").fetchone()
    if p is not None:
        items = [dict(r) for r in db.execute(
            "SELECT * FROM wi_set_project_items WHERE project_id=? ORDER BY order_index", (p["id"],)
        )]
        project = V3Project(
            id=p["id"], code=p["project_code"] or "", name=p["project_name"],
            site=p["site"], bu=p["bu"], process=p["process"], family=p["family"],
            model=p["model"], description=p["description"] or "", status=p["status"],
            total_tmu=p["total_tmu"], items=items,
        )
    db.close()
    return statements, modules, wi_templates, project, actions


# ═════════════════════ 引擎重算 ═════════════════════

def compute_rows(rows: list[ConvertedRow], rsdata: Any) -> None:
    from ddm_v2.most_engine import SequenceError, compute_cycle
    from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

    for r in rows:
        if r.errors:
            continue  # 對映失敗 → FAIL，不進引擎
        try:
            cycle_obj = CycleIn.model_validate(r.cycle)
            result = compute_cycle(cycle_in_to_engine(cycle_obj), rsdata)
            r.engine_tmu = result.total_tmu
        except SequenceError as e:
            r.engine_error = f"[{e.code}] {e}"
        except Exception as e:  # Pydantic 驗證失敗等
            r.engine_error = str(e)


# ═════════════════════ 對帳報告 ═════════════════════

def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:g}"


def print_report(statements: list[V3Statement], modules: list[V3Module],
                 wi_templates: list[V3WiTemplate], project: V3Project | None,
                 actions: list[V3Module]) -> bool:
    all_rows = [r for s in statements for r in s.rows] \
        + [r for m in modules for r in m.rows] + [r for w in wi_templates for r in w.rows] \
        + [r for a in actions for r in a.rows]
    print("=" * 110)
    print("【對帳表 1】MI statement items（主要資產）：v3 存值 vs v2 引擎重算")
    print("=" * 110)
    print(f"{'#':>2} | {'statement / 列':<46} | {'seq':<3} | {'手':<2} | {'v3 tmu':>8} | {'v2 tmu':>8} | {'freq':>4} | {'simo':>4} | 狀態")
    print("-" * 110)
    n = 0
    for s in statements:
        for r in s.rows:
            n += 1
            label = f"{s.name[:20]}…#{r.order_index}" if len(s.name) > 20 else f"{s.name}#{r.order_index}"
            print(f"{n:>2} | {label:<46} | {r.seq:<3} | {r.hand:<2} | {r.v3_base_tmu:>8g} | {_fmt(r.engine_tmu):>8} | {r.frequency:>4} | {('Y' if r.is_simo else ''):>4} | {r.status}")
            for e in r.errors:
                print(f"     ! {e}")
            if r.engine_error:
                print(f"     ! engine: {r.engine_error}")
    print("-" * 110)

    print("\n【對帳表 2】statement 合計（ADR-020：SIMO 列貢獻 0，v3/v2 同語義）")
    print(f"{'statement':<52} | {'v3 total':>9} | {'v2 total':>9} | 狀態")
    print("-" * 90)
    for s in statements:
        if any(r.engine_tmu is None for r in s.rows):
            v2_total: float | None = None
        else:
            v2_total = round(sum(r.v2_contrib_tmu or 0 for r in s.rows), 3)
        status = "-FAIL-" if v2_total is None else ("OK" if abs(v2_total - s.total_tmu) <= TOL else "DIFF")
        print(f"{s.name[:50]:<52} | {s.total_tmu:>9g} | {_fmt(v2_total):>9} | {status}")

    print("\n【對帳表 3】獨立動作模組（action_module_templates 去重後）")
    for m in modules:
        r = m.rows[0]
        print(f"  {m.name[:44]:<46} | v3 {m.v3_total:>8g} | v2 {_fmt(r.engine_tmu):>8} | {r.status}")

    print("\n【對帳表 4】WI 模板（wi_templates）")
    for w in wi_templates:
        if any(r.engine_tmu is None for r in w.rows):
            v2t: float | None = None
        else:
            v2t = round(sum(r.v2_contrib_tmu or 0 for r in w.rows), 3)
        status = "-FAIL-" if v2t is None else ("OK" if abs(v2t - w.v3_total) <= TOL else "DIFF")
        print(f"  {w.name[:44]:<46} | v3 {w.v3_total:>8g} | v2 {_fmt(v2t):>8} | {status}  ({len(w.rows)} 列)")

    if project is not None:
        stmt_total = {s.id: (round(sum(r.v2_contrib_tmu or 0 for r in s.rows), 3)
                             if all(r.engine_tmu is not None for r in s.rows) else None)
                      for s in statements}
        v2_proj = 0.0
        missing = 0
        for it in project.items:
            t = stmt_total.get(it["source_wi_id"])
            if t is None:
                missing += 1
            else:
                v2_proj += t
        v2_proj = round(v2_proj, 3)
        status = "-FAIL-" if missing else ("OK" if abs(v2_proj - project.total_tmu) <= TOL else "DIFF")
        print(f"\n【對帳表 5】WI Set 專案：{project.name}")
        print(f"  items={len(project.items)} | v3 total {project.total_tmu:g} | v2 total {v2_proj:g}"
              + (f"（{missing} 項因列 FAIL 缺值）" if missing else "") + f" | {status}")

    print("\n【對帳表 6】ADR-022 A-4：most_sequence_items → category='action' 單列模組（29 條）")
    print(f"{'#':>2} | {'名稱（句子截 60 字）':<52} | {'seq':<3} | {'手':<2} | {'v3 tmu':>8} | {'v2 tmu':>8} | 狀態")
    print("-" * 100)
    for n, a in enumerate(actions, start=1):
        r = a.rows[0]
        print(f"{n:>2} | {a.name[:50]:<52} | {r.seq:<3} | {r.hand:<2} | {a.v3_total:>8g} | {_fmt(r.engine_tmu):>8} | {r.status}")

    # 未對映清單（no-error-bypass：不得靜默略過）
    unmapped: dict[str, list[str]] = {}
    for r in all_rows:
        for e in r.errors:
            unmapped.setdefault(e, []).append(f"{r.source}#{r.order_index}")
    print("\n【未對映 / 失敗清單】")
    if unmapped:
        for e, locs in unmapped.items():
            print(f"  ✗ {e}  ← {', '.join(locs)}")
    engine_fails = [(r.source, r.order_index, r.engine_error) for r in all_rows if r.engine_error]
    for src, oi, msg in engine_fails:
        print(f"  ✗ 引擎拒算 {src}#{oi}: {msg}")
    if not unmapped and not engine_fails:
        print("  （無）")

    diffs = [r for r in all_rows if r.status == "DIFF"]
    print("\n【摘要】")
    ok = sum(1 for r in all_rows if r.status == "OK")
    print(f"  列級：{ok}/{len(all_rows)} OK，DIFF {len(diffs)}，FAIL {len(all_rows) - ok - len(diffs)}")
    return ok == len(all_rows)


# ═════════════════════ --execute 落庫 ═════════════════════

async def get_or_create_vocab(session: Any, cache: dict, kind: str, name: str, user: str) -> uuid.UUID:
    from sqlalchemy import select

    from ddm_v2.models.v2.vocab import WorkVocabItem

    key = (kind, name)
    if key in cache:
        return cache[key]
    existing = (await session.execute(
        select(WorkVocabItem).where(
            WorkVocabItem.kind == kind, WorkVocabItem.name_zh == name,
            WorkVocabItem.is_active.is_(True))
    )).scalars().first()
    if existing is not None:
        cache[key] = existing.id
        return existing.id
    # source_system CHECK 僅允許 local/mes/erp/plm/imported → 用 'imported'，
    # 來源批次記在 attributes（規格說 'v3-import'，受 CHECK 限制改記於 attributes）。
    item = WorkVocabItem(
        id=uuid.uuid4(), kind=kind, name_zh=name,
        source_system="imported",
        attributes={"source": "v3-import", "imported_by": user},
    )
    session.add(item)
    await session.flush()
    cache[key] = item.id
    return item.id


async def build_vocab_refs(session: Any, cache: dict, row: ConvertedRow, user: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for ctx_key, kind in CTX_VOCAB_KIND.items():
        name = row.context_fields.get(ctx_key, "")
        if not name:
            continue
        vid = await get_or_create_vocab(session, cache, kind, name, user)
        refs[VOCAB_REF_KEY[kind]] = str(vid)
    return refs


async def upsert_module(
    session: Any, *, name: str, category: str | None, rows: list[ConvertedRow],
    user: str, vocab_cache: dict, stats: dict,
    keywords: list[str] | None = None, assign_pairs: bool = True,
) -> uuid.UUID:
    """建 motion_module + publish rows + status='standard'（冪等：name+category 查重跳過）。

    assign_pairs=False（ADR-022 category='action' 單列素材）：SIMO 配對屬 WI 情境語義，
    單動作素材不落 simo_pair_index（v3 is_simo 僅作對帳參考）。
    """
    from sqlalchemy import select

    from ddm_v2.auth.deps import ROLE_ORDER
    from ddm_v2.models.v2.motion_module import MotionModule
    from ddm_v2.schemas.v2.most import CycleIn
    from ddm_v2.schemas.v2.motion_module import ModuleRowIn, MotionModuleCreate, PublishRequest
    from ddm_v2.services.v2 import motion_module_service as svc

    stmt = select(MotionModule).where(MotionModule.name_zh == name)
    stmt = stmt.where(MotionModule.category == category) if category is not None \
        else stmt.where(MotionModule.category.is_(None))
    existing = (await session.execute(stmt)).scalars().first()
    if existing is not None:
        stats["skipped_modules"] += 1
        return existing.id

    created = await svc.create_module(
        session,
        MotionModuleCreate(name_zh=name, category=category, scope="global",
                           keywords=list(keywords) if keywords else ["v3-import"]),
        current_user_no=user, current_user_level=ROLE_ORDER["admin"],
    )
    pair_idx: list[int | None] = assign_simo_pairs(rows) if assign_pairs else [None] * len(rows)
    module_rows = []
    for i, r in enumerate(rows):
        refs = await build_vocab_refs(session, vocab_cache, r, user)
        module_rows.append(ModuleRowIn(
            sub_activity=r.sentence, hand=r.hand, frequency=r.frequency,
            simo_pair_index=pair_idx[i], vocab_refs=refs,
            cycle=CycleIn.model_validate(r.cycle),
        ))
    ver = await svc.publish_version(
        session, created.id,
        PublishRequest(rows=module_rows, rule_set_code=RULE_SET_CODE),
        current_user_no=user,
    )
    # (e) 使用者已認證的資料 → 直接設 standard（promote 端點目前 501，走 DB 層）
    m = await session.get(MotionModule, created.id)
    m.status = "standard"
    await session.flush()
    stats["created_modules"] += 1
    stats["published_tmu"][name] = float(ver.total_tmu)
    return created.id


async def execute_migration(
    statements: list[V3Statement], modules: list[V3Module],
    wi_templates: list[V3WiTemplate], project: V3Project | None, user: str,
    actions: list[V3Module],
) -> dict:
    from sqlalchemy import select

    from ddm_v2.database import get_session_maker
    from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion
    from ddm_v2.models.v2.wi_set import WiSetItem, WiSetProject

    stats: dict[str, Any] = {
        "created_modules": 0, "skipped_modules": 0,
        "created_projects": 0, "skipped_projects": 0,
        "republished": 0, "skipped_republish": 0,
        "published_tmu": {},
    }
    vocab_cache: dict = {}
    maker = get_session_maker()
    async with maker() as session:
        stmt_module_id: dict[str, uuid.UUID] = {}
        # (a) 13 個 MI statement → motion_module(category='wi-template') + publish + standard
        for s in statements:
            mid = await upsert_module(
                session, name=s.name, category="wi-template", rows=s.rows,
                user=user, vocab_cache=vocab_cache, stats=stats,
            )
            stmt_module_id[s.id] = mid
        # (b) 獨立動作模組（去重後）→ category 一般（None）
        for m in modules:
            await upsert_module(
                session, name=m.name, category=None, rows=m.rows,
                user=user, vocab_cache=vocab_cache, stats=stats,
            )
        # (b2) ADR-022 A-4：29 條 most_sequence_items → 單列 category='action' 模組
        for a in actions:
            await upsert_module(
                session, name=a.name, category="action", rows=a.rows,
                user=user, vocab_cache=vocab_cache, stats=stats,
                keywords=["v3-import", "v3-sequence"], assign_pairs=False,
            )
        # (c) wi_templates → 同 (a) 模式（items 已為展開快照）
        for w in wi_templates:
            await upsert_module(
                session, name=w.name, category="wi-template", rows=w.rows,
                user=user, vocab_cache=vocab_cache, stats=stats,
            )
        # (f) ADR-022 A-4：既有 v3-import 模組重發佈一版 → rows 帶上每列 computed。
        #     冪等：current version rows[0] 已有 computed 即跳過；名稱/專案快照不動。
        #     重發佈後 total 對帳（引擎同語義重算，TOL 內），漂移即中止（no-error-bypass）。
        from ddm_v2.schemas.v2.motion_module import ModuleRowIn as _RowIn
        from ddm_v2.schemas.v2.motion_module import PublishRequest as _PubReq
        from ddm_v2.services.v2 import motion_module_service as _svc

        v3_mods = (await session.execute(
            select(MotionModule).where(MotionModule.keywords.contains(["v3-import"]))
        )).scalars().all()
        for mod in v3_mods:
            if mod.current_version == 0:
                continue
            ver = (await session.execute(
                select(MotionModuleVersion).where(
                    MotionModuleVersion.module_id == mod.id,
                    MotionModuleVersion.version_no == mod.current_version)
            )).scalar_one()
            if ver.rows and isinstance(ver.rows[0], dict) and "computed" in ver.rows[0]:
                stats["skipped_republish"] += 1
                continue
            rows_in = [_RowIn.model_validate(r) for r in ver.rows]
            new_ver = await _svc.publish_version(
                session, mod.id,
                _PubReq(rows=rows_in, rule_set_code=RULE_SET_CODE),
                current_user_no=user,
            )
            if abs(float(new_ver.total_tmu) - float(ver.total_tmu)) > TOL:
                raise RuntimeError(
                    f"重發佈 total 漂移：{mod.name_zh} v{ver.version_no}={ver.total_tmu} "
                    f"→ v{new_ver.version_no}={new_ver.total_tmu}（中止，no-error-bypass）")
            stats["republished"] += 1
        # (d) wi_set_project + items（wi_template_id → (a) 模組；快照由伺服器端解析同款邏輯回填）
        if project is not None:
            # v3 project_code 為空字串；v2 要求非空唯一 → 以 project_name 作 code（偏差已記錄於報告）
            code = project.code or project.name
            existing = (await session.execute(
                select(WiSetProject).where(WiSetProject.project_code == code)
            )).scalars().first()
            if existing is not None:
                stats["skipped_projects"] += 1
            else:
                proj = WiSetProject(
                    id=uuid.uuid4(), project_code=code, name=project.name,
                    site=project.site, bu=project.bu, process=project.process,
                    family=project.family, model=project.model,
                    description=project.description or None,
                    status="draft", created_by=user,
                )
                session.add(proj)
                await session.flush()
                for seq_no, it in enumerate(project.items, start=1):
                    tmid = stmt_module_id.get(it["source_wi_id"])
                    if tmid is None:
                        raise RuntimeError(
                            f"wi_set item #{it['order_index']} 對不到 statement 模組："
                            f"{it['wi_name_snapshot']}（no-error-bypass：中止）")
                    module = await session.get(MotionModule, tmid)
                    if module is None:
                        raise RuntimeError(f"模組 {tmid} 不存在（不應發生）")
                    ver = (await session.execute(
                        select(MotionModuleVersion).where(
                            MotionModuleVersion.module_id == tmid,
                            MotionModuleVersion.version_no == module.current_version)
                    )).scalar_one()
                    session.add(WiSetItem(
                        id=uuid.uuid4(), project_id=proj.id, seq_no=seq_no,
                        wi_template_id=tmid,
                        wi_code_snapshot=None,
                        wi_name_snapshot=module.name_zh,
                        action_count_snapshot=len(ver.rows),
                        total_tmu_snapshot=float(ver.total_tmu),
                        total_seconds_snapshot=float(ver.total_seconds),
                        notes=it.get("note"),
                    ))
                await session.flush()
                stats["created_projects"] += 1
        await session.commit()
    return stats


# ═════════════════════ main ═════════════════════

async def amain() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="落庫（預設 dry-run 只對帳）")
    ap.add_argument("--dry-run", action="store_true", help="（預設）解析＋引擎重算＋對帳，不落庫")
    ap.add_argument("--v3-db", type=Path, default=DEFAULT_V3_DB)
    ap.add_argument("--user", default="IEC141289", help="落庫 owner/published_by/created_by")
    args = ap.parse_args()
    if args.execute and args.dry_run:
        ap.error("--execute 與 --dry-run 互斥")

    if not args.v3_db.exists():
        print(f"[中止] 找不到 v3 SQLite：{args.v3_db}", file=sys.stderr)
        return 1

    statements, modules, wi_templates, project, actions = load_v3(args.v3_db)
    n_items = sum(len(s.rows) for s in statements)
    print(f"v3 盤點：MI statements {len(statements)}（items {n_items}）、"
          f"獨立動作模組 {len(modules)}（去重後）、WI 模板 {len(wi_templates)}、"
          f"WI Set 專案 {1 if project else 0}、"
          f"sequence items（→ category='action'）{len(actions)}")

    # rule-set：從 v2 DB 載（正式 runtime 路徑；值 = v3 字典經 import_v3_dictionary 轉出）
    import os
    if not os.environ.get("DATABASE_URL"):
        print("[中止] 需要 DATABASE_URL（rule-set 從 v2 DB 載入）", file=sys.stderr)
        return 1
    from ddm_v2.database import get_session_maker
    from ddm_v2.most_engine import load_rule_set_from_db

    maker = get_session_maker()
    async with maker() as session:
        rsdata = await load_rule_set_from_db(session, RULE_SET_CODE)
        # dry-run 不落庫：此 session 僅讀 rule-set，不 commit

    all_row_groups = [s.rows for s in statements] + [m.rows for m in modules] \
        + [w.rows for w in wi_templates] + [a.rows for a in actions]
    for rows in all_row_groups:
        compute_rows(rows, rsdata)

    all_green = print_report(statements, modules, wi_templates, project, actions)

    if not args.execute:
        print("\n[dry-run] 未落庫。核對帳表後以 --execute 執行。")
        return 0 if all_green else 1

    if not all_green:
        print("\n[中止] 對帳有 FAIL/DIFF，--execute 不執行（no-error-bypass）。", file=sys.stderr)
        return 1

    stats = await execute_migration(statements, modules, wi_templates, project, args.user, actions)
    print("\n【執行結果】")
    print(f"  建立模組 {stats['created_modules']}、跳過（已存在）{stats['skipped_modules']}")
    print(f"  建立專案 {stats['created_projects']}、跳過 {stats['skipped_projects']}")
    print(f"  重發佈（rows 補 computed）{stats['republished']}、跳過（已有 computed）{stats['skipped_republish']}")
    for name, tmu in stats["published_tmu"].items():
        print(f"    - {name}: total_tmu={tmu:g}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
