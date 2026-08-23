"""對外列舉的**相容性下界**（ADR-011：契約優先穩定、schema 只准加法）。

⚠️ **這份表只准長、不准縮。** 每個集合都是「已經有人依賴的值」——DB 裡既存的
`ai_parse_runs.plan` / `routing_status` / `routing_reasons`、前端依 key 顯示的文案表、
`i18n_review_state` / `vocab_items` / `wi_contexts` 的既存列。刪掉或改名任何一個成員都是
**破壞性變更**：ADR-011 政策 2 要求走「加新欄 → 雙寫過渡 → 廢舊欄」三步，不是就地改。

**只有 accepted ADR 的裁決能編輯這份表。** 動它之前先回答：那個值在 DB 裡還有沒有列？
前端有沒有依它顯示文案？舊的 plan JSON 還讀不讀得回來？

為什麼需要這份表（實測，2026-08-23）：把 `nlp/contracts.py` 的 `RoleStatus` 拿掉
`"default"`，`pytest tests/unit` **1385 passed 全綠**。當時唯一會紅的是拿掉
`"explicit_unresolved"`——而那是**偶然**：只因為今天剛好有 production code 會產出它，
不是因為存在任何相容性守衛。哪天沒有 producer 了，它就跟 `default` 一樣無聲。

為什麼下界**不能**由 `get_args()` 自己提供：`test_prompt_few_shots` 曾拿
`get_args(DependencyType)` 當「合法集合」的唯一來源。enum 一收窄，那條守衛的判準也跟著
收窄——它不但擋不住收窄，還會**替收窄背書**。下界必須寫死在契約之外。

## ⚠️ 涵蓋範圍（v1）——本表**不是**「全 repo 對外列舉」的清單

只涵蓋 **wi-plan-v1**（`nlp/contracts.py` ＋ `nlp/routing.py`）與 **i18n／vocab／wi_context
三支 schema**。其餘對外列舉**尚未凍結**（票 G-3，待裁決）：

- 模組級別名：`locale.Locale`、`llm_client.ResponseFormatMode`、
  `level_validation_service.Trigger`、`parse_job_service.OutcomeBucket`（全樹 15 個，本表 11 個）。
- 欄位層 inline Literal：`schemas/v2` 底下另有 13 欄零守衛，含 `most.py::CycleIn.seq`、
  `motion_module.py::*.{category,scope}`、`rule_set_options.py` 五欄。

也就是說：**沒有列在這份表裡的對外列舉，收窄時不會有任何東西紅。**
`FROZEN_ALIAS_SCAN_MODULES` 的涵蓋率掃描只掃列出的那幾個模組，新模組不會自動被發現。
"""
from __future__ import annotations

# ── wi-plan-v1（nlp/contracts.py）─────────────────────────────────────
# 這五個別名是 `ai_parse_runs.plan` / `slot_candidates` / `routing_status` 的值域，
# 既存列直接帶著這些字串；收窄＝舊列反序列化失敗（ADR-033 D3／D5 明文保留這兩個
# 「已無產生者」的列舉，理由就是相容性）。

FROZEN_ACTION_TYPE = frozenset({
    "acquire",
    "move_place",
    "controlled_move",
    "process",
    "inspect",
    "release_return",
    "composite_unknown",
})

FROZEN_ROLE_STATUS = frozenset({
    "explicit",
    "inferred",
    "default",              # ADR-033 D3 後無產生者，**仍不得刪**（既存 plan 帶著它）
    "explicit_unresolved",
    "missing",
})

FROZEN_DEPENDENCY_TYPE = frozenset({
    "uses_tool",
    "tool_held_for",
    "same_object",
    "precedes",             # ADR-033 D5：零消費者、不再索取，型別保留
})

FROZEN_CANDIDATE_SOURCE = frozenset({
    "template",
    "synonym_exact",
    "synonym_longest",
    "trgm",
    "embedding",
    "llm_rerank",
    "default",
})

FROZEN_ROUTING_STATUS = frozenset({"auto", "review", "abstain", "invalid"})

# 巢在模型欄位裡的 inline Literal（沒有模組級別名，但一樣落進 plan JSON）
FROZEN_SOURCE_REF_KIND = frozenset({"interactive", "import_row"})
FROZEN_LANGUAGE = frozenset({"zh", "en", "mixed"})

# ── schemas/v2 的對外列舉 ────────────────────────────────────────────
# 這些值同樣**落 DB 並回 API**：`wi_contexts.source`、`vocab_items.kind`、
# `i18n_review_state.{entity_type,field,source}`。i18n 三欄另有 DB CHECK 約束，
# 但 CHECK 只約束**寫入**——Literal 收窄會讓既存列在讀取端就炸掉，兩者守的不是同一件事。

FROZEN_WI_CONTEXT_SOURCE = frozenset({"manual", "imported", "ai_assisted", "system"})
FROZEN_VOCAB_KIND = frozenset({"object", "component", "tool", "from", "to", "hand"})
FROZEN_I18N_ENTITY_TYPE = frozenset({"rule_option", "vocab_item", "motion_template"})
FROZEN_I18N_FIELD_NAME = frozenset({"label", "sentence", "name"})
FROZEN_I18N_PENDING_STATUS = frozenset({"never_translated", "unreviewed", "stale"})
FROZEN_I18N_REVIEW_SOURCE = frozenset({"machine", "human", "legacy_seed", "untranslated"})

# ── 模組級 Literal 別名的凍結表 ──────────────────────────────────────
# key = "<module>.<name>"；`test_contract_enum_freeze` 會 AST 掃描這些模組，
# 掃到卻不在表裡的別名一律紅——新別名不得靜默逃過凍結。

FROZEN_ALIAS_MEMBERS: dict[str, frozenset[str]] = {
    "ddm_v2.nlp.contracts.ActionType": FROZEN_ACTION_TYPE,
    "ddm_v2.nlp.contracts.RoleStatus": FROZEN_ROLE_STATUS,
    "ddm_v2.nlp.contracts.DependencyType": FROZEN_DEPENDENCY_TYPE,
    "ddm_v2.nlp.contracts.CandidateSource": FROZEN_CANDIDATE_SOURCE,
    "ddm_v2.nlp.contracts.RoutingStatus": FROZEN_ROUTING_STATUS,
    "ddm_v2.schemas.v2.wi_context.SourceLiteral": FROZEN_WI_CONTEXT_SOURCE,
    "ddm_v2.schemas.v2.vocab.VocabKind": FROZEN_VOCAB_KIND,
    "ddm_v2.schemas.v2.i18n.EntityType": FROZEN_I18N_ENTITY_TYPE,
    "ddm_v2.schemas.v2.i18n.FieldName": FROZEN_I18N_FIELD_NAME,
    "ddm_v2.schemas.v2.i18n.PendingStatus": FROZEN_I18N_PENDING_STATUS,
    "ddm_v2.schemas.v2.i18n.ReviewSource": FROZEN_I18N_REVIEW_SOURCE,
}

# AST 掃描涵蓋的模組（掃「這個檔裡定義的」模組級 Literal 別名，不含 import 進來的）
FROZEN_ALIAS_SCAN_MODULES = (
    "ddm_v2.nlp.contracts",
    "ddm_v2.schemas.v2.wi_context",
    "ddm_v2.schemas.v2.vocab",
    "ddm_v2.schemas.v2.i18n",
)

# ── wi-plan-v1 模型欄位的 Literal 凍結表 ─────────────────────────────
# key = "<Model>.<field>"。別名型欄位共用同一個 frozenset（下界同一份，不抄第二份）；
# inline Literal（`SourceRef.kind`／`*.language`）沒有別名，只有這裡守得到。
# `test_contract_enum_freeze` 會反射 `nlp/contracts.py` 內所有 BaseModel，
# 帶 Literal 的欄位**必須**在這張表裡。

FROZEN_FIELD_MEMBERS: dict[str, frozenset[str]] = {
    "RoleValue.status": FROZEN_ROLE_STATUS,
    "PlannedAction.action_type": FROZEN_ACTION_TYPE,
    "ActionDependency.type": FROZEN_DEPENDENCY_TYPE,
    "SourceRef.kind": FROZEN_SOURCE_REF_KIND,
    "WorkInstructionPlan.language": FROZEN_LANGUAGE,
    "OptionCandidate.source": FROZEN_CANDIDATE_SOURCE,
    "ParseRunResult.routing_status": FROZEN_ROUTING_STATUS,
    "PlannerOutput.language": FROZEN_LANGUAGE,
}

# ── 非 Literal，但同屬「對外列舉」的封閉集合 ─────────────────────────

# `validate_planner_output` / `sanitize_planner_output` 的合法角色鍵。收窄＝既存 plan 的
# 角色被當成「自創鍵」丟棄（`role_key_dropped`），而且會靜默：丟棄是**降級不是失敗**。
FROZEN_ROLE_KEYS = frozenset({
    "hand",
    "object",
    "tool",
    "tool_ref",
    "from_location",
    "destination",
    "return_to",            # ADR-033 D2（P1 加入，P2 才有產生者）
    "distance",
    "quantity",
    "process_kind",
    "inspect_kind",
})

# `routing_reasons` 的 key 的**宣告集合**。
#
# ⚠️ 措辭要準，這一項與上面幾張表**不同**：它**不是**反序列化閘門。`ai_parse_runs.
# routing_reasons` 是 JSONB 的 `list[str]`，沒有任何地方拿這個 frozenset 驗過它
# （S-5：`compute_routing` 對它零引用，宣告了卻不執行）。所以收窄它**不會**讓既存列
# 讀不回來——會壞的是**前端依 key 顯示中文文案**那條路：少一個 key，覆核者看到的是
# 一個沒有文案的裸代碼。
#
# 那為什麼還要凍結？因為它是「有執行語意的集合」的宣告面：`_eligible_auto` 的
# `blocked` 才是真正擋 auto 的封閉集合，兩者由
# `test_eligible_auto_blocked_reasons_are_all_declared` 單向釘死。宣告面一縮，那條
# 守衛的判準也跟著縮（與 `get_args()` 當下界是同一個病）。
# S-5 的治本方案是把它變成真正的過濾器，屆時值域變動必須是**有裁決的**變動。
FROZEN_ROUTING_REASONS = frozenset({
    "engines_disagree",
    "baseline_disagreement",
    "quantity_policy_review",
    "distance_unevidenced_review",
    "quantity_unevidenced_review",
    "non_finite_value_rejected",
    "template_hint",           # 2026-08-24 補宣告：先前只在 `blocked` 有執行語意
    "planner_invented_action",
    "tool_state_violation",
    "role_key_dropped",
    "role_numeric_stripped",
    "role_text_not_in_source",
    "dependency_dropped",
    "fallback_rule_based",
    "composite_unknown",
    "next_operation",
    "i_range_assumed",
    "m_zero_pure_inspection_assumed",
})

# ── 這份表自己的規模（防「把表掏空 → 守衛恆綠」）──────────────────
#
# 表被掏空時 `基準 ⊆ 實際` 對空集合恆真，凍結會**無聲失效**；更糟的是被
# `@pytest.mark.parametrize` 消費的那幾張表一空，測試不是變紅而是**整批 skipped**
# ——不存在的測試不會紅（實測：掏空 `FROZEN_ALIAS_MEMBERS` → 5 failed ＋ 3 skipped）。
#
# ⚠️ 判準是 **`==` 不是 `>=`**。用 `>=` 的話，表合法長大（ADR 裁決新增成員）之後
# 沒有東西要求同步調高數字，防掏空的強度會逐年衰減：表長到 60 個成員而常數還是 50 時，
# 一次刪掉 10 個仍然全綠。**動這張表就要改這裡的數字**，這是刻意的摩擦。
#
# 所以名字是 `EXPECTED_` 不是 `MIN_`：叫 `MIN_` 卻寫 `== ` 會讓下一個人以為是 bug，
# 「順手改回 `>=`」把剛修掉的鬆弛病放回來，而且他會覺得自己在修 bug。**名字勝過註解。**
# （`test_contract_enum_freeze._MIN_BLOCKED_REASONS` 保留 `MIN_`：它守的是產品碼、
#   判準真的是 `>=`，兩者刻意不同名。）
#
# ⚠️ 有兩個 frozenset 被**共用**，加一個成員會**同時**打破兩個數字：
#   `FROZEN_ROLE_STATUS` → 別名表 ＋ 欄位表（`RoleValue.status`）
#   `FROZEN_LANGUAGE`   → `WorkInstructionPlan.language` ＋ `PlannerOutput.language`
EXPECTED_FROZEN_ALIASES = 11
EXPECTED_FROZEN_ALIAS_MEMBERS = 50
EXPECTED_FROZEN_FIELDS = 8
EXPECTED_FROZEN_FIELD_MEMBERS = 35
EXPECTED_FROZEN_ROLE_KEYS = 11
EXPECTED_FROZEN_ROUTING_REASONS = 18
# `FROZEN_ALIAS_SCAN_MODULES` 是**唯一一張被 parametrize 直接消費、卻曾經沒有下界**
# 的清單：清空它，那 4 個模組的涵蓋率檢查（含它 body 裡的 `stale` 反向檢查）會一起
# 變成 skipped 而不是 failed，而且沒有別的斷言蓋得住它。
EXPECTED_FROZEN_SCAN_MODULES = 4

ADR_011 = (
    "ADR-011 政策 1／2：對外契約只准以加法演進；刪成員或改名是破壞性變更，"
    "必須走「加新 → 雙寫過渡 → 廢舊」三步並留 ADR 裁決，不得就地收窄。"
    "下界表：tests/unit/_contract_freeze_v1.py"
)
