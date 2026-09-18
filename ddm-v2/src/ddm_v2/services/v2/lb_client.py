"""LB 回寫 client——`GET …/results/{r}/writeback`（ADR-036 D1／B3；契約 LB §8）。

例外分層**分層原則比照 `dsx_client`**（型別分離、雙層 timeout）：**逾時（單次操作／總時限）→ `LbTimeout`**（呼叫端 504）；
連線失敗／5xx／其他非預期狀態 → `LbUnreachable`（呼叫端 502）；4xx → `LbRequestFailed(status)`。log 帶原始狀態碼。
`LbTimeout` 是 `LbUnreachable` 子類——既有「不可達即 502」的 except 不變，路由層先判 LbTimeout→504、再判 LbUnreachable→502。
（ADR-036 D7 維持 502／504：逾時以子類別分出；裁決見 ADR-036 §5。）

⚠️ 總時限：`httpx.AsyncClient(timeout=timeout_s)` 是單次操作逾時（connect/read/write/pool 各自計時，
非總時限）——外面再包 `asyncio.timeout(timeout_s)` 當總時限硬上限，逾時一律視同 `LbUnreachable`
（同 `dsx_client.query_distance` 的做法）。

ADR-036 D1（＋2026-09-18 追記）：v1 直連、不經 gateway；但 **LB 應用本身檢查身分 header**（真機驗證），
最小需求 `X-User-Id`＋`X-Plant-Code`＋`X-Username` 三個都要，缺任一 → 401。故 client 帶一組 header
（`headers` 參數；由 `DDM_LB_AUTH_HEADERS` 設定，值為固定字串或 `@me`＝當前使用者員編）。這仍是加法——
日後掛 Traefik 只換 base URL 與 header 值來源，解析／資料模型／UI 不動。401／403 → `LbAuthRequired`（提示設定 header）。
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

logger = logging.getLogger(__name__)

# 座標（project／version／result id）會直接成為 LB URL 的路徑段。只允許 [A-Za-z0-9_-]{1,64}：擋 `/`、`..`、
# 空白、控制字元、`%`（預先編碼的斜線）、`?`／`#` 等——否則可把請求改寫成 LB 主機上的任意路徑，並帶著身分
# header 發 GET。只做 URL 編碼不夠（仍可能打到別的路徑），所以擋在驗證。LB 實際格式（32 位 hex、UUID、
# `original`、`v_<hex>`）都在此集合內。路由層 `FetchIn` 用同一個 pattern 回 422；這裡是縱深防線。
# ⚠️ 只能給 pydantic（Rust regex）或 `fullmatch` 用：Python `re.match`／`search` 的 `$` 會放過結尾換行。
LB_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
_LB_ID_RE = re.compile(LB_ID_PATTERN)


class LbUnreachable(Exception):
    """LB 連不到（連線失敗）或回報 5xx／非預期狀態（呼叫端 → 502）。"""


class LbTimeout(LbUnreachable):
    """LB 逾時：單次操作逾時（`httpx.TimeoutException`）或總時限逾時（`asyncio.timeout`）（呼叫端 → 504）。

    是 `LbUnreachable` 的子類——既有「不可達即 502」的捕捉不變（LbTimeout is-a LbUnreachable），
    但路由層先判 LbTimeout → 504、再判 LbUnreachable → 502，讓「太慢/還在回」與「連不到」分開。
    """


class LbRequestFailed(Exception):
    """LB 回報 4xx（請求層問題，如座標不存在）。帶原始狀態碼。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"LB 回報請求失敗（HTTP {status_code}）：{detail}")


class LbAuthRequired(LbRequestFailed):
    """LB 回報 401／403：缺身分 header（ADR-036 D1 追記——LB 應用本身檢查 gateway 身分 header，
    最小需求 X-User-Id＋X-Plant-Code＋X-Username 三個都要）。呼叫端 → 明確提示設定 DDM_LB_AUTH_HEADERS。"""


async def fetch_writeback(
    *,
    base_url: str,
    project_id: str,
    version_id: str,
    result_id: str,
    timeout_s: float,
    headers: dict[str, str] | None = None,
) -> dict:
    """呼叫 LB writeback 端點，回原始 payload（dict）。

    URL：`{base_url}/api/v3/projects/{p}/versions/{v}/results/{r}/writeback`。
    headers：身分 header 一組（ADR-036 D1 追記；LB 最小需求 X-User-Id/X-Plant-Code/X-Username）。
    座標不合 `LB_ID_PATTERN` → `ValueError`，不發任何請求（路由層應已先擋成 422；到這裡代表呼叫端漏驗）。
    """
    for name, value in (("project_id", project_id), ("version_id", version_id), ("result_id", result_id)):
        if not _LB_ID_RE.fullmatch(value):
            raise ValueError(f"LB 座標 {name} 格式不合法（只允許 [A-Za-z0-9_-]，1–64 字元）")
    url = (
        f"{base_url.rstrip('/')}/api/v3/projects/{project_id}"
        f"/versions/{version_id}/results/{result_id}/writeback"
    )
    try:
        async with asyncio.timeout(timeout_s):
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url, headers=headers or None)
    except httpx.TimeoutException as exc:
        # 單次操作逾時（connect/read/write/pool）——LB 還在回或太慢。TimeoutException 是 TransportError
        # 的子類，必須先於 TransportError 捕捉。→ 504。
        raise LbTimeout(f"LB 逾時（單次操作 {timeout_s}s）：{exc}") from exc
    except httpx.TransportError as exc:
        # 其餘 TransportError＝連線失敗（ConnectError/NetworkError）——連不到。→ 502。
        raise LbUnreachable(f"LB 連線失敗：{exc}") from exc
    except TimeoutError as exc:
        # asyncio.timeout 的總時限（httpx 逐段都沒超標但總耗時超過）——LB 太慢。→ 504。
        raise LbTimeout(f"LB 總時限逾時（{timeout_s}s）：{exc}") from exc

    if resp.status_code in (401, 403):
        logger.warning("LB writeback 缺身分 header（HTTP %s）：%s", resp.status_code, resp.text)
        raise LbAuthRequired(resp.status_code, resp.text)
    if 400 <= resp.status_code < 500:
        logger.warning("LB writeback 請求失敗（HTTP %s）：%s", resp.status_code, resp.text)
        raise LbRequestFailed(resp.status_code, resp.text)
    if resp.status_code >= 500:
        logger.warning("LB writeback 服務錯誤（HTTP %s）：%s", resp.status_code, resp.text)
        raise LbUnreachable(f"LB 回報服務錯誤（HTTP {resp.status_code}）：{resp.text}")
    if resp.status_code >= 300:
        # 3xx（httpx 預設不自動跟隨）等非預期狀態：視同服務端問題，不落到 resp.json()。
        logger.warning("LB writeback 非預期狀態（HTTP %s）：%s", resp.status_code, resp.text)
        raise LbUnreachable(f"LB 回報非預期狀態（HTTP {resp.status_code}）：{resp.text}")

    return resp.json()
