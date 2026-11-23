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
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _make_client(timeout_s: float) -> httpx.AsyncClient:
    """建立 httpx client。測試替換成接假 DSX（ASGI app）的 client；正式路徑不帶 transport。"""
    return httpx.AsyncClient(timeout=timeout_s)


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
            async with _make_client(timeout_s) as client:
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


# ════════ ADR-038 D5.3／D5.4（W7）：物件清單與座標快照 ════════

class DsxNotReady(Exception):
    """DSX 場景座標尚未就緒（3D Kit 還沒回報 placements）。與「連不到」分開回報（ADR-038 D5.4）。"""


# DSX 沒有認證，回應當不可信輸入：本文位元組、筆數、字串長度、座標範圍都有上限；超過就整份拒絕（不截斷：
# 截掉的物件會被誤判成「快照裡找不到」而清掉區域座標）。
MAX_DSX_BODY_BYTES = 2 * 1024 * 1024
MAX_DSX_OBJECTS = 2000
MAX_DSX_TEXT = 200
# 站內座標的合理範圍（公分）：一個工作站不會超過 ±10 公尺；也遠在 Numeric(10,2) 之內
MAX_ABS_COORD_CM = 1000.0
MAX_REVISION = 2**31 - 1

_PARSE_ERRORS = (AttributeError, KeyError, TypeError, ValueError, OverflowError, RecursionError)


@dataclass(frozen=True)
class DsxObject:
    id: str
    label_zh: str
    vocab_code: str | None
    visible: bool


@dataclass(frozen=True)
class DsxPlacement:
    """一個物件在站內局部座標的量測點（公分，原點＝作業員站位）。

    `point_source`：`anchor`＝DSX 的 `anchor_cm`（套用取放錨點後的量測點，優先）；`station_local`＝DSX 沒給
    `anchor_cm` 時退回物件原點的站內座標。記下來，事後才分得出每個距離是量到哪一點（ADR-038 D5.6(d)）。
    """

    object_id: str
    x: float
    y: float
    z: float
    point_source: str


@dataclass(frozen=True)
class DsxPlacements:
    station_id: str
    placement_revision: int
    placements: list[DsxPlacement]


async def _get_body(base_url: str, path: str, timeout_s: float) -> tuple[int, bytes]:
    """GET 並讀本文，超過 `MAX_DSX_BODY_BYTES` 就中止（不整個讀進記憶體）。"""
    url = f"{base_url.rstrip('/')}{path}"
    try:
        async with asyncio.timeout(timeout_s):
            async with _make_client(timeout_s) as client:
                async with client.stream("GET", url) as resp:
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_DSX_BODY_BYTES:
                            raise DsxUnreachable(f"DSX 回應超過 {MAX_DSX_BODY_BYTES} bytes")
                        chunks.append(chunk)
                    return resp.status_code, b"".join(chunks)
    except httpx.TransportError as exc:
        raise DsxUnreachable(f"DSX data-service 連線失敗或逾時：{type(exc).__name__}") from exc
    except TimeoutError as exc:
        raise DsxUnreachable(f"DSX data-service 總時限逾時（{timeout_s}s）") from exc


def _text(v: Any) -> str | None:
    """選填字串：空白、過長都當沒給。"""
    if v is None:
        return None
    s = str(v).strip()
    return s if s and len(s) <= MAX_DSX_TEXT else None


def _req_text(v: Any) -> str:
    s = _text(v)
    if s is None:
        raise ValueError("missing or oversized id")
    return s


def _coord(v: Any) -> float:
    f = float(v)
    if f != f or abs(f) > MAX_ABS_COORD_CM:
        raise ValueError("coordinate out of range")
    return f


def _bounded_list(v: Any) -> list:
    if not isinstance(v, list):
        raise TypeError("expected a list")
    if len(v) > MAX_DSX_OBJECTS:
        raise ValueError(f"more than {MAX_DSX_OBJECTS} items")
    return v


def _unique(ids: list[str]) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate object id")


async def list_objects(*, base_url: str, timeout_s: float) -> list[DsxObject]:
    """`GET /api/v1/objects`：給區域綁定的下拉用。看不懂或超過上限的回應視同連不到（`DsxUnreachable`）。"""
    status, body = await _get_body(base_url, "/api/v1/objects", timeout_s)
    if status != 200:
        raise DsxUnreachable(f"DSX data-service 回報非預期錯誤（HTTP {status}）")
    try:
        raw = _bounded_list(json.loads(body).get("objects") or [])
        out = [
            DsxObject(
                id=_req_text(o.get("id")),
                label_zh=_text(o.get("label_zh")) or _req_text(o.get("id")),
                vocab_code=_text(o.get("vocab_code")),
                visible=bool(o.get("visible", True)),
            )
            for o in raw
        ]
        _unique([o.id for o in out])
    except _PARSE_ERRORS as exc:
        raise DsxUnreachable(f"DSX 物件清單格式不符：{type(exc).__name__}") from exc
    return out


async def get_placements(*, base_url: str, timeout_s: float) -> DsxPlacements:
    """`GET /api/v1/placements`：同步座標用。`ready=false` 或 HTTP 409 → `DsxNotReady`。"""
    status, body = await _get_body(base_url, "/api/v1/placements", timeout_s)
    if status == 409:
        raise DsxNotReady("DSX 場景座標尚未就緒")
    if status != 200:
        raise DsxUnreachable(f"DSX data-service 回報非預期錯誤（HTTP {status}）")
    try:
        data = json.loads(body)
        if not data.get("ready", False):
            raise DsxNotReady("DSX 場景座標尚未就緒")
        out: list[DsxPlacement] = []
        for p in _bounded_list(data.get("placements") or []):
            anchor = p.get("anchor_cm")
            pt, source = (anchor, "anchor") if anchor is not None else (p["station_local_cm"], "station_local")
            out.append(DsxPlacement(object_id=_req_text(p.get("object_id")), x=_coord(pt["x"]), y=_coord(pt["y"]),
                                    z=_coord(pt["z"]), point_source=source))
        _unique([p.object_id for p in out])
        revision = int(data["placement_revision"])
        if not 0 <= revision <= MAX_REVISION:
            raise ValueError("placement_revision out of range")
        return DsxPlacements(station_id=_req_text(data.get("station_id")), placement_revision=revision, placements=out)
    except DsxNotReady:
        raise
    except _PARSE_ERRORS as exc:
        raise DsxUnreachable(f"DSX 擺放座標格式不符：{type(exc).__name__}") from exc
