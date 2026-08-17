"""SlotLinker unit tests（池隔離／低分回空／disagree）。"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.contracts import (
    EvidenceSpan,
    OptionCandidate,
    PlannedAction,
    RoleValue,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.linking import SlotLinker, _merge_l1_l2


def _plan(action_type: str, text: str, roles: dict | None = None) -> WorkInstructionPlan:
    return WorkInstructionPlan(
        source_text=text,
        normalized_text=text,
        source_ref=SourceRef(kind="interactive"),
        actions=[
            PlannedAction(
                action_id="a1",
                action_type=action_type,  # type: ignore[arg-type]
                sequence_order=1,
                roles=roles or {},
                evidence=[EvidenceSpan(start=0, end=len(text), text=text)],
            )
        ],
    )


@pytest.mark.asyncio
async def test_g_pool_does_not_return_x_candidates():
    syn = [
        {"parameter": "G", "option_code": "g_grasp", "synonym_norm": "拿取", "priority": 1},
        {"parameter": "X", "option_code": "x_screw_fix", "synonym_norm": "鎖附", "priority": 1},
    ]
    linker = SlotLinker(syn)
    plan = _plan("acquire", "拿取螺絲", {"object": RoleValue(text="螺絲", status="explicit")})
    sets = await linker.link(plan)
    g = [s for s in sets if s.parameter == "G"]
    assert g and g[0].chosen and g[0].chosen.option_code == "g_grasp"
    assert all(c.parameter == "G" for s in g for c in s.top_k)


@pytest.mark.asyncio
async def test_no_candidate_when_below_threshold():
    linker = SlotLinker([])
    plan = _plan("acquire", "神秘動詞物件")
    sets = await linker.link(plan)
    assert sets
    assert sets[0].chosen is None
    assert sets[0].review_reason == "no_candidate"


@pytest.mark.asyncio
async def test_l0_template_hint_needs_review():
    plan = _plan("acquire", "雙手抓握主板放到DIMM壓合治具")
    templates = [
        {
            "id": "tmpl-1",
            "keywords": ["治具", "DIMM"],
            "cycle_template": {"seq": "GM", "g2": {"g_code": "g_grasp"}},
        }
    ]
    linker = SlotLinker([])
    sets = await linker.link(plan, templates=templates)
    tmpl = [s for s in sets if s.parameter == "TEMPLATE"]
    assert tmpl and tmpl[0].chosen and tmpl[0].chosen.option_code == "tmpl-1"
    assert tmpl[0].needs_review is True
    assert tmpl[0].review_reason == "template_hint"


def test_engines_disagree_marks_reason():
    l1 = [
        OptionCandidate(parameter="G", option_code="g_grasp", score=0.95, source="synonym_exact", rank=1)
    ]
    l2 = [
        OptionCandidate(parameter="G", option_code="g_touch", score=0.8, source="trgm", rank=1)
    ]
    chosen, top, reason = _merge_l1_l2(l1, l2)
    assert reason == "engines_disagree"
    assert chosen and chosen.option_code == "g_grasp"
    assert {c.option_code for c in top} >= {"g_grasp", "g_touch"}


# ── P 方向數情境規則（IE 裁決 D3-017：放入機構件→對準／放上盤面→無方向）──────

_P_VARIANTS = [
    {"parameter": "P", "option_code": "p_place_single", "synonym_norm": "放至", "priority": 0},
    {"parameter": "P", "option_code": "p_place_none", "synonym_norm": "放至", "priority": 1},
    {"parameter": "P", "option_code": "p_place_single", "synonym_norm": "放置", "priority": 0},
    {"parameter": "P", "option_code": "p_place_none", "synonym_norm": "放置", "priority": 1},
    {"parameter": "P", "option_code": "p_hold", "synonym_norm": "保持住", "priority": 0},
]


def _p_set(sets):
    return next(s for s in sets if s.parameter == "P")


@pytest.mark.asyncio
async def test_p_direction_mechanism_defaults_single():
    """機構件賓語（治具）→ p_place_single（方向數預設一種）；另一變體進 top_k。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "雙手抓握主板放至DIMM壓合治具"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_single"
    assert [c.option_code for c in p.top_k[:2]] == ["p_place_single", "p_place_none"]


@pytest.mark.asyncio
async def test_p_direction_surface_picks_none():
    """盤面賓語（工作台）→ p_place_none（IE 情境規則：無方向）。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "雙手重新抓握主板放至潔淨棚的工作台"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_none"
    assert [c.option_code for c in p.top_k[:2]] == ["p_place_none", "p_place_single"]


@pytest.mark.asyncio
async def test_p_direction_unclassified_keeps_default_flags_review():
    """賓語不在兩類名單（規定位置處）→ 維持預設 single＋needs_review（IE 裁決）。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "左手抓握DIMM材料盒放至規定位置處"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_single"
    assert p.needs_review is True
    assert p.review_reason == "p_direction_unclassified"


@pytest.mark.asyncio
async def test_p_direction_tail_bounded_by_clause():
    """賓語擷取止於子句標點：「放至定位,再從料架取料」不得跨子句配到料架（盤面）。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "放至定位,再從料架取料"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_place_single"
    assert p.review_reason == "p_direction_unclassified"


@pytest.mark.asyncio
async def test_p_direction_rule_skips_non_variant_faces():
    """非方向變體面（保持住→p_hold）原樣通過，不被規則改寫。"""
    linker = SlotLinker(_P_VARIANTS)
    sets = await linker.link(_plan("move_place", "雙手抓握主板保持住至流水線"))
    p = _p_set(sets)
    assert p.chosen and p.chosen.option_code == "p_hold"
    assert p.review_reason is None


# ── X/I 面命中掛進對應格（D3-024；CM 序列＝A B G M X I A，X/I 與 M 同 cycle）──

_XI_SYNONYMS = [
    {"parameter": "M", "option_code": "m_press", "synonym_norm": "按壓", "priority": 0},
    {"parameter": "X", "option_code": "x_screw_fix", "synonym_norm": "鎖附", "priority": 0},
    {"parameter": "X", "option_code": "x_blow_clean", "synonym_norm": "清潔", "priority": 0},
    {"parameter": "I", "option_code": "i_confirm", "synonym_norm": "確認", "priority": 0},
]


def _sets_of(sets, parameter):
    return [s for s in sets if s.parameter == parameter]


@pytest.mark.asyncio
async def test_cm_action_mounts_x_on_face_hit():
    """controlled_move 句面有 X 面（鎖附）→ X 掛進 x4.x_code（IE 登記的
    x_screw_fix 不再閒置）。mutation：X 掛值拆掉 → 本測紅。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("controlled_move", "鎖附主機板固定螺絲"))
    x = _sets_of(sets, "X")
    assert x, "X 面命中必須掛格"
    assert x[0].field == "x4.x_code"
    assert x[0].chosen and x[0].chosen.option_code == "x_screw_fix"
    assert x[0].needs_review is False and x[0].review_reason is None


@pytest.mark.asyncio
async def test_cm_action_mounts_i_on_face_hit():
    """controlled_move 句面有 I 面（確認）→ I 掛進 i5.i_code，且因 action 無
    inspect_kind role 帶 i_range_assumed（H2：視線範圍守門不分 action_type）。
    mutation：I 掛值拆掉 → 本測紅；守門綁回 action_type=="inspect" → 本測紅。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("controlled_move", "並確認DIMM點位"))
    i = _sets_of(sets, "I")
    assert i, "I 面命中必須掛格"
    assert i[0].field == "i5.i_code"
    assert i[0].chosen and i[0].chosen.option_code == "i_confirm"
    assert i[0].needs_review is True
    assert i[0].review_reason == "i_range_assumed", (
        "「視線範圍未明→取 NORMAL」是假設（i_confirm 6 vs i_confirm_out 16 TMU）"
        "——I 掛值不得繞過守門"
    )


@pytest.mark.asyncio
async def test_cm_action_mounts_x_and_i_together():
    """X＋I 同句（鎖附＋確認）＝單一 CM cycle 的兩格同時掛（spec §2：
    同 cycle 本來就容納 M/X/I）。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("controlled_move", "並鎖附固定並確認螺絲到位"))
    assert _sets_of(sets, "X") and _sets_of(sets, "I")
    assert _sets_of(sets, "X")[0].chosen.option_code == "x_screw_fix"
    assert _sets_of(sets, "I")[0].chosen.option_code == "i_confirm"


@pytest.mark.asyncio
async def test_cm_action_no_xi_noise_without_face_hit():
    """句面無 X/I 面 → 不追加 spec（不製造 no_candidate 噪音；與 B 的條件式
    追加同構）。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("controlled_move", "按壓功能測試臺"))
    assert not _sets_of(sets, "X") and not _sets_of(sets, "I")
    m = _sets_of(sets, "M")
    assert m and m[0].chosen.option_code == "m_press"


@pytest.mark.asyncio
async def test_gm_action_does_not_mount_xi():
    """GM 序列（A B G A B P A）沒有 X/I 格——move_place 句面即使有 X 面
    （鎖附）也不掛（掛了＝把 CM 參數塞進 GM cycle）。"""
    linker = SlotLinker(_XI_SYNONYMS + _P_VARIANTS)
    sets = await linker.link(_plan("move_place", "鎖附後放至治具"))
    assert not _sets_of(sets, "X") and not _sets_of(sets, "I")


@pytest.mark.asyncio
async def test_process_action_mounts_i_partner_cell():
    """process（core X）句面有 I 面 → I 伴隨格也掛（CM 三格同 cycle）；
    伴隨 I 格同樣帶 i_range_assumed（H2 守門不分掛格路徑）。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("process", "鎖附兩顆螺絲並確認到位"))
    assert _sets_of(sets, "X")[0].chosen.option_code == "x_screw_fix"
    i = _sets_of(sets, "I")[0]
    assert i.chosen.option_code == "i_confirm"
    assert i.needs_review is True and i.review_reason == "i_range_assumed"


@pytest.mark.asyncio
async def test_inspect_core_i_without_inspect_kind_keeps_flag():
    """inspect 原路徑不變（H2 解綁不是放寬）：inspect action 無 inspect_kind
    role → core I 格照樣 i_range_assumed。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("inspect", "確認DIMM到位"))
    i = _sets_of(sets, "I")[0]
    assert i.chosen and i.chosen.option_code == "i_confirm"
    assert i.needs_review is True and i.review_reason == "i_range_assumed"


@pytest.mark.asyncio
async def test_inspect_with_inspect_kind_role_no_flag():
    """action 帶 inspect_kind role（視線範圍有明示來源）→ 不掛假設旗標。"""
    linker = SlotLinker(_XI_SYNONYMS)
    plan = _plan(
        "inspect",
        "確認DIMM到位",
        {"inspect_kind": RoleValue(text="確認", status="explicit")},
    )
    sets = await linker.link(plan)
    i = _sets_of(sets, "I")[0]
    assert i.chosen and i.chosen.option_code == "i_confirm"
    assert i.needs_review is False and i.review_reason is None


# ── X input_mode 守門（D3-024 複審 H1）×  清潔情境守門（D3-021）──────────────
#
# x_blow_clean 是 seconds 模式（製程時間 IE 量測給值）——無秒數來源不落
# chosen（X0＋x_seconds_required）；清潔情境旗標只對真的掛上的值有意義
# （帶秒數來源時才輪得到它）。

_X_SECONDS_ROLE = {
    "process_kind": RoleValue(text="清潔", value=6, unit="秒", status="explicit")
}


@pytest.mark.asyncio
async def test_x_seconds_mode_without_source_not_mounted():
    """seconds 模式且無秒數來源 → 不落 chosen（cycle X 格維持空＝X0）、
    候選仍留 top_k、掛 x_seconds_required（資訊保留、需求浮上、不硬拒）。
    mutation：input_mode 判斷拆掉 → chosen 掛上 → 本測紅（engine_gate 版
    見 test_engine_gate_seconds_x_not_invalid）。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("controlled_move", "按壓把手並清潔卡槽"))
    x = _sets_of(sets, "X")
    assert x, "X 面命中仍要出候選格（資訊保留）"
    assert x[0].chosen is None, "seconds 模式無秒數來源不得落 chosen"
    assert [c.option_code for c in x[0].top_k] == ["x_blow_clean"]
    assert x[0].needs_review is True
    assert x[0].review_reason == "x_seconds_required"


@pytest.mark.asyncio
async def test_x_seconds_mode_with_source_mounts():
    """seconds 模式**帶秒數來源**（process_kind role 帶秒值＝compile 讀
    x_seconds 的同一形狀）→ 照掛；吹風脈絡下不帶旗。"""
    linker = SlotLinker(_XI_SYNONYMS)
    plan = _plan("controlled_move", "拿取風槍清潔DIMM卡槽", dict(_X_SECONDS_ROLE))
    sets = await linker.link(plan)
    x = _sets_of(sets, "X")
    assert x and x[0].chosen and x[0].chosen.option_code == "x_blow_clean"
    assert x[0].needs_review is False and x[0].review_reason is None


@pytest.mark.asyncio
async def test_x_clean_without_context_mounts_value_but_needs_review():
    """「清潔→x_blow_clean」有秒數來源但句面無風槍/吹風脈絡：掛值**照掛**
    （不越權丟候選）但 needs_review＋x_clean_context_unverified（IE 只裁了
    吹風情境，D3-021）。mutation：守門拆掉（無條件套用）→ 本測紅。"""
    linker = SlotLinker(_XI_SYNONYMS)
    plan = _plan("controlled_move", "清潔外殼", dict(_X_SECONDS_ROLE))
    sets = await linker.link(plan)
    x = _sets_of(sets, "X")
    assert x and x[0].chosen and x[0].chosen.option_code == "x_blow_clean"
    assert x[0].needs_review is True
    assert x[0].review_reason == "x_clean_context_unverified"


@pytest.mark.asyncio
async def test_x_clean_guard_applies_to_process_core_cell():
    """守門對 process 的 core X 格同樣作用（判定單一出處，不分掛格路徑）。"""
    linker = SlotLinker(_XI_SYNONYMS)
    plan = _plan("process", "清潔外殼", dict(_X_SECONDS_ROLE))
    sets = await linker.link(plan)
    x = _sets_of(sets, "X")
    assert x and x[0].chosen and x[0].chosen.option_code == "x_blow_clean"
    assert x[0].needs_review is True
    assert x[0].review_reason == "x_clean_context_unverified"


@pytest.mark.asyncio
async def test_x_seconds_guard_applies_to_process_core_cell():
    """input_mode 守門對 process 的 core X 格同樣作用：不落 chosen →
    missing_core_x（incomplete）而非 complete+引擎拒。"""
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(_plan("process", "清潔外殼"))
    x = _sets_of(sets, "X")
    assert x and x[0].chosen is None
    assert x[0].review_reason == "x_seconds_required"


# ── engine_gate 合成句（CI_GATES 掛值閘門：核心格可填＋新格面命中）────────────
#
# 語料對「complete=True 才觸發」的失效結構性失明（D3-024 複審 H1 實證：
# 語料 X/I 句全 missing_core_m，掛值→引擎拒的路徑零覆蓋）——動 linker 掛值
# 必須有「核心格可填＋新格面命中」的合成句跑完整 engine_gate。


async def _engine_gate_run(action_type: str, text: str, roles: dict | None = None):
    from ddm_v2.most_compiler.compile import allow_lists_from_rule_set, compile_plan
    from ddm_v2.most_compiler.engine_gate import apply_engine_gate
    from ddm_v2.most_engine.providers import build_from_seed_v2
    from ddm_v2.nlp.routing import compute_routing

    plan = _plan(action_type, text, roles)
    linker = SlotLinker(_XI_SYNONYMS)
    candidates = await linker.link(plan)
    rs = build_from_seed_v2()
    drafts = compile_plan(
        plan,
        candidates,
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists=allow_lists_from_rule_set(rs),
    )
    drafts = apply_engine_gate(drafts, rs)
    status, reasons = compute_routing(plan, candidates, drafts, auto_enabled=True)
    return candidates, drafts, status, reasons


@pytest.mark.asyncio
async def test_engine_gate_fixed_x_true_tmu():
    """(a) 核心格可填（按壓→M）＋fixed X 面（鎖附→x_screw_fix，fixed_seconds
    0.216s）→ complete、引擎收、真 TMU 含 X 段（M3＋X6＝9.0）。"""
    _cands, drafts, status, _reasons = await _engine_gate_run(
        "controlled_move", "按壓把手並鎖附固定"
    )
    d = drafts[0]
    assert d.complete is True
    assert d.engine_result is not None, "fixed X 是真值可算——引擎必須收"
    assert d.engine_result["total_tmu"] == 9.0
    assert d.engine_result["tech_line"] == "A0 B0 G0 M3 X6 I0 A0"
    assert d.cycle["x4"]["x_code"] == "x_screw_fix"
    assert status == "auto", "全 exact、無旗標、真 TMU——fixed X 不擋 auto"


@pytest.mark.asyncio
async def test_engine_gate_seconds_x_not_invalid():
    """(b) 複審 H1 實測句「按壓把手並清潔卡槽」：seconds X（x_blow_clean，
    無秒數來源）不落 chosen → X0、引擎收（M3＝3.0）、routing 不 invalid、
    x_seconds_required 旗標在。mutation：input_mode 判斷拆掉 → 掛值進 chosen
    → 引擎拒 X_SECONDS_REQUIRED → routing=invalid → 本測紅。"""
    cands, drafts, status, _reasons = await _engine_gate_run(
        "controlled_move", "按壓把手並清潔卡槽"
    )
    d = drafts[0]
    assert status != "invalid", "合法草稿（核心 M 可填）不得因 seconds X 被整筆判死"
    assert status == "review", "x_seconds_required 需 IE 給秒數——不 auto"
    assert d.complete is True
    assert d.engine_result is not None and d.engine_result["total_tmu"] == 3.0
    assert d.cycle["x4"]["x_code"] is None, "cycle X 格維持空＝X0（今天行為不變）"
    assert not any(i.startswith("engine_reject_") for i in d.issues)
    x = _sets_of(cands, "X")
    assert x and x[0].review_reason == "x_seconds_required", "需求要浮上（旗標在）"
    assert [c.option_code for c in x[0].top_k] == ["x_blow_clean"], "候選仍進 top_k"


@pytest.mark.asyncio
async def test_engine_gate_i_mounted_flags_and_blocks_auto():
    """複審 H2 實測句「按壓DIMM壓合治具的把手並確認到位」：I 掛值（i_confirm
    6 TMU＝NORMAL 假設）→ complete 9.0，但 i_range_assumed 擋 auto。
    mutation：守門綁回 action_type=="inspect" → routing=auto → 本測紅。"""
    cands, drafts, status, _reasons = await _engine_gate_run(
        "controlled_move", "按壓DIMM壓合治具的把手並確認到位"
    )
    d = drafts[0]
    assert d.complete is True
    assert d.engine_result is not None and d.engine_result["total_tmu"] == 9.0
    assert d.engine_result["tech_line"] == "A0 B0 G0 M3 X0 I6 A0"
    i = _sets_of(cands, "I")
    assert i and i[0].chosen and i[0].chosen.option_code == "i_confirm"
    assert i[0].review_reason == "i_range_assumed"
    assert status == "review", "視線範圍未明的 NORMAL 假設不得 auto 採用"


@pytest.mark.asyncio
async def test_xi_mounted_cycle_still_incomplete_without_core_m():
    """紅線（D3-024）：X/I 掛值不放寬完整性——controlled_move 缺 M 面仍
    missing_core_m（「X 承載做工時 M 可為零」是 IE 域判準，未裁不硬通；
    待裁題列 docs/llm/gold-review/README.md 快答清單）。"""
    from ddm_v2.most_compiler.compile import compile_plan

    plan = _plan("controlled_move", "鎖附主機板固定螺絲")
    linker = SlotLinker(_XI_SYNONYMS)
    sets = await linker.link(plan)
    drafts = compile_plan(
        plan,
        sets,
        rule_set_code="MINIMOST_FACTORY_V2",
        allow_lists={"G": set(), "P": set(), "P_ADDON": set(), "M": {"m_press"},
                     "X": {"x_screw_fix", "x_blow_clean"}, "I": {"i_confirm"}, "B": set()},
    )
    assert len(drafts) == 1
    d = drafts[0]
    assert d.complete is False
    assert "missing_core_m" in d.issues, "completeness 判準不得因 X 掛值而放寬"
    assert (d.cycle or {}).get("x4", {}).get("x_code") == "x_screw_fix", (
        "X 值要掛進 cycle（判型解鎖後 x_screw_fix 不再閒置）"
    )
