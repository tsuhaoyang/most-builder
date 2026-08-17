"""版控同義詞詞典的 seed 實際落地（D3-030 B1）。

守的是**環境**不是程式：同義詞守門測試（`test_synonym_registration_governance`）
判定的是 DB 現存資料，若 CI／新環境的 seed 鏈漏跑 `scripts/dev_seed_synonyms.py`，
守門會以「DB 無任何同義詞」的模樣紅掉——訊息看起來像資料壞了，實際是少跑一步。
本檔把那件事講清楚：**版控的 22 條必須真的在 DB 裡**，缺哪條就報哪條。

另一半是冪等性：seed 會在每次 CI／每個開發環境重跑，重跑不得產生重複列
（UNIQUE 會擋，但擋下來的形式是整支腳本爆掉）。
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import text as sql

from ddm_v2.nlp.normalization import normalize

pytestmark = pytest.mark.integration

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_synonyms.py"


def _load():
    spec = importlib.util.spec_from_file_location("_dev_seed_synonyms_it", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SEED = _load()


def _expected_keys() -> set[tuple[str, str, str, int]]:
    return {
        (p, normalize(raw), code, prio) for p, code, raw, prio, _r in SEED.SYNONYMS
    }


async def _live_keys(db_session) -> set[tuple[str, str, str, int]]:
    rows = (
        await db_session.execute(
            sql(
                "select s.parameter, s.synonym_norm, s.option_code, s.priority"
                " from rule_option_synonyms s join rule_sets rs on rs.id = s.rule_set_id"
                " where rs.code = :code"
            ),
            {"code": SEED.RULE_SET_CODE},
        )
    ).all()
    return {(r[0], r[1], r[2], r[3]) for r in rows}


async def test_every_seeded_synonym_is_present_in_db(db_session):
    """seed 鏈跑過的 DB 必須含版控的每一條——缺了就是 seed 步驟沒跑（CI 順序）。"""
    missing = sorted(_expected_keys() - await _live_keys(db_session))
    assert missing == [], (
        f"DB 缺少版控詞典 {len(missing)} 條：{missing}——"
        "請在 migrate/seed 之後跑 `python scripts/dev_seed_synonyms.py`"
    )


async def test_seed_is_idempotent(db_session):
    """空詞典 → 22 新增；再跑一次 → 0 新增、22 略過，且總數維持 22。

    走 conftest 的 savepoint 隔離（先清空本 rule-set 的同義詞再重建），
    teardown rollback ⇒ 對真實資料零影響。
    """
    rs_id = (
        await db_session.execute(
            sql("select id from rule_sets where code = :code"),
            {"code": SEED.RULE_SET_CODE},
        )
    ).scalar_one()
    await db_session.execute(
        sql("delete from rule_option_synonyms where rule_set_id = :rs"), {"rs": rs_id}
    )
    await db_session.flush()

    assert await SEED.seed_synonyms(db_session) == (len(SEED.SYNONYMS), 0)
    first = await _live_keys(db_session)
    assert first == _expected_keys()

    assert await SEED.seed_synonyms(db_session) == (0, len(SEED.SYNONYMS))
    assert await _live_keys(db_session) == first
    count = (
        await db_session.execute(
            sql(
                "select count(*) from rule_option_synonyms where rule_set_id = :rs"
            ),
            {"rs": rs_id},
        )
    ).scalar_one()
    assert count == len(SEED.SYNONYMS), "重跑產生了重複列"


async def test_seed_refuses_when_rule_set_missing(db_session, monkeypatch):
    """邊界：rule-set 不存在時明確失敗（不靜默建立、不寫半套）。"""
    monkeypatch.setattr(SEED, "RULE_SET_CODE", "NO_SUCH_RULE_SET")
    with pytest.raises(SystemExit) as e:
        await SEED.seed_synonyms(db_session)
    assert "dev_seed_v2" in str(e.value)
