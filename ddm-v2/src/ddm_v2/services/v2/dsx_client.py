"""DSX data-service client——a3 距離查詢（DSX 整合 API 契約 v2 §3.1；ADR-031 I1／I4／I5）。

呼叫 `POST {base_url}/api/v1/distance {from_id, to_id}`（DSX 物件 id，非 vocab UUID）。
**不用** `/sentence/resolve`——那支連 a0/a6 一起算，MVP 只做 a3（見契約 §0.2）。

I1：本模組不得計算 TMU／band index，也不得為了顯示方便先幫忙分帶或四捨五入——
`DsxDistanceResult.raw` 原樣保留 DSX 回應，供上層原封不動存進 `wi_row_dsx_suggestions.dsx_response`。

I5：連線失敗／逾時（`DsxUnreachable`）與「查無此物件」（`DsxObjectNotFound`）是兩種不同的
異常型別，呼叫端不得把兩者混在一起回報，否則使用者無法分辨是服務連不上還是這個物件組合
真的沒有 3D 資料。

⚠️ 總時限：`httpx.AsyncClient(timeout=timeout_s)` 的 `timeout_s` 是**單次操作**逾時
（connect/read/write/pool 各自計時，不是總時限）——伺服器只要在每個時間窗內送一點資料，
理論上可以讓單一請求無限期佔住呼叫端的 DB session（`dsx_service.get_a3_distance` 呼叫本函式
時 session 仍 checkout 著）。外面再包一層 `asyncio.timeout(timeout_s)` 當總時限硬上限，
逾時一律視同連線失敗（`DsxUnreachable`），不管 httpx 內部是卡在哪個階段。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DsxUnreachable(Exception):
    """DSX data-service 連線失敗、逾時，或回報非預期的服務錯誤（非 404/409）。"""


class DsxObjectNotFound(Exception):
    """DSX 回報查無此物件座標。

    涵蓋兩種 DSX 端狀態，本模組刻意合併為同一個例外（詳見模組內 `query_distance`
    docstring 的 ⚠ 說明）：
    - HTTP 404：`from_id`／`to_id` 任一在該場景沒有已知座標。
    - HTTP 409：場景座標尚未就緒（3D Kit 還沒回報 placements）。
    """


@dataclass(frozen=True)
class DsxDistanceResult:
    """對應 DSX `DistanceResult`（schema.py）。`raw` 是 DSX 回應原樣，未經任何轉換。

    `horizontal_cm`／`vertical_cm`：DSX 回應本來就有的水平／垂直分量（ASlot 架構上
    `reach_cm`／`foot_cm` 可同時有值，見 `_a_tmu` 取 max 而非互斥）。本模組只原樣多傳
    一份，**不**在這裡判斷該填哪個欄位——那是 ADR-031 P1 未定案的範圍。DSX 若未提供
    （舊版 DSX 或這組物件沒有分量資料）則為 `None`，不得假設一定存在。
    """

    distance_cm: float
    provisional: bool
    measure_from_mode: str
    warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    horizontal_cm: float | None = None
    vertical_cm: float | None = None


async def query_distance(
    *, base_url: str, from_id: str, to_id: str, timeout_s: float
) -> DsxDistanceResult:
    """查詢 DSX 兩物件間的直線距離。

    ⚠️ 契約落差（2026-08-24 對照 DSX 原始碼 `app.py::distance` 發現，DSX 整合 API 契約
    草案 v2 §3.1 的 `reason` 枚舉只有三種，未涵蓋這個狀態）：DSX 對「場景座標尚未就緒」
    回 HTTP 409（`STORE.placements_ready()` 為 false），語意上不是「查無此物件」而是
    「服務還沒準備好」。契約沒有第四種 reason 可用，這裡先併入 `DsxObjectNotFound`
    （對 IE 而言效果相近：這個組合現在算不出建議值），但用 WARNING log 保留原始
    status code，不在伺服器端也靜默混淆——這是本函式能做到的最大誠實度，是否要在
    契約加第四個 reason（例如 `dsx_not_ready`）留給下一輪決定。
    """
    url = f"{base_url.rstrip('/')}/api/v1/distance"
    try:
        async with asyncio.timeout(timeout_s):
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(url, json={"from_id": from_id, "to_id": to_id})
    except httpx.TransportError as exc:
        # TransportError 涵蓋連線失敗（ConnectError/NetworkError）與逾時（TimeoutException
        # 是 TransportError 的子類）——兩者對呼叫端的意義相同：問不到、不是「查無此物件」。
        raise DsxUnreachable(f"DSX data-service 連線失敗或逾時：{exc}") from exc
    except TimeoutError as exc:
        # asyncio.timeout 的總時限——httpx 逐段計時都沒超標，但總耗時超過 timeout_s
        # （例如伺服器分段慢速回應，每段都小於單次操作逾時）。
        raise DsxUnreachable(f"DSX data-service 總時限逾時（{timeout_s}s）：{exc}") from exc

    if resp.status_code == 404:
        raise DsxObjectNotFound(f"DSX 查無此物件座標（HTTP 404）：{resp.text}")
    if resp.status_code == 409:
        logger.warning(
            "DSX 場景座標尚未就緒（HTTP 409，from_id=%s to_id=%s）：%s", from_id, to_id, resp.text
        )
        raise DsxObjectNotFound(f"DSX 場景座標尚未就緒（HTTP 409）：{resp.text}")
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise DsxUnreachable(
            f"DSX data-service 回報非預期錯誤（HTTP {resp.status_code}）：{resp.text}"
        ) from exc

    data = resp.json()
    return DsxDistanceResult(
        distance_cm=float(data["distance_cm"]),
        provisional=bool(data.get("provisional", True)),
        measure_from_mode=str(data.get("measure_from_mode", "")),
        warnings=list(data.get("warnings") or []),
        raw=data,
        horizontal_cm=_safe_component_float(data.get("horizontal_cm"), field="horizontal_cm"),
        vertical_cm=_safe_component_float(data.get("vertical_cm"), field="vertical_cm"),
    )


def _safe_component_float(value: Any, *, field: str) -> float | None:
    """`horizontal_cm`／`vertical_cm` 是附屬參考欄位，不是查詢成功與否的判準。

    `distance_cm` 轉換失敗要嚴格拋錯（見上方 `float(data["distance_cm"])`）——那是必要
    欄位。這兩個分量欄位若格式異常（非數字字串、None 以外的怪值），不該讓整筆原本能
    成功的查詢被 `dsx_service` 的 except 區塊接住、誤判為 `dsx_unreachable`。轉不動就當
    沒給，記一行 WARNING 供除錯，不往外拋。
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("DSX 回應的 %s 無法轉換為數字，視同未提供：%r", field, value)
        return None
