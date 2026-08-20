"""i18n 覆核狀態 API（ADR-032 D6）：待審清單摘要 ＋ 清單 ＋ 覆核 mutation。

| 端點 | 角色 | 說明 |
|---|---|---|
| `GET  /api/v2/i18n/review/summary` | analyst+ | `{total, reviewed, pending}` |
| `GET  /api/v2/i18n/review/pending` | analyst+ | 待審列表，可篩 entity_type/status |
| `POST /api/v2/i18n/review/mark-reviewed` | analyst+ | 標記已覆核（可同時修正譯文） |
| `POST /api/v2/i18n/review/assign` | analyst+ | 指派／取消指派 |

角色一律 analyst 以上（D6：取字典 admin 入口與主數據 analyst 入口的**下界**——
清單同時涵蓋兩類物件，不落在任何單一既有入口之下；與 D4 的 `_en` 編輯權一致。
沿用既有 `require_role`，不另造權限模型）。

**沒有批次核准端點，是刻意的**（ADR-032 R1／I5）：`g_grasp`(6 TMU)／`g_touch`(3 TMU)
這類「英文看起來一樣」的誤譯只有逐條人看才擋得住，一次核准 126 列會把覆核變成橡皮
圖章——而「每條譯文都有人負責」正是 D2（機器翻譯先全灌）賴以成立的三個前提之一。
要開這條路得先回答「怎麼避免橡皮圖章」，那是新的裁決，不是實作細節。
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.api.routes.v2.rule_set import option_http_error
from ddm_v2.auth.deps import CurrentUser, require_role
from ddm_v2.database import get_db_session
from ddm_v2.schemas.v2.i18n import (
    I18nAssignIn,
    I18nMarkReviewedIn,
    I18nPendingItemOut,
    I18nReviewItemOut,
    I18nReviewSummaryOut,
)
from ddm_v2.services.v2 import i18n_service as svc
from ddm_v2.services.v2 import rule_option_service as opt_svc
from ddm_v2.services.v2 import rule_set_service as rs_svc

router = APIRouter(prefix="/api/v2/i18n", tags=["v2-i18n"])

_ENTITY_TYPE_PATTERN = r"^(rule_option|vocab_item|motion_template)$"
_STATUS_PATTERN = r"^(never_translated|unreviewed|stale)$"

# 覆核 mutation 帶譯文修正時會走 D4 的 `_en` 寫入閘，因此會拋出選項級的那組例外
# （實務上碰得到的是 `EnLabelNotUnique`＝I5 衝突）。對映共用 `option_http_error`，
# 不在這裡另寫一份，見該函式檔頭。
_EN_GATE_ERRORS = (
    rs_svc.CertifiedImmutable, rs_svc.RuleSetRetired, rs_svc.NotEditable, rs_svc.RuleSetNotFound,
    opt_svc.EnFieldNotWritable, opt_svc.EnLabelNotUnique, opt_svc.OptionNotFound,
)


def _to_item(r: svc.TranslatableRow) -> I18nReviewItemOut:
    return I18nReviewItemOut(
        entity_type=r.entity_type,  # type: ignore[arg-type]
        scope_key=r.scope_key,
        field=r.field,
        status=r.status,  # type: ignore[arg-type]
        rule_set_code=r.rule_set_code,
        source_zh=r.source_zh,
        target_en=r.target_en,
        source_changed=r.source_changed,
        target_changed=r.target_changed,
        review_source=r.review_source,  # type: ignore[arg-type]
        translated_by=r.translated_by,
        translated_at=r.translated_at,
        reviewed_by=r.reviewed_by,
        reviewed_at=r.reviewed_at,
        assigned_to=r.assigned_to,
        assigned_at=r.assigned_at,
    )


@router.get("/review/summary", response_model=I18nReviewSummaryOut)
async def get_review_summary(
    entity_type: str | None = Query(default=None, pattern=_ENTITY_TYPE_PATTERN),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> I18nReviewSummaryOut:
    data = await svc.summary(session, entity_type=entity_type)
    return I18nReviewSummaryOut(**data)


@router.get("/review/pending", response_model=list[I18nPendingItemOut])
async def list_review_pending(
    entity_type: str | None = Query(default=None, pattern=_ENTITY_TYPE_PATTERN),
    status: str | None = Query(default=None, pattern=_STATUS_PATTERN),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> list[I18nPendingItemOut]:
    rows = await svc.pending_rows(session, entity_type=entity_type, status=status)
    return [I18nPendingItemOut(**_to_item(r).model_dump()) for r in rows]


@router.post("/review/mark-reviewed", response_model=I18nReviewItemOut)
async def mark_reviewed(
    payload: I18nMarkReviewedIn = Body(...),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> I18nReviewItemOut:
    """把一列標成「已由人覆核」（`source='human'` ＋ `reviewed_by`／`reviewed_at`
    ＋ `target_sha256`），可選在同一個請求裡帶入修正後的英文。

    `target_en` 一併帶入時：譯文先經 D4 的 `_en` 寫入閘落盤，再寫側表，**同一個
    交易**——任一步失敗整批 rollback，不會出現「字改了但清單還說未覆核」或反之。

    覆核之後若有人再改英文，`target_sha256` 對不上 → 這一列自動回到待審清單
    （`status='stale'` ＋ `target_changed=true`）。
    """
    try:
        row = await svc.mark_reviewed(
            session,
            entity_type=payload.entity_type,
            scope_key=payload.scope_key,
            field=payload.field,
            reviewed_by=user.employee_no,
            target_en=payload.target_en,
            rule_set_code=payload.rule_set_code,
            note=payload.note,
        )
    except _EN_GATE_ERRORS as e:
        raise option_http_error(e) from e
    return _to_item(row)


@router.post("/review/assign", response_model=I18nReviewItemOut)
async def assign_review(
    payload: I18nAssignIn = Body(...),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> I18nReviewItemOut:
    """指派一條待審項給某位員工（`assigned_to=null`／空白 ＝取消指派）。

    指派不改變 `status`——它記的是「誰在處理」，不是「處理到哪」。側表列不存在時
    就地建立（`never_translated` 的列本來就沒有側表列，而那正是最需要有人認領的一批），
    詳見 `i18n_service.assign_review`。
    """
    row = await svc.assign_review(
        session,
        entity_type=payload.entity_type,
        scope_key=payload.scope_key,
        field=payload.field,
        assigned_to=payload.assigned_to,
        actor=user.employee_no,
        rule_set_code=payload.rule_set_code,
    )
    return _to_item(row)
