"""dev seed：MOST 選項／詞彙／範本英文標籤機器翻譯灌值（ADR-032 Phase B/C）。idempotent。

**Phase C 增補（`sentence_text_en`）**：除了 Phase B 的 `label_en`／`name_en`（側表
`field='label'`／`'name'`），本檔另灌 7 張選項表的 `sentence_text_en`（側表
`field='sentence'`，值域早已由 `i18n_service._RULE_OPTION_FIELDS` 允許）。標籤與句面
是**兩個不同語意的欄**（ADR-032 1.2a）：標籤要能在下拉選單中辨義（"Align (precision
<4mm)"），句面要能入句（"aligned to within 4 mm"），所以是兩張翻譯表、兩組側表記錄。
句面的英文資料契約（不含連接詞、G 不帶受詞、P/M 自足含代名詞、X 動名詞、I 過去分詞）
見 `most_engine/narrative_en.py` 檔頭——**改那份契約必須同時改這裡的翻譯表**。

**（2026-08-20 更新：此段已過期，保留以說明演進）** Phase C 當下
`i18n_service._candidates_sql()` 只列 `field='label'` 候選，故句面的覆核狀態
寫得進側表卻永遠查不出來、不會進待審 UI。D6 覆核 mutation 輪次已補上兩種 field
都出候選，`summary()` 的 rule_option 分母因此由 63 變成 126（ADR-032 D6
「分母修正」補記）。本檔灌值的行為沒有變，變的是清單看不看得到那批句面。

執行：
  DATABASE_URL=... PYTHONPATH=src .venv/bin/python scripts/dev_seed_i18n_labels.py

**翻譯方式**：本檔的翻譯表由工程端依 MOST 領域知識直接產生（ADR-032 D2「機器翻譯」
一詞不代表接外部翻譯 API——這批是專業術語，判型矩陣／同義詞治理已處理過大量
同一批詞的語意分工），每一條登記到 `i18n_review_state` 時一律標
`source='machine'`（未經 IE 覆核的初翻，不是 'human'）。

**side 表存在 ≠ `_en` 欄位已填（2026-08-18 覆審修正，S1）**：`i18n_review_state`
的 UNIQUE 鍵刻意不含 `rule_set_id`（D5），但 `label_en`／`name_en` 是**每個
rule-set 版本各自一欄**。若把「側表列是否存在」當成「這一列 `_en` 該不該填」的
判準，掃描順序一旦先碰到 draft、後碰到 active，active 的同一個 option code
會因為側表列已由 draft 建立而被跳過，`_en` 永遠留 NULL——且因為是冪等腳本，
重跑也修不回來（後續每次都判「已有側表列」而跳過）。**修法**：側表列的建立
（`upsert_review_state`）與 `_en` 欄位的填值是兩件事，分開判斷——側表沒有列
就建一次（不重覆寫、不覆蓋既有覆核狀態）；`_en` 則**逐列**各自判斷，只要
`IS NULL` 就照填，不管側表有沒有記錄。`seed_rule_options` 另外把 `is_active`
排在查詢的第一位（`ORDER BY is_active DESC`）當第二層保險，讓 active 版一定
先被處理、側表的 `source_text` 稽核記錄以 active 的 `label_zh` 為準。

**I5（同一參數表內英文標籤正規化後必須唯一）在灌值當下就避免碰撞**——不是翻完
再檢查、撞了才補救。已知高風險對（ADR-032 §3 I5／R1）：
  - `g_grasp`（抓握，6 TMU）→ "Grasp" vs `g_touch`（接觸，3 TMU）→ "Touch"
  - `g_pat`（輕拍）→ "Pat" vs `g_tap`（輕按）→ "Tap"
  - `m_tearopen`（撕開）→ "Tear open" vs `m_teartape`（撕除）→ "Peel off (tape)"
    （刻意不用同一個詞根 "tear"，讓語意差異在英文裡也分得出來）
`test_i18n_labels_are_unique_per_table`（unit）與 `test_english_labels_are_unique_
within_each_option_table`（integration，對真實 active rule-set 資料）都守著這件事；
跑完本腳本後**再獨立驗證一次**（見兩個測試），衝突即腳本 bug，不得加後綴矇混。

**灌值範圍（D6）**：active rule-set ＋ 現存 draft 的選項表（`rule_sets.status='draft'
OR rule_sets.is_active`——與 `i18n_service.IN_SCOPE_RULE_SET_SQL` 同一個判準，
避免「灌了什麼」與「待審清單顯示什麼」兩處各自維護一份定義而漂移）；
全部 `work_vocab_items`；全部 `motion_templates`。

**`motion_templates` 既有 16 筆 legacy_seed 不覆寫**：`name_en` 已有值但出處不明
（ADR-032 1.2c——來自 `dev_seed_templates.py` 的開發者手寫欄，非 IE 認證、非翻譯
流程產出），本腳本只補一筆 `source='legacy_seed'` 的側表記錄，`name_en` 原樣保留。

**冪等**：`(entity_type, scope_key, field, locale)` 已有側表列 → 不重覆寫入（不覆寫
既有覆核狀態，無論是 machine／human／legacy_seed——重跑 seed 不得抹掉 IE 已完成的
覆核）；但這**只管側表**，不管 `_en` 欄位本身（見上）。

**S3（2026-08-18 覆審修正）：缺翻譯不再讓整條 seed 中止**。單一 rule-set（尤其是
從非當前基準版本 clone 出來的草稿）出現字典裡沒有的 option code 時，舊行為是
`raise TranslationMissing` 當場中止整支腳本——連早就掃描完、已經填好的 active
版與主數據都因為還沒 `commit()` 而全部付諸東流。現在改為：`_seed_one` 把缺漏
記進 `SeedStats.missing`（不中止），讓其餘資料表／rule-set 繼續掃完；`main()`
無論如何先 `commit()` 已完成的部分，**commit 之後**才用 `raise_if_missing()`
把全部缺漏一次列出並以非 0 結束（仍是 fail-loud，只是不拖累已經成功的部分）。

灌值與側表記錄同一個 SQLAlchemy session、同一個交易（呼叫端於 `main()` 統一
commit），符合 ADR-032 D6「灌值同時寫入 `_en` 欄位本身與 `i18n_review_state`
對應列，兩者原子」。

**B1（2026-08-18 第二輪複審修正；2026-08-18 第四輪已拆除，見下）**：security
review Medium 曾加過一道寫入前逐字比對防線（`i18n_service._authoritative_zh_text`
／`SourceTextStale`），對「active 根本沒有這個 code」一度 fail-closed，撞上 D4
允許 IE 在 draft 新增 active 沒有的選項時會整批炸掉（重演 S1 的失敗模式）。
第二輪複審當時的修法是讓 `_authoritative_zh_text` 有條件放行、`_seed_one` 包一層
`try/except SourceTextStale`。**第四輪（2026-08-18）拆除了整道比對防線**——
三輪複審後發現它是過去每一個阻擋級問題的唯一來源，而它想擋的問題（draft 改過
的中文污染 active 覆核狀態）讀取端的 sha256 過期偵測本來就正確處理了
（見 `i18n_service.upsert_review_state` 檔頭）。拆除後 `upsert_review_state`
不再檢查中文內容、也不再需要 `rule_set_id` 參數，`_seed_one` 因此不再需要
`try/except`——這裡的段落保留是為了交代這段演進，不是描述現行行為。
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ddm_v2.models.v2 import rule_set_tables as rt
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.services.v2 import i18n_service as i18n

# ── 來源識別字串（寫進 i18n_review_state.translated_by，供事後追「這批是誰灌的」）──
MACHINE_TRANSLATED_BY = "dev_seed_i18n_labels.py:engineer-domain-v1"
LEGACY_SEED_TRANSLATED_BY = "legacy:dev_seed_templates.py"
LEGACY_SEED_NOTE = (
    "既有值出處不明（ADR-032 1.2c）：來自 dev_seed_templates.py 的開發者手寫欄，"
    "非 IE 認證、非翻譯流程產出，等同未覆核"
)

# ══════════════════════════════════════════════════════════════════
# 7 張選項表的翻譯表（key＝option code；與 rule_set_id 無關——見 ADR-032 D5
# 「scope_key 刻意不含 rule_set_id」，同一個 code 在不同版本共用同一條翻譯）。
# ══════════════════════════════════════════════════════════════════

B_LABELS: dict[str, str] = {
    "b_bend": "Stand up or bend/sit",
    "b_eye": "Eye action",
    "b_none": "No body motion",
    "b_stand": "Stand",
}

G_LABELS: dict[str, str] = {
    "g_grab": "Grab",
    "g_grasp": "Grasp",
    "g_handchange": "Hand change (transfer)",
    "g_pat": "Pat",
    "g_pick_collect": "Pick up (collect)",
    "g_pick_sel": "Pick up (select)",
    "g_pick_small": "Pick up (select, small)",
    "g_pullout": "Pull out (separate)",
    "g_regrasp": "Regrasp",
    "g_tap": "Tap",
    "g_touch": "Touch",
}

P_BASE_LABELS: dict[str, str] = {
    "p_asm_multi": "Assemble (multi-direction)",
    "p_asm_single": "Assemble (single direction)",
    "p_hold": "Hold in place",
    "p_place_multi": "Place (multi-direction)",
    "p_place_none": "Place (no direction)",
    "p_place_single": "Place (single direction)",
    "p_toss": "Toss",
}

P_ADDON_LABELS: dict[str, str] = {
    "a_align": "Align (precision <4mm)",
    "a_hard": "Difficult to handle",
    "a_insert": "Insert",
    "a_press": "Apply pressure",
    "a_snap": "Snap fit",
}

M_LABELS: dict[str, str] = {
    "m_attach": "Attach",
    "m_btn": "Press button",
    "m_fold": "Fold",
    "m_foot": "Foot step",
    "m_hand": "Hand turn",
    "m_li": "Dress",
    "m_press": "Press",
    "m_pull": "Pull",
    "m_push": "Push",
    "m_remove": "Remove",
    "m_rotate": "Rotate",
    "m_screw": "Screw release",
    "m_tearopen": "Tear open",
    "m_teartape": "Peel off (tape)",
    "m_through": "Thread",
    "m_wipe": "Wipe",
}

X_LABELS: dict[str, str] = {
    "x_blow_clean": "Air-blow clean",
    "x_glue": "Dispense glue",
    "x_heat": "Heat-melt machine",
    "x_laser": "Laser marking",
    "x_none": "No machine wait",
    "x_press": "Press-fit machine",
    "x_scan_bar": "Scan barcode",
    "x_scan_ppid": "Scan PPID",
    "x_scan_wo": "Scan work-order QR code",
    "x_screw_fix": "Screw fastening (per diagram sequence)",
    "x_snap_press": "Snap & press machine",
}

I_LABELS: dict[str, str] = {
    "i_align1": "Align to point (normal vision)",
    "i_align1_out": "Align to point (outside normal vision)",
    "i_align2": "Align to two points (normal vision)",
    "i_align2_out": "Align to two points (outside normal vision)",
    "i_check": "Check (normal vision)",
    "i_check_out": "Check (outside normal vision)",
    "i_confirm": "Confirm (normal vision)",
    "i_confirm_out": "Confirm (outside normal vision)",
    "i_none": "No additional alignment",
}

# (ORM 表, scope_key 參數前綴, 翻譯表)——P 的 base/addon 共用參數字母 'p'，
# code 命名空間不重疊（p_base 一律 `p_` 開頭、p_addon 一律 `a_` 開頭）。
RULE_OPTION_TABLES: tuple[tuple[type, str, dict[str, str]], ...] = (
    (rt.RuleBOption, "b", B_LABELS),
    (rt.RuleGAction, "g", G_LABELS),
    (rt.RulePBase, "p", P_BASE_LABELS),
    (rt.RulePAddon, "p", P_ADDON_LABELS),
    (rt.RuleMVerb, "m", M_LABELS),
    (rt.RuleXOption, "x", X_LABELS),
    (rt.RuleIOption, "i", I_LABELS),
)

# ══════════════════════════════════════════════════════════════════
# 7 張選項表的**句面**翻譯表（`sentence_text_en`，ADR-032 Phase C）。
#
# 與上面的標籤翻譯表刻意不同構——契約見 `most_engine/narrative_en.py` 檔頭：
#   G   ＝裸及物動詞（受詞由樣板自 vocab 填真實名詞）
#   P/M ＝自足動詞片語，含代名詞受詞（第一句已introduce過真實名詞）
#   X   ＝動名詞（樣板補 "while"）；I ＝過去分詞（樣板不補連接詞）
# 空字串＝**刻意不入句**（對齊 `sentence_text_zh` 同樣為空的那幾條：b_none／
# a_hard／a_press／m_hand／m_foot／x_none／i_none）。
#
# 句面**不套用 I5 唯一性**（那是標籤的約束）：中文句面本來就有一詞多用
# （拿取＝g_pick_sel／g_pick_small／g_pick_collect、放＝三個 p_place_*），
# 英文照樣共用；辨義責任在標籤，不在句面。
# ══════════════════════════════════════════════════════════════════

B_SENTENCES: dict[str, str] = {
    "b_bend": "stand up or bend down",
    "b_eye": "eye action",
    "b_none": "",
    "b_stand": "stand",
}

G_SENTENCES: dict[str, str] = {
    "g_grab": "grab",
    "g_grasp": "grasp",
    "g_handchange": "transfer",
    "g_pat": "pat",
    "g_pick_collect": "pick up",
    "g_pick_sel": "pick up",
    "g_pick_small": "pick up",
    "g_pullout": "pull out",
    "g_regrasp": "regrasp",
    "g_tap": "tap",
    "g_touch": "touch",
}

P_BASE_SENTENCES: dict[str, str] = {
    "p_asm_multi": "assemble it",
    "p_asm_single": "assemble it",
    "p_hold": "hold it in place",
    "p_place_multi": "place it",
    "p_place_none": "place it",
    "p_place_single": "place it",
    "p_toss": "toss it",
}

P_ADDON_SENTENCES: dict[str, str] = {
    "a_align": "aligned to within 4 mm",   # prefix_visible_term：英文是後綴（D7.3.2）
    "a_hard": "",
    "a_insert": "insert it",
    "a_press": "",
    "a_snap": "snap it into place",
}

M_SENTENCES: dict[str, str] = {
    "m_attach": "attach it",
    "m_btn": "press the button",
    "m_fold": "fold it",
    "m_foot": "",
    "m_hand": "",
    "m_li": "dress it",
    "m_press": "press it",
    "m_pull": "pull it",
    "m_push": "push it",
    "m_remove": "remove it",
    "m_rotate": "rotate it",
    "m_screw": "slide the screw out",
    "m_tearopen": "tear it open",
    "m_teartape": "peel the tape off",
    "m_through": "thread it through",
    "m_wipe": "wipe it",
}

X_SENTENCES: dict[str, str] = {
    "x_blow_clean": "air-blow cleaning",
    "x_glue": "dispensing glue",
    "x_heat": "heat-melting on the machine",
    "x_laser": "laser-marking",
    "x_none": "",
    "x_press": "press-fitting on the machine",
    "x_scan_bar": "scanning the barcode",
    "x_scan_ppid": "scanning the PPID",
    "x_scan_wo": "scanning the work-order QR code",
    "x_screw_fix": "screw-fastening to secure",
    "x_snap_press": "snap-fitting and press-fitting on the machine",
}

I_SENTENCES: dict[str, str] = {
    "i_align1": "aligned to the point",
    "i_align1_out": "aligned to the point",
    "i_align2": "aligned to two points",
    "i_align2_out": "aligned to two points",
    "i_check": "checked",
    "i_check_out": "checked",
    "i_confirm": "confirmed",
    "i_confirm_out": "confirmed",
    "i_none": "",
}

# 與 RULE_OPTION_TABLES 同序、同表——句面翻譯表逐張對應（`zip` 靠位置配對，
# 兩個 tuple 一旦不同長或改序就會錯配到別張表的翻譯，故在 import 期斷言）。
RULE_OPTION_SENTENCES: tuple[dict[str, str], ...] = (
    B_SENTENCES, G_SENTENCES, P_BASE_SENTENCES, P_ADDON_SENTENCES,
    M_SENTENCES, X_SENTENCES, I_SENTENCES,
)

assert len(RULE_OPTION_SENTENCES) == len(RULE_OPTION_TABLES)
assert all(
    set(sentences) == set(labels)
    for (_model, _param, labels), sentences in zip(RULE_OPTION_TABLES, RULE_OPTION_SENTENCES)
), "句面翻譯表與標籤翻譯表的 code 集合必須逐張相同（否則某些選項只有標籤沒有句面）"

# ══════════════════════════════════════════════════════════════════
# 詞彙庫（work_vocab_items）：key＝name_zh（實測 59 列、53 個相異中文名——
# 同名跨 kind 共用同一條翻譯，如「料架」同時是 from／to）。
# ══════════════════════════════════════════════════════════════════
VOCAB_LABELS: dict[str, str] = {
    "CPU 拉桿": "CPU lever",
    "DIMM": "DIMM",
    "DIMM 內存": "DIMM memory",
    "DIMM 卡扣": "DIMM latch",
    "DIMM卡槽": "DIMM slot",
    "DIMM卡槽的左右卡扣": "DIMM slot left/right latches",
    "DIMM壓合治具": "DIMM press-fit fixture",
    "DIMM壓合治具的底板": "DIMM press-fit fixture base plate",
    "DIMM壓合治具的把手": "DIMM press-fit fixture handle",
    "DIMM材料盒": "DIMM material box",
    "I/O 擋板": "I/O shield",
    "Label": "Label",
    "PSU": "PSU",
    "SATA 排線": "SATA cable",
    "SSD": "SSD",
    "上蓋": "Top cover",
    "主板": "Main board",
    "主板的包装袋": "Main board packaging bag",
    "主機板": "Motherboard",
    "保護膜": "Protective film",
    "假DIMM": "Dummy DIMM",
    "假DIMM的包裝袋": "Dummy DIMM packaging bag",
    "側板": "Side panel",
    "垃圾桶": "Trash bin",
    "外箱": "Outer carton",
    "天線": "Antenna",
    "對應的點位": "Corresponding point",
    "導熱膠": "Thermal paste",
    "工作台": "Workbench",
    "成品": "Finished product",
    "散熱片": "Heat sink",
    "料架": "Rack",
    "條碼": "Barcode",
    "標籤": "Tag",
    "機箱": "Chassis",
    "泡棉": "Foam",
    "流水線": "Assembly line",
    "測試治具": "Test fixture",
    "測試鈕": "Test button",
    "潔淨棚的工作台": "Clean-tent workbench",
    "無塵布": "Cleanroom wipe",
    "电动起子": "Electric screwdriver",
    "線束": "Wire harness",
    "螺絲": "Screw",
    "螺絲x4": "Screw x4",
    "螺絲x6": "Screw x6",
    "螺絲料盒": "Screw material box",
    "規定位置": "Designated position",
    "規定位置處": "Designated location",
    "防靜電袋": "Anti-static bag",
    "顯示卡": "Graphics card",
    "風扇": "Fan",
    "風槍": "Air gun",
}

# 範本庫（motion_templates）：現況全部 16 筆皆已有 name_en（legacy_seed 分支處理，
# 不需要翻譯）。這裡刻意留空——若日後有新範本缺 name_en，腳本會把缺漏記進
# `SeedStats.missing`（見 `_seed_one`），而不是靜默略過。
TEMPLATE_LABELS: dict[str, str] = {}


@dataclass
class SeedStats:
    filled: int = 0
    legacy_seed: int = 0
    skipped: int = 0
    by_entity: dict[str, int] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def bump(self, entity_type: str) -> None:
        self.by_entity[entity_type] = self.by_entity.get(entity_type, 0) + 1


class TranslationMissing(SystemExit):
    """`stats.missing` 有一條以上未處理項——中止腳本（非 0 exit），不得靜默略過
    （否則會留下 `_en IS NULL` 卻沒人知道的欄位，且待審清單會一直顯示
    never_translated 但沒人被通知）。

    `stats.missing` 收一類項目（「這一列需要人工介入」，不是程式錯誤）：
    翻譯表沒有對應的 code。不得靜默吞掉，統一走這裡回報。

    **2026-08-18 第四輪簡化**：先前還有第二類項目（`upsert_review_state` 因
    `SourceTextStale` 拒絕寫入）——那道寫入前比對防線已拆除（見
    `i18n_service.upsert_review_state` 檔頭），`_seed_one` 傳進去的 `scope_key`
    永遠是剛從 DB 查到的既有列，天生就會通過現在唯一保留的「entity 是否存在」
    檢查，不會再撞到任何寫入例外，因此不再需要 `try/except`。

    **S1 覆審修正（2026-08-18）之前**：`_seed_one` 一撞到缺漏就直接 `raise` 這個
    例外，讓整支腳本（含早就掃描完、已經填好的 active 版）在 `main()` 的
    `commit()` 之前就中止，active 也一起沒灌進去。**現在**：`_seed_one` 只把缺漏
    記進 `SeedStats.missing`，不中止；`main()` 先 `commit()` 已完成的部分，
    commit 之後才呼叫 `raise_if_missing()` 把全部缺漏一次列出、非 0 結束。
    """


def raise_if_missing(stats: SeedStats) -> None:
    """`stats.missing` 非空 → 一次列出全部未處理項並中止（fail-loud，不是吞錯）。

    刻意設計成獨立函式（不是內嵌在 `main()` 裡）：方便不碰真實 DB 就能單元測試
    「缺漏會不會被正確報出來」，不需要為了測這件事另外跑一次真的 seed。
    """
    if not stats.missing:
        return
    lines = "\n".join(f"  - {m}" for m in stats.missing)
    raise TranslationMissing(
        f"{len(stats.missing)} 條需要人工處理（已完成的部分已經 commit，這裡只是回報）：\n"
        f"{lines}\n"
        "請先在 scripts/dev_seed_i18n_labels.py 補上對應的英文譯名，再重跑"
        "（不得略過：略過會留下 `_en IS NULL` 但沒人知道要補）"
    )


async def _seed_one(
    session: AsyncSession,
    stats: SeedStats,
    *,
    entity_type: str,
    scope_key: str,
    field_name: str,
    source_zh: str,
    current_en: str | None,
    translations: dict[str, str],
    translation_key: str,
    context: str,
) -> str | None:
    """回傳這一列 `_en` 應該被填成的新值（`None` ＝這一列不需要改動 `_en`）。

    **側表寫入**與**`_en` 欄位填值**是兩個分開的判斷（S1 覆審修正——見檔頭）：

    1. 側表（`i18n_review_state`）：`(entity_type, scope_key, field)` 已有列
       → 不重覆寫入（尊重既有覆核狀態，無論是 machine／human／legacy_seed）；
       沒有列 → 依分支建立一筆（machine 或 legacy_seed）。**只建一次**，
       不因為同一個 scope_key 在多個 rule-set 版本各出現一次而重覆寫入。
    2. `_en` 欄位：**逐列**判斷，`current_en is not None` 就不動（已有值，
       無論是這次 clone 帶過來的還是舊資料）；`current_en is None` 就照翻譯表
       填值——**不看側表是否已有列**，因為側表的存在與否是「這個業務鍵翻過了
       嗎」，跟「這一列（這個 rule-set 版本）的欄位有沒有值」是兩件事。

    **不再需要 `rule_set_id` 與 `try/except`（2026-08-18 第四輪簡化）**：
    `i18n_service.upsert_review_state` 已拆除寫入前的中文內容比對防線，只保留
    「entity 是否存在」這一個 fail-closed 檢查（見該函式檔頭）。這裡傳入的
    `scope_key` 永遠是呼叫端剛從 DB 查到的既有列（`seed_rule_options`／
    `seed_vocab`／`seed_motion_templates` 三個呼叫點皆然），天生就會通過這個
    檢查，因此不會再拋出寫入例外，不需要 `try/except` 收斂進 `stats.missing`。
    """
    existing = await i18n.get_review_state(session, entity_type, scope_key, field_name)

    if current_en is not None:
        if existing is not None:
            # 側表已有記錄、這一列的 `_en` 也已有值——兩件事都不用做。
            stats.skipped += 1
            return None
        # `_en` 已有值但尚無側表列（legacy_seed 情境，例如 motion_templates
        # 既有 16 筆）：只登記一筆側表記錄，`_en` 原樣保留、不改動。
        await i18n.upsert_review_state(
            session, entity_type=entity_type, scope_key=scope_key, field=field_name,
            source="legacy_seed", source_text=source_zh, translated_by=LEGACY_SEED_TRANSLATED_BY,
            note=LEGACY_SEED_NOTE,
        )
        stats.legacy_seed += 1
        stats.bump(entity_type)
        return None

    # current_en IS NULL：這一列需要被填值，**不管側表有沒有列**——
    # 側表可能已經因為另一個 rule-set 版本的同一個 scope_key 而存在。
    if translation_key not in translations:
        stats.missing.append(f"{context}（中文來源 {source_zh!r}）不在翻譯表中")
        return None
    translation = translations[translation_key]
    if existing is None:
        await i18n.upsert_review_state(
            session, entity_type=entity_type, scope_key=scope_key, field=field_name,
            source="machine", source_text=source_zh, translated_by=MACHINE_TRANSLATED_BY,
        )
    # 側表寫不寫都算「填值」——`filled` 記的是 `_en` 欄位本身變動的列數，不是側表
    # 寫入次數（側表已有列時，這一列仍然被填值，只是不重覆寫側表，見上方分支）。
    stats.filled += 1
    stats.bump(entity_type)
    return translation


async def seed_rule_options(session: AsyncSession, stats: SeedStats) -> None:
    """D6 範圍：`status='draft' OR is_active`（與 `i18n_service.IN_SCOPE_RULE_SET_SQL`
    同一個判準）。

    **`ORDER BY is_active DESC`（S1 覆審修正的第二層保險）**：active 版一定先被
    處理——這樣側表第一次為某個 scope_key 建立記錄時，`source_text` 一定是
    active（認證）版的 `label_zh`，不會因為掃描順序把 draft 的內容當成稽核基準。
    **不是**寫入層防線（第四輪簡化已拆除 `upsert_review_state` 的內容比對，見
    `i18n_service.py` 檔頭）——「draft 覆核污染 active」現在完全由讀取端
    （`_classify` 的 sha256 過期偵測）擋，這裡只影響側表第一次建立時記錄的是
    哪個版本的中文，純粹是資料品質的第二層保險，不是安全邊界。
    """
    rule_sets = (
        await session.execute(
            select(RuleSet)
            .where((RuleSet.status == "draft") | (RuleSet.is_active.is_(True)))
            .order_by(RuleSet.is_active.desc())
        )
    ).scalars().all()
    for rs in rule_sets:
        for (model, param, labels), sentences in zip(RULE_OPTION_TABLES, RULE_OPTION_SENTENCES):
            rows = (
                await session.execute(select(model).where(model.rule_set_id == rs.id))
            ).scalars().all()
            for row in rows:
                scope_key = f"{param}:{row.code}"
                context = f"{rs.code}/{model.__tablename__}/{row.code}"
                new_en = await _seed_one(
                    session, stats,
                    entity_type="rule_option", scope_key=scope_key, field_name="label",
                    source_zh=row.label_zh, current_en=row.label_en,
                    translations=labels, translation_key=row.code,
                    context=context,
                )
                if new_en is not None:
                    row.label_en = new_en
                # 句面（Phase C）：來源中文取引擎實際會用的那一個——`_sent()` 的回退
                # 鏈是 `sentence_text_zh or label_zh`，過期偵測的基準必須跟著它走，
                # 否則句面空白的那幾條會拿一個引擎根本沒讀的字串去算 sha256。
                new_sent_en = await _seed_one(
                    session, stats,
                    entity_type="rule_option", scope_key=scope_key, field_name="sentence",
                    source_zh=row.sentence_text_zh or row.label_zh,
                    current_en=row.sentence_text_en,
                    translations=sentences, translation_key=row.code,
                    context=f"{context}(sentence)",
                )
                if new_sent_en is not None:
                    row.sentence_text_en = new_sent_en


async def seed_vocab(session: AsyncSession, stats: SeedStats) -> None:
    """D6 範圍：全部 `work_vocab_items`（主數據不分版本）。"""
    rows = (await session.execute(select(WorkVocabItem))).scalars().all()
    for row in rows:
        new_en = await _seed_one(
            session, stats,
            entity_type="vocab_item", scope_key=str(row.id), field_name="name",
            source_zh=row.name_zh, current_en=row.name_en,
            translations=VOCAB_LABELS, translation_key=row.name_zh,
            context=f"work_vocab_items/{row.kind}/{row.name_zh}",
        )
        if new_en is not None:
            row.name_en = new_en


async def seed_motion_templates(session: AsyncSession, stats: SeedStats) -> None:
    """D6 範圍：全部 `motion_templates`（既有 16 筆 legacy_seed 分支處理，不覆寫）。"""
    rows = (await session.execute(select(MotionTemplate))).scalars().all()
    for row in rows:
        new_en = await _seed_one(
            session, stats,
            entity_type="motion_template", scope_key=str(row.id), field_name="name",
            source_zh=row.name_zh, current_en=row.name_en,
            translations=TEMPLATE_LABELS, translation_key=row.name_zh,
            context=f"motion_templates/{row.name_zh}",
        )
        if new_en is not None:
            row.name_en = new_en


async def seed_i18n_labels(session: AsyncSession) -> SeedStats:
    """跑完整套灌值；**不 commit**（呼叫端決定：`main()` 給真 DB 一次性 commit，
    測試給隔離 session，交給 conftest 的 savepoint 隔離收尾）。

    **本函式永不 raise**（S1／S3 覆審修正）：缺翻譯的項目只會記進
    `SeedStats.missing`，讓其餘表／rule-set 版本照常掃完、照常填值。
    呼叫端若要 fail-loud，在拿到 `stats` 之後自行呼叫 `raise_if_missing(stats)`
    ——`main()` 就是這樣做的：commit 已完成的部分**之後**才檢查缺漏並中止。
    """
    stats = SeedStats()
    await seed_rule_options(session, stats)
    await seed_vocab(session, stats)
    await seed_motion_templates(session, stats)
    await session.flush()
    return stats


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await seed_i18n_labels(s)
        await s.commit()  # 已完成的部分（active／主數據／已翻譯的 draft 列）先落盤，
        # 不因為某個 draft 有一兩個缺翻譯的 option code 就整批不見（S3）。
    await engine.dispose()
    print(
        f"✓ i18n 標籤灌值：machine 新增 {stats.filled} 筆、legacy_seed 登記 {stats.legacy_seed} 筆、"
        f"略過(已有側表列) {stats.skipped} 筆"
    )
    print(f"  依 entity_type：{stats.by_entity}")
    if stats.missing:
        print(f"✗ 缺 {len(stats.missing)} 條翻譯（上面已完成的部分已經 commit）：")
        for m in stats.missing:
            print(f"  - {m}")
    raise_if_missing(stats)  # 缺漏一律非 0 結束；上面的 commit 已經先發生過了。


if __name__ == "__main__":
    asyncio.run(main())
