# 領域索引：spatial-distance — 區域、DSX 座標快照、物件歸區與自動算距離

## 一句話
按 SKU 的標準工作站設區域、綁 DSX 物件、按「同步」存座標快照、把 WI 用到的物件歸區，再依區域座標算距離建議（ADR-038 D5）。

## 權威文件
- [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md) D5.1–D5.6（含 2026-11-23 修訂與 W7a 追記）
- [ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md)（proposed；採用其距離治理規則，不採用工位模型）
- 交付與驗收：[roadmap/adr-038-delivery-plan.md](../roadmap/adr-038-delivery-plan.md)〈W7a〉〈W7b〉〈W8〉

## 決策（相關 ADR）
- [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md) — 距離兩段式；MOST 是距離資料與計算的權威，DSX 是操作介面
- [ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md) — I1／I4／I5（引擎唯一時間權威、建議帶出處、不得靜默夾擠）

## 程式入口
- 路徑：`src/ddm_v2/services/v2/{zone_service,dsx_client}.py`、`src/ddm_v2/api/routes/v2/zone.py`、`src/ddm_v2/schemas/v2/zone.py`、`src/ddm_v2/models/v2/zone.py`、`migrations/versions_v2/v2_0054_sku_zones.py`
- graphify 錨點：`zone_service`、`sync_from_dsx`、`set_object_zones`、`worksheet_objects`、`dsx_client`

## 吃哪些欄位／狀態
- `zone_categories`（內建＋admin 新增）、`sku_zones`（中心座標只由同步寫入）、`sku_placement_snapshots`（每 SKU 留 20 份）、`sku_object_zones`（(SKU, work_vocab_item) → 區域）。
- 列上的 `object_vocab_id`／`from_vocab_id`／`to_vocab_id`／`tool_vocab_id`（「這份 WI 用到的物件」）。
- W7b 起：`wi_rows.distance_status`（W2）、`modeling_policy_versions.policy_json` 的距離設定。

## 不變量
見 `docs/agent-team/domains.yaml` domain `spatial-distance` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_zones.py`、`tests/unit/test_dsx_client_w7.py`。
- 缺口：算距離與建議（W7b）、畫面（W8）尚未實作；DSX 需確認事項見 W7b 產出的配合文件。
