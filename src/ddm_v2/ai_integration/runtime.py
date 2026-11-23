"""外部 ai_service 整合的行程級單例（ADR-037 S3 路由接線）。

為什麼要單例：`GuardedWiParser` 的並行上限、每人每分鐘、每日預算、single-flight 都在**程序記憶體**內計數
（ADR-037 D8；多 worker 時各自計數，上限實際是 worker 數倍，見 BL-ENG-15）。每個請求各建一個就等於沒有限制。

**建立時機**：app 啟動時在背景執行緒預熱（`warm_up()`，由 lifespan 呼叫），請求路徑用 `await get_runtime_async()`。
建立要做同步 I/O（`validate_config` 的 DNS 檢查、讀金鑰檔），**不能在 event loop 上做**——DNS 慢或掛掉時會卡住
所有請求，不只 AI。所以：
- 請求路徑一律經 `asyncio.to_thread` 建立（萬一預熱還沒完成或失敗）；
- 建立期間的任何例外都收成「啟用但不可用」，不往外拋：設定不合格時其他功能不受影響（ADR-037 D7）。

**暫時性失敗會重試**：DNS 解析失敗或連不到（`UNREACHABLE`）不代表設定錯，可能只是 ai_service 比 MOST 晚起來。
這類結果只保留 `RETRY_AFTER_S` 秒，之後下一個請求會重建一次。設定本身錯（金鑰太短、host 不在允許清單）要改設定
並重啟才會生效——那是營運者的明確動作，不該讓每個請求都重試。

`status`（`enabled`／`available`）不打網路、不讀熔斷器：`GET /wi-ai/status` 是 viewer 可呼叫的端點，不能讓任何人
重新整理頁面就觸發外送；熔斷器的 `allow()` 會改變半開狀態，不是唯讀查詢。所以 `available` 只代表「開關開著且
設定通過檢查」，不代表 ai_service 此刻一定回得來——真的回不來時，請求會降級成 rule_based（回應帶 `ai_error`）。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

from ddm_v2.ai_integration.adapter import AiServiceWiParser, DisabledWiParser
from ddm_v2.ai_integration.client import AiServiceClient
from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind
from ddm_v2.ai_integration.guard import GuardedWiParser
from ddm_v2.ai_integration.ports import WiParserPort

logger = logging.getLogger(__name__)

# 暫時性失敗（DNS、連不到）之後多久允許重建一次
RETRY_AFTER_S = 60.0
_TRANSIENT_KINDS = frozenset({AiServiceErrorKind.UNREACHABLE})


@dataclass(frozen=True)
class AiRuntime:
    parser: WiParserPort
    enabled: bool
    available: bool
    # 部署設定的 ai_service bundle code（快取鍵與回應比對用）；不可用時為 None
    service_bundle_code: str | None
    # 這份結果有效到何時（monotonic 秒）；None＝一直有效。只有暫時性失敗會設
    expires_at: float | None = field(default=None, compare=False)


_lock = threading.Lock()
_runtime: AiRuntime | None = None


def _unavailable(kind: AiServiceErrorKind, *, enabled: bool, transient: bool = False) -> AiRuntime:
    return AiRuntime(
        parser=DisabledWiParser(kind),
        enabled=enabled,
        available=False,
        service_bundle_code=None,
        expires_at=time.monotonic() + RETRY_AFTER_S if transient else None,
    )


def _enabled_flag_is_set() -> bool:
    """`load_config` 失敗時（例：數字格式錯）仍要知道營運者是否開了開關，讓 `enabled` 反映營運者的意圖。"""
    import os

    from ddm_v2.ai_integration.config import _parse_bool

    return _parse_bool(os.environ.get("DDM_AI_SERVICE_ENABLED"))


def _build() -> AiRuntime:
    """同步 I/O（DNS、讀檔）：只能在執行緒裡跑。任何例外都收成「不可用」，不往外拋。"""
    from ddm_v2.ai_integration.config import default_resolver, load_config, validate_config

    try:
        cfg = load_config()
    except AiServiceError as err:
        logger.warning("ai_service integration disabled: %s", err)
        return _unavailable(err.kind, enabled=_enabled_flag_is_set())
    if not cfg.enabled:
        return _unavailable(AiServiceErrorKind.DISABLED, enabled=False)
    try:
        validate_config(cfg, resolver=default_resolver)
        # 設定已驗證過：直接組 parser，不再經 `build_wi_parser`（它會再驗一次、再查一次 DNS）
        parser = GuardedWiParser(
            AiServiceWiParser(AiServiceClient(cfg, resolver=default_resolver)),
            bundle_code=cfg.bundle_code,
            concurrency={"interactive": cfg.concurrency_interactive, "batch": cfg.concurrency_batch},
            per_user_per_minute=cfg.per_user_per_minute,
            daily_budget=cfg.daily_budget,
        )
    except AiServiceError as err:
        # 開關開了但設定不合格：記一次 WARNING（不含金鑰），整合停用，其他功能不受影響（ADR-037 D7）
        transient = err.kind in _TRANSIENT_KINDS
        logger.warning(
            "ai_service integration enabled but not usable%s; staying on rule_based: %s",
            f" (retry in {RETRY_AFTER_S:.0f}s)" if transient else "",
            err,
        )
        return _unavailable(err.kind, enabled=True, transient=transient)
    except Exception as exc:  # noqa: BLE001  任何非預期錯誤都不能讓 nl-draft（含 viewer 的 rule_based）變 500
        logger.error("ai_service integration failed to start (%s); staying on rule_based", type(exc).__name__)
        return _unavailable(AiServiceErrorKind.MISCONFIGURED, enabled=True, transient=True)
    return AiRuntime(parser=parser, enabled=True, available=True, service_bundle_code=cfg.bundle_code)


def _current() -> AiRuntime | None:
    rt = _runtime
    if rt is not None and rt.expires_at is not None and time.monotonic() >= rt.expires_at:
        return None
    return rt


def get_runtime() -> AiRuntime:
    """同步取得（會在呼叫端的執行緒做 I/O）。**async 程式碼請用 `get_runtime_async()`**。"""
    global _runtime
    rt = _current()
    if rt is not None:
        return rt
    with _lock:
        rt = _current()
        if rt is None:
            rt = _build()
            _runtime = rt
    return rt


async def get_runtime_async() -> AiRuntime:
    """async 路徑用：已建好就直接回（不切執行緒）；要建立時在執行緒裡做，不阻塞 event loop。"""
    rt = _current()
    if rt is not None:
        return rt
    return await asyncio.to_thread(get_runtime)


def warm_up() -> None:
    """app 啟動時呼叫（在執行緒裡）。失敗不影響啟動：結果一樣是「不可用」，之後的請求照常降級。"""
    rt = get_runtime()
    if rt.enabled:
        logger.warning(
            "ai_service integration %s (bundle=%s)", "available" if rt.available else "NOT available",
            rt.service_bundle_code or "-",
        )


def reset_for_tests(runtime: AiRuntime | None = None) -> None:
    """測試用：清掉單例（下次重新讀環境變數），或直接換成指定的 runtime。"""
    global _runtime
    with _lock:
        _runtime = runtime
