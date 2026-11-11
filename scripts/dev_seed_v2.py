"""dev seed（v2）：rule_set 工廠 v1＋v2（ADR-014）+ 最小階層（site→…→worksheet）+ 詞彙。

讓持久化 demo 有 worksheet 可掛、wi_rows 有 vocab 可指。idempotent（已存在則略過）。
跑：  DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_v2.py
"""
from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import ddm_v2.models.v2 as M
from ddm_v2.seed.v2.policy_seed import seed_policy_factory_v1
from ddm_v2.seed.v2.rule_set_seed import seed_rule_set_factory_v1
from ddm_v2.seed.v2.rule_set_seed_v2 import seed_rule_set_factory_v2
from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
from ddm_v2.services.v2.rule_set_service import activate as activate_rule_set

# 固定 UUID（demo 可引用）
SITE = uuid.UUID("11111111-1111-1111-1111-111111111111")
PRODUCT = uuid.UUID("22222222-2222-2222-2222-222222222222")
SKU = uuid.UUID("33333333-3333-3333-3333-333333333333")
VERSION = uuid.UUID("44444444-4444-4444-4444-444444444444")
WORKSHEET = uuid.UUID("55555555-5555-5555-5555-555555555555")
V_OBJ = uuid.UUID("66666666-6666-6666-6666-666666666666")
V_FROM = uuid.UUID("77777777-7777-7777-7777-777777777777")
V_TO = uuid.UUID("88888888-8888-8888-8888-888888888888")


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        # rule_set（+ 子表）
        rs_v1 = (await s.execute(select(M.RuleSet).where(M.RuleSet.code == "MINIMOST_FACTORY_V1"))).scalar_one_or_none()
        if rs_v1 is None:
            rs_v1 = seed_rule_set_factory_v1(s)
            print("seeded rule_set:", rs_v1.code)
        else:
            print("rule_set exists:", rs_v1.code)
        rs = (await s.execute(select(M.RuleSet).where(M.RuleSet.code == "MINIMOST_FACTORY_V2"))).scalar_one_or_none()
        if rs is None:
            rs = seed_rule_set_factory_v2(s)  # V2＝v3 IE 認證字典（ADR-014）；新 worksheet 預設
            print("seeded rule_set:", rs.code)
        else:
            print("rule_set exists:", rs.code)

        # ADR-023 §3.3 規則 3 / §3.5：治理旗標由本編排腳本設定（值本身仍由 seed 模組權威）。
        # - V1/V2 皆走 import_v3_dictionary → seed 的認證路徑 → provenance='certified_import'
        # - V2 為 active（ADR-014 值權威）；V1 保持 published + inactive（回放版本）
        # 全新 DB 時 migration 的資料遷移跑在 seed 之前（當時無資料），故此處必須補設，
        # 否則新環境會沒有 active rule-set。
        for r in (rs_v1, rs):
            # 守衛式：只補未標記者，不覆寫營運端可能已調整的血緣（與下方 is_active 對稱）
            if r.provenance != "certified_import":
                r.provenance = "certified_import"
                print("  provenance=certified_import:", r.code)
        await s.flush()
        existing_active = (await s.execute(
            select(M.RuleSet).where(M.RuleSet.is_active.is_(True)))).scalar_one_or_none()
        if existing_active is None:
            # 走正規 activate()（含 published 前置＋validate_complete＋audit log），
            # 不直接寫 is_active——繞過前置檢查等於在 seed 開後門。
            await activate_rule_set(s, rs.code, actor="dev_seed")
            print("activated rule_set:", rs.code)
        else:
            print("active rule_set exists:", existing_active.code)

        # R2a：factory policy V1（migration 通常已種；此處 idempotent）
        mp, lp = await seed_policy_factory_v1(s)
        await s.flush()
        print("policy manifests:", mp.name, lp.name)

        async def ensure(model, pk, **kw):
            obj = await s.get(model, pk)
            if obj is None:
                obj = model(id=pk, **kw)
                s.add(obj)
                print("  + ", model.__name__, kw.get("name_zh") or kw.get("version_no") or pk)
            return obj

        await ensure(M.Site, SITE, external_code="SITE001", name_zh="示範廠區")
        await ensure(M.Product, PRODUCT, site_id=SITE, external_code="PRD0001", name_zh="示範產品")
        await ensure(M.Sku, SKU, product_id=PRODUCT, sku_code="HDL5X_DEMO", name_zh="示範機種")
        await ensure(M.ProcessVersion, VERSION, sku_id=SKU, version_no="v1", status="draft")
        await ensure(
            M.MostWorksheet,
            WORKSHEET,
            process_version_id=VERSION,
            model_label="HDL5X_DEMO",
            analyst="demo",
            default_rule_set_id=rs.id,
            modeling_policy_version_id=MODELING_FACTORY_V1_ID,
            level_policy_version_id=LEVEL_FACTORY_V1_ID,
        )
        await ensure(M.WorkVocabItem, V_OBJ, external_code="CMP0001", kind="component", name_zh="DIMM 內存")
        await ensure(M.WorkVocabItem, V_FROM, external_code="LOC0001", kind="from", name_zh="料架")
        await ensure(M.WorkVocabItem, V_TO, external_code="LOC0002", kind="to", name_zh="工作台")

        # RBAC bootstrap：初始 admin（員工編號 IEC141289）
        admin = (await s.execute(select(M.AppUser).where(M.AppUser.employee_no == "IEC141289"))).scalar_one_or_none()
        if admin is None:
            s.add(M.AppUser(id=uuid.uuid4(), employee_no="IEC141289", display_name="IEC141289", roles=["admin"]))
            print("  +  AppUser admin IEC141289")

        await s.commit()
    await engine.dispose()
    print("\n=== demo ids ===")
    print("worksheet_id:", WORKSHEET)
    print("object/from/to vocab:", V_OBJ, V_FROM, V_TO)
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
