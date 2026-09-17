"""LB 回寫 client——`GET …/results/{r}/writeback`（ADR-036 D1／B3；契約 LB §8）。

例外分層**分層原則比照 `dsx_client`**（型別分離、雙層 timeout；不自創新語意）：連線失敗／逾時／總時限
逾時／5xx／其他非預期狀態 → `LbUnreachable`；4xx → `LbRequestFailed(status)`。log 帶原始狀態碼。
（dsx_client 對非 2xx 走 `raise_for_status()`；此處為了讓 4xx 與 5xx 走不同例外型別，改為顯式狀態碼分段，
行為對等：4xx→RequestFailed、5xx/3xx/其他→Unreachable。）

⚠️ 總時限：`httpx.AsyncClient(timeout=timeout_s)` 是單次操作逾時（connect/read/write/pool 各自計時，
非總時限）——外面再包 `asyncio.timeout(timeout_s)` 當總時限硬上限，逾時一律視同 `LbUnreachable`
（同 `dsx_client.query_distance` 的做法）。

ADR-036 D1：v1 直連、不經 gateway、預設不帶身分 header；`auth_header` 為日後掛 Traefik 預留
（設了才帶，值＝當前使用者員編），解析／資料模型／UI 屆時一律不動——認證只能是加法。
"""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class LbUnreachable(Exception):
    """LB 連線失敗、逾時，或回報 5xx 服務錯誤（呼叫端 → 502／504）。"""


class LbRequestFailed(Exception):
    """LB 回報 4xx（請求層問題，如座標不存在）。帶原始狀態碼。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"LB 回報請求失敗（HTTP {status_code}）：{detail}")


async def fetch_writeback(
    *,
    base_url: str,
    project_id: str,
    version_id: str,
    result_id: str,
    timeout_s: float,
    auth_header: tuple[str, str] | None = None,
) -> dict:
    """呼叫 LB writeback 端點，回原始 payload（dict）。

    URL：`{base_url}/api/v3/projects/{p}/versions/{v}/results/{r}/writeback`。
    """
    url = (
        f"{base_url.rstrip('/')}/api/v3/projects/{project_id}"
        f"/versions/{version_id}/results/{result_id}/writeback"
    )
    headers = {auth_header[0]: auth_header[1]} if auth_header else None
    try:
        async with asyncio.timeout(timeout_s):
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(url, headers=headers)
    except httpx.TransportError as exc:
        # TransportError 涵蓋連線失敗與逾時（TimeoutException 是其子類）——問不到。
        raise LbUnreachable(f"LB 連線失敗或逾時：{exc}") from exc
    except TimeoutError as exc:
        # asyncio.timeout 的總時限（httpx 逐段都沒超標但總耗時超過）。
        raise LbUnreachable(f"LB 總時限逾時（{timeout_s}s）：{exc}") from exc

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
