"""v2 rule-set 編輯/版本化 API（#1）。

版本級：list / active / full / clone-draft / put-full / publish / activate / retire（ADR-023 §3.2）。
反向操作（D3b）：`DELETE /rule-sets/{code}`（僅 draft）／`POST /rule-sets/{code}/unretire`
（retired → published，不改 is_active）——補上 clone-on-write 與 retire 原本「有去無回」的缺口。
匯出入（D3）：`GET /rule-sets/{code}/export`（＝full ＋ metadata）／`POST /rule-sets/import`
（只建 draft+manual；§3.6。**認證值權威仍只走 CLI**：`scripts/import_v3_dictionary.py`）。
選項級（D2）：/rule-sets/{code}/params/{param}/... —— 每參數一組端點，**非泛型**。
v3 的「一套 PUT /options/{id} 打天下」在 v2 不成立（ADR-023 §2：12 張不同構子表）。

| param | 次級選擇 | 形狀 | 端點 |
|---|---|---|---|
| A | `?component=reach\\|twist\\|foot`（必填） | 帶 | `GET options` / `PUT bands`（整組替換） |
| B, G, X, I | 無 | 選項 | `GET/POST options`、`PATCH/DELETE options/{code}`、`POST .../duplicate` |
| P | `?section=base\\|addon`（必填） | 選項 | 同上 |
| M | `?section=verb`（必填） | 選項 | 同上 |
| M | `?section=ladder\\|foot\\|rotation\\|hand` | 帶 | `GET options` / `PUT bands` |

所有寫入：`require_role("analyst")` ＋ `rule_set_service.assert_editable`
（certified_import → 409、非 draft → 409）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.rule_set_options import (
    BandInvalid,
    BandsReplaceIn,
    ParamInvalid,
    SectionInvalid,
    SectionRequired,
)
from ddm_v2.services.v2 import rule_option_service as opt_svc
from ddm_v2.services.v2 import rule_set_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-ruleset"])


class CloneDraftIn(BaseModel):
    # ADR-023 §3.2：選填，缺省由服務層生成 {code}_DRAFT_{YYYYMMDDHHMM}（查重附序號）。
    new_code: str | None = None
    name_zh: str | None = None


@router.get("/rule-sets")
async def list_rule_sets(
    selectable: bool = Query(False, description="只回 published+active（供 UI 下拉；ADR-023 §3.4 規則 2）"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[dict]:
    return await svc.list_rule_sets(session, selectable=selectable)


@router.get("/rule-sets/active")
async def get_active(session: AsyncSession = Depends(get_db_session, scope="function"),
                     _: CurrentUser = Depends(current_user)) -> dict:
    """目前啟用中的 rule-set（前端取代寫死常數；ADR-023 §3.5）。無 active＝設定錯誤 → 500。"""
    rs = await svc.get_active_rule_set(session)
    return {"id": str(rs.id), "code": rs.code, "name_zh": rs.name_zh}


@router.get("/rule-sets/{code}/full")
async def get_full(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                   _: CurrentUser = Depends(require_role("analyst"))) -> dict:
    """整份 12 張子表（值權威內容）。

    RBAC＝analyst（D7b 收緊，原為 `current_user`）：IE 認證工時字典是 IE 部門的 know-how，
    原本任何有帳號的員工——包含 `deps.current_user` JIT 建立、`roles=[]`、level=0 的新
    使用者——都能一次拿走整份值。而且同一份內容在 `GET /diff` 已是 analyst，形成
    「`/full` 拿得到的東西 `/diff` 反而拒絕」的矛盾。三支（full/export/diff）現已一致。

    ⚠️ 不連坐收緊 `GET /rule-sets`（版本清單）、`/rule-sets/active`、`/rule-sets/{code}/options`：
    工作台建模需要它們，且它們給的是「可選項目」而非整份值表。
    """
    try:
        return await svc.load_full(session, code)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")


@router.post("/rule-sets/{code}/clone-draft")
async def clone_draft(code: str, payload: CloneDraftIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                      user: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.clone_draft(session, code, payload.new_code, payload.name_zh, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.RuleSetExists:
        raise HTTPException(status_code=409, detail=f"code 已存在：{payload.new_code}")


@router.put("/rule-sets/{code}/full")
async def put_full(code: str, full: dict[str, Any] = Body(...), session: AsyncSession = Depends(get_db_session, scope="function"),
                   user: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.replace_children(session, code, full, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (BandInvalid, svc.PayloadInvalid) as e:
        # 帶界契約與 PUT /bands 同源（D2 HIGH-2）；區塊鍵/欄位型別與 import 同源（D3 HIGH-1/2）
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rule-sets/{code}/diff")
async def diff_rule_set(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                        _: CurrentUser = Depends(require_role("analyst"))) -> dict:
    """本版本相對**目前 active 版本**的值差異（ADR-023 D7 / H-1）。

    給覆核者看「按下 publish 之後，線上的值會從什麼變成什麼」。在此之前 publish 只回
    `{"code":..., "status":"published"}`，approver 對被覆核的內容零資訊——
    log 上只留他的員編，卻分不出他是改值的人還是覆核的人。

    基準固定為 active（＝發布啟用後會被取代的那一版），回應以 `base_code` 標明。
    差異結構：`diff.sections[<區塊>].{added,removed,changed}`（changed 逐欄帶前後值）
    ＋ `diff.row_counts`（12 區塊前後列數）＋ `diff.header`（name_zh / multiplier）。

    另附血緣（D7b）：`source_code`（本版 clone 自哪一版；查稽核紀錄，無紀錄＝null）與
    `base_is_source`。來源不是 active 時多一個 `lineage_note`，提醒覆核者這份 diff
    混了「兩條血緣的既有落差」與「作者這次的編輯」，不可全部當成本次改動。

    RBAC：analyst 以上（唯讀，且與 `GET /full` 同樣是字典內容）。
    """
    try:
        return await svc.diff_against_active(session, code)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")


@router.get("/rule-sets/{code}/export")
async def export_rule_set(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                          user: CurrentUser = Depends(require_role("analyst"))) -> dict:
    """匯出版本（ADR-023 §3.6）。形狀＝`GET /full` ＋ `schema_version/exported_at/exported_by`。

    RBAC＝analyst（D7b 收緊，原為 `current_user`）：它與 `GET /full` 是同一份內容，
    只多三個 metadata 欄——兩者權限必須一致，否則收緊 `/full` 只是把外流改走這條路。
    去掉三個 metadata 欄後即為 `PUT /full` 的合法 body——export→離線編輯→import 閉環。
    """
    try:
        return await svc.export_full(session, code, exported_by=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")


class ImportIn(BaseModel):
    # body 直接是 export 形狀（extra 欄位＝各子表），另可帶 new_code / name_zh。
    model_config = ConfigDict(extra="allow")

    new_code: str | None = None
    name_zh: str | None = None


@router.post("/rule-sets/import")
async def import_rule_set(payload: ImportIn = Body(...),
                          session: AsyncSession = Depends(get_db_session, scope="function"),
                          user: CurrentUser = Depends(require_role("analyst"))) -> dict:
    """由匯出負載建立新草稿（ADR-023 §3.6）。**只建 draft + manual**。

    schema_version 必填且須為 "1"；缺區塊鍵、必要子表為空、multiplier 非正數或帶界非法
    → 400（不得靜默建立不完整版本）；new_code 撞既有 code → 409；缺省 code 依 clone-draft
    同一套自動命名規則。

    回應含 `warnings`：合法但會改變計算路徑的情況（目前唯一一項＝`m_foot` 為空 →
    `foot_tmu()` 靜默回退 `ladder_tmu()`）必須在匯入當下就講出來。
    """
    body = payload.model_dump()
    new_code = body.pop("new_code", None)
    name_zh = body.pop("name_zh", None)
    try:
        return await svc.import_draft(session, body, new_code, name_zh, actor=user.employee_no)
    except (svc.PayloadInvalid, BandInvalid) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except svc.RuleSetExists:
        raise HTTPException(status_code=409, detail=f"code 已存在：{new_code}")


@router.post("/rule-sets/{code}/publish")
async def publish(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                  user: CurrentUser = Depends(require_role("approver"))) -> dict:
    try:
        return await svc.publish(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuleSetIncomplete as e:
        # ADR-023 §3.2：發布前完整性驗證未過 → 409（帶缺表詳情）。
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_INCOMPLETE", "message": str(e)})


@router.post("/rule-sets/{code}/activate")
async def activate(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                   user: CurrentUser = Depends(require_role("approver"))) -> dict:
    """啟用為唯一 active 版本（ADR-023 §3.2）。非 published → 400；不完整 → 409。"""
    try:
        return await svc.activate(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuleSetIncomplete as e:
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_INCOMPLETE", "message": str(e)})


@router.post("/rule-sets/{code}/retire")
async def retire(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                 user: CurrentUser = Depends(require_role("approver"))) -> dict:
    """下架版本（ADR-023 §3.2）。啟用中版本 → 400（須先啟用其他版本）。

    ⚠️ 下架不影響回放：已引用該版本的 cycle 仍可載入重算（§3.4）。
    """
    try:
        return await svc.retire(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rule-sets/{code}/unretire")
async def unretire(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                   user: CurrentUser = Depends(require_role("approver"))) -> dict:
    """解除封存：retired → published（ADR-023 D3b）。

    `retired` 原本是終態（只有 publish/activate/retire，無反向操作），誤按封存後無 UI 可救。
    但 retired 的語意只是「不再用於新工作」，歷史 cycle 依 §3.4 鐵則照常載入——
    解除封存不影響任何資料完整性。

    ⚠️ `is_active` 維持 false：解除封存**不等於**啟用，要啟用請另外呼叫 `/activate`。
    """
    try:
        return await svc.unretire(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_NOT_RETIRED", "message": str(e)})


@router.delete("/rule-sets/{code}")
async def delete_rule_set(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                          user: CurrentUser = Depends(require_role("approver"))) -> dict:
    """刪除一個 draft 版本（ADR-023 D3b）。clone-on-write 的反向操作。

    409 一律帶 `detail.code`，讓前端能區分五種拒絕原因（不是只看狀態碼）：

    | detail.code | 原因 |
    |---|---|
    | `CERTIFIED_IMMUTABLE` | provenance='certified_import'（認證版本不受線上治理操作） |
    | `RULE_SET_NOT_DRAFT` | status 為 published/retired |
    | `RULE_SET_ACTIVE` | is_active=true |
    | `RULE_SET_IN_USE` | 已被 cycle/worksheet/module 版本引用（`detail.references` 附各表引用數） |

    12 張規則子表 ＋ rule_option_synonyms 由 DB CASCADE 一併刪除（回應的
    `children_deleted` 為刪除前的列數快照）。
    """
    try:
        return await svc.delete_rule_set(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.CertifiedImmutable as e:
        raise HTTPException(status_code=409, detail={"code": "CERTIFIED_IMMUTABLE", "message": str(e)})
    except svc.RuleSetActive as e:
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_ACTIVE", "message": str(e)})
    except svc.NotEditable as e:
        # RuleSetActive/CertifiedImmutable 都是 NotEditable 的子類，已在上面先攔；到這裡只剩「非 draft」。
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_NOT_DRAFT", "message": str(e)})
    except svc.RuleSetInUse as e:
        raise HTTPException(status_code=409, detail={
            "code": "RULE_SET_IN_USE", "message": str(e),
            "references": {k: v for k, v in e.refs.items() if v},
        })


# ══════════════════════════════════════════════════════════════════
# 選項級 CRUD（ADR-023 D2）
# ══════════════════════════════════════════════════════════════════

_SECTION_Q = Query(
    None,
    description="P/M 的次級區塊（P: base|addon；M: verb|ladder|foot|rotation|hand）。缺省 → 400，不會靜默選一個。",
)
_COMPONENT_Q = Query(None, description="A 的分量（reach|twist|foot）；即 A 的 section。")


def _handle(exc: Exception) -> HTTPException:
    """選項級端點的統一錯誤對映（單一實作＝不會有端點對映不一致）。"""
    if isinstance(exc, svc.CertifiedImmutable):
        return HTTPException(status_code=409, detail={"code": "CERTIFIED_IMMUTABLE", "message": str(exc)})
    if isinstance(exc, svc.NotEditable):
        return HTTPException(status_code=409, detail={"code": "RULE_SET_FROZEN", "message": str(exc)})
    if isinstance(exc, svc.RuleSetNotFound):
        return HTTPException(status_code=404, detail=f"rule-set 不存在：{exc}")
    if isinstance(exc, opt_svc.OptionNotFound):
        return HTTPException(status_code=404, detail=f"選項不存在：{exc}")
    if isinstance(exc, opt_svc.OptionExists):
        return HTTPException(status_code=409, detail=f"選項代碼已存在：{exc}")
    if isinstance(exc, (SectionRequired, SectionInvalid, ParamInvalid)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (opt_svc.BandInvalid, opt_svc.BandsNotSupported, opt_svc.OptionConstraintViolation)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValidationError):
        # payload 與該 (param, section) 的 schema 不符 → 422（欄位級錯誤原樣回傳）
        return HTTPException(status_code=422, detail=exc.errors(include_url=False))
    raise exc


_OPT_ERRORS = (
    svc.CertifiedImmutable, svc.NotEditable, svc.RuleSetNotFound,
    opt_svc.OptionNotFound, opt_svc.OptionExists, opt_svc.OptionConstraintViolation,
    opt_svc.BandInvalid, opt_svc.BandsNotSupported,
    SectionRequired, SectionInvalid, ParamInvalid, ValidationError,
)


@router.get("/rule-sets/{code}/params/{param}/options")
async def list_param_options(
    code: str,
    param: str,
    section: str | None = _SECTION_Q,
    component: str | None = _COMPONENT_Q,
    active_only: bool = Query(False, description="只回啟用中的列（供下拉；編輯畫面請留 false）"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> dict:
    """讀一個 (param, section) 的所有列。帶型區塊也走這裡（回應的 `kind` 區分）。"""
    try:
        return await opt_svc.list_options(session, code, param, section or component, active_only=active_only)
    except _OPT_ERRORS as e:
        raise _handle(e) from e


@router.post("/rule-sets/{code}/params/{param}/options")
async def create_param_option(
    code: str,
    param: str,
    payload: dict[str, Any] = Body(...),
    section: str | None = _SECTION_Q,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await opt_svc.create_option(session, code, param, section, payload, actor=user.employee_no)
    except _OPT_ERRORS as e:
        raise _handle(e) from e


@router.patch("/rule-sets/{code}/params/{param}/options/{option_code}")
async def update_param_option(
    code: str,
    param: str,
    option_code: str,
    payload: dict[str, Any] = Body(...),
    section: str | None = _SECTION_Q,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """部分更新：未給的欄位沿用現值，但合併後仍過**完整** schema 驗證。"""
    try:
        return await opt_svc.update_option(session, code, param, section, option_code, payload, actor=user.employee_no)
    except _OPT_ERRORS as e:
        raise _handle(e) from e


@router.delete("/rule-sets/{code}/params/{param}/options/{option_code}")
async def delete_param_option(
    code: str,
    param: str,
    option_code: str,
    section: str | None = _SECTION_Q,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """硬刪（draft 專屬，無人引用 → 不需 soft-delete）。"""
    try:
        return await opt_svc.delete_option(session, code, param, section, option_code, actor=user.employee_no)
    except _OPT_ERRORS as e:
        raise _handle(e) from e


@router.post("/rule-sets/{code}/params/{param}/options/{option_code}/duplicate")
async def duplicate_param_option(
    code: str,
    param: str,
    option_code: str,
    section: str | None = _SECTION_Q,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """複製一筆選項；新 code 為 `{code}_copy`／`{code}_copy_2`…（保證唯一）。"""
    try:
        return await opt_svc.duplicate_option(session, code, param, section, option_code, actor=user.employee_no)
    except _OPT_ERRORS as e:
        raise _handle(e) from e


@router.put("/rule-sets/{code}/params/{param}/bands")
async def replace_param_bands(
    code: str,
    param: str,
    payload: BandsReplaceIn = Body(...),
    component: str | None = _COMPONENT_Q,
    section: str | None = _SECTION_Q,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """帶型區塊**整組替換**（A / M.ladder|foot|rotation|hand）。

    帶界必須遞增、無重疊，open-ended（上界 null）只能在末位；
    單筆增刪不提供，因為那會產生非法中間態（ADR-023 §2）。
    """
    try:
        return await opt_svc.replace_bands(session, code, param, component or section, payload.items, actor=user.employee_no)
    except _OPT_ERRORS as e:
        raise _handle(e) from e
