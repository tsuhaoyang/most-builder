"""dev seed：NL 同義詞詞典（`rule_option_synonyms`）——IE 已裁決的 22 條登記。idempotent。

執行：
  DATABASE_URL=... PYTHONPATH=src .venv/bin/python scripts/dev_seed_synonyms.py

**為什麼要有這支腳本**（D3-030 複審 B1）：
`tests/integration/test_synonym_registration_governance.py` 的守門對象是 **DB 現存
資料**，而 CI 的 seed 鏈（`alembic upgrade head` → `dev_seed_v2.py` →
`dev_seed_templates.py`）**沒有任何一步寫入 `rule_option_synonyms`**——乾淨 DB 上
主守門的 `assert rows` 必紅（複審在拋棄式 DB 實測：3 failed）。詞典先前只存在於
開發機的執行期資料裡，等於守門在 CI 上從未真的守過。本腳本把「已被 IE 裁決過」
的 22 條登記帶進版控，seed 鏈跑完即有詞典。

**值的來源＝各批 worklog 的 IE 裁決紀錄**（`docs/llm/wi-ai-parser-worklog.md`
D3-016／D3-017／D3-019／D3-021），逐條標註輪次與 IE 答案；不是工程端補的相似詞。
新增一條的合法來源只有 ADR-023 §3.3 規則 1 補節二的兩條：(a) 該詞出現在對應選項
自己的標籤／句面文字裡，或 (b) 有明確 IE 裁決——**工程端不得以相似性自行判定**
（D3-028 Q4 已否決「下壓≈按壓」「按下≈按動按鈕」）。

**登記走 `synonym_service.create_synonym`**（與 API `POST /api/v2/rule-sets/{code}/
synonyms` 同一條路）：option_code 應用層 FK 驗證、retired 終態守門、同面撞 priority
守門（D3-018 H1）都由它負責——seed 不另開平行寫入路徑。

**範圍**：本腳本只負責**版控的詞典**（下表這 22 條）。IE 在執行期走 API 登記的
同義詞不在此列，本腳本也不刪不覆蓋（同 ADR-023 補節二的範圍聲明）。
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.synonym import RuleOptionSynonym
from ddm_v2.nlp.normalization import normalize
from ddm_v2.services.v2 import synonym_service

# 詞典掛在 V2（＝v3 IE 認證字典，ADR-014 值權威；dev_seed_v2.py 建立並 activate）
RULE_SET_CODE = "MINIMOST_FACTORY_V2"
# 登記人沿用原登記紀錄的工號（各批 worklog 皆記 IEC141289）
REGISTERED_BY = "IEC141289"

# (parameter, option_code, synonym_raw, priority, ruling)
#   priority＝偏好位次（**數字小者優先，0＝預設**；同一詞面掛多個 code 時必須以
#   不同 priority 顯式宣告偏好序，見 D3-018 H1）。
#   ruling＝該條登記的 IE 裁決出處（輪次 D3-NNN ＋ 答案內容）。
SYNONYMS: list[tuple[str, str, str, int, str]] = [
    # ── D3-016（2026-08-16）：IE 第二輪核可「10 個同字直配動詞」＝11 條映射 ──
    #     同字直配＝詞面就是字典選項自己的標籤／句面（含帶方向補語的複合詞
    #     「推至／拉至／丟至」，標籤是單字動詞「推／拉／丟」）。
    ("G", "g_grasp", "抓握", 0, "D3-016 IE 第二輪：同字直配核可（標籤『抓握』）"),
    ("G", "g_touch", "接觸", 0, "D3-016 IE 第二輪：同字直配核可（標籤『接觸』）"),
    ("M", "m_press", "按壓", 0, "D3-016 IE 第二輪：同字直配核可（標籤『按壓』）"),
    ("M", "m_remove", "去除", 0, "D3-016 IE 第二輪：同字直配核可（標籤『去除』）"),
    ("M", "m_pull", "拉至", 0, "D3-016 IE 第二輪：同字直配核可（標籤『拉』⊆『拉至』）"),
    ("M", "m_push", "推至", 0, "D3-016 IE 第二輪：同字直配核可（標籤『推』⊆『推至』）"),
    ("M", "m_btn", "按動按鈕", 0, "D3-016 IE 第二輪：同字直配核可（標籤『按動按鈕』）"),
    ("M", "m_attach", "貼附", 0, "D3-016 IE 第二輪：同字直配核可（標籤『貼附』）"),
    ("M", "m_teartape", "撕除", 0, "D3-016 IE 第二輪：同字直配核可（標籤『撕除』）"),
    ("P", "p_hold", "保持住", 0, "D3-016 IE 第二輪：同字直配核可（標籤『保持住』）"),
    ("P", "p_toss", "丟至", 0, "D3-016 IE 第二輪：同字直配核可（標籤『丟』⊆『丟至』）"),
    # ── D3-017（2026-08-16）：IE 第三輪裁決——「放至／放置」按賓語情境分兩變體 ──
    #     放入機構件（治具／卡槽／機箱等要定位者）→ 必對準＝`p_place_single`（預設，
    #     priority 0）；放上盤面類（流水線／工作台／垃圾桶等）→ 無方向＝
    #     `p_place_none`（priority 1）。一面兩 code 必須以不同 priority 宣告偏好序，
    #     否則 parser tie-break 會靜默擇一（D3-018 H1，service 層 409 擋）。
    ("P", "p_place_single", "放至", 0, "D3-017 IE 第三輪：機構件情境＝必對準（預設變體）"),
    ("P", "p_place_single", "放置", 0, "D3-017 IE 第三輪：機構件情境＝必對準（預設變體）"),
    ("P", "p_place_none", "放至", 1, "D3-017 IE 第三輪：盤面情境＝無方向（次選變體）"),
    ("P", "p_place_none", "放置", 1, "D3-017 IE 第三輪：盤面情境＝無方向（次選變體）"),
    # ── D3-019（2026-08-17）：IE 第三輪答案①「拿取」→ 預設「選取」──
    #     **恰一條**：small／collect 兩個變體 IE 只答預設、未授權都掛，維持候選。
    ("G", "g_pick_sel", "拿取", 0, "D3-019 IE 答①：『拿取』預設『選取』，變體未授權"),
    # ── D3-021（2026-08-17）：IE 第四輪答案（6 條）──
    ("I", "i_confirm", "確認", 0, "D3-021 IE 答①：『確認』＝範圍內 i_confirm"),
    (
        "X",
        "x_screw_fix",
        "鎖附",
        0,
        "D3-021 IE 答②：『鎖附』＝X 製程 x_screw_fix（電動起子情境；"
        "D3-024 IE 再確認產線無手動鎖附 ⇒ 一律當電動、無條件）",
    ),
    ("P", "p_asm_single", "組至", 0, "D3-021 IE 答③：『組至』照放置邏輯掛 p_asm_single"),
    ("P", "p_asm_single", "組於", 0, "D3-021 IE 答③：『組於』照放置邏輯掛 p_asm_single"),
    (
        "X",
        "x_blow_clean",
        "清潔",
        0,
        "D3-021 IE 答④：『清潔』＝x_blow_clean **僅吹風情境**——DB 映射是全域的、"
        "裁決是情境的，情境守門在 harvest 端（x_clean_context_unverified）",
    ),
    (
        "P",
        "p_asm_single",
        "插入",
        0,
        "D3-021 IE 答⑤：『插入』＝多費力，P 主項 p_asm_single ＋ addon a_insert 兩段"
        "都計時。**唯一非標籤衍生的登記**（『插入』不在 p_asm_single 的標籤『組"
        "(一種方向)』／句面『組』裡），守門走 IE_RULING_ALLOWLIST 的 (b) 例外",
    ),
]


async def seed_synonyms(session: AsyncSession) -> tuple[int, int]:
    """把 SYNONYMS 寫進 DB；回傳 (新增, 略過)。

    **冪等**：以 UNIQUE 鍵 `(rule_set_id, parameter, synonym_norm, option_code)`
    先查證，已存在就跳過（不覆寫既有列的 priority／created_by／created_at——
    重跑 seed 不得改寫 IE 的登記紀錄）。

    session 由呼叫端提供（`main()` 給真 DB，測試給隔離 session）——腳本內不
    自建 engine，整合測試才不會繞過 conftest 的 savepoint 隔離。
    """
    rs = (
        await session.execute(select(RuleSet).where(RuleSet.code == RULE_SET_CODE))
    ).scalar_one_or_none()
    if rs is None:
        raise SystemExit(
            f"找不到 rule_set {RULE_SET_CODE}——請先跑 scripts/dev_seed_v2.py"
        )
    rs_id = rs.id

    added = skipped = 0
    for parameter, option_code, synonym_raw, priority, _ruling in SYNONYMS:
        synonym_norm = normalize(synonym_raw)
        exists = (
            await session.execute(
                select(RuleOptionSynonym).where(
                    RuleOptionSynonym.rule_set_id == rs_id,
                    RuleOptionSynonym.parameter == parameter,
                    RuleOptionSynonym.synonym_norm == synonym_norm,
                    RuleOptionSynonym.option_code == option_code,
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            skipped += 1
            continue
        # 走與 API 同一條服務路徑（FK／retired／priority 撞面守門都在裡面）
        await synonym_service.create_synonym(
            session,
            RULE_SET_CODE,
            {
                "parameter": parameter,
                "option_code": option_code,
                "synonym_raw": synonym_raw,
                "priority": priority,
            },
            created_by=REGISTERED_BY,
        )
        added += 1
    return added, skipped


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        added, skipped = await seed_synonyms(s)
        total = (
            await s.execute(
                select(RuleOptionSynonym)
                .join(RuleSet, RuleSet.id == RuleOptionSynonym.rule_set_id)
                .where(RuleSet.code == RULE_SET_CODE)
            )
        ).scalars().all()
    await engine.dispose()
    print(
        f"✓ 同義詞詞典：新增 {added} 筆、已存在略過 {skipped} 筆"
        f"（版控定義 {len(SYNONYMS)} 筆；{RULE_SET_CODE} 現有 {len(total)} 筆）"
    )
    if len(total) != len(SYNONYMS):
        # 不是錯誤：執行期由 IE 走 API 登記的條目不在版控詞典裡（範圍聲明見檔頭）。
        print(
            f"  註：DB 筆數與版控定義不同（{len(total)} vs {len(SYNONYMS)}）"
            "——差額＝執行期經 API 登記的同義詞，本腳本不動它們。"
        )


if __name__ == "__main__":
    asyncio.run(main())
