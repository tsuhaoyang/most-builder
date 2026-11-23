# 領域索引：spatial-distance — 區域、DSX 座標快照、物件歸區與自動算距離

## 一句話
按 SKU 的標準工作站設區域、綁 DSX 物件、按「同步」存座標快照、把 WI 用到的物件歸區，再依區域座標算距離建議（ADR-038 D5）。

## 權威文件
- [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md) D5.1–D5.6、D6（含 2026-11-23 修訂與 W7a、W7b 追記）
- [ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md)（proposed；採用其距離治理規則，不採用工位模型）
- 交付與驗收：[roadmap/adr-038-delivery-plan.md](../roadmap/adr-038-delivery-plan.md)〈W7a〉〈W7b〉〈W8〉

## 決策（相關 ADR）
- [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md) — 距離兩段式；MOST 是距離資料與計算的權威，DSX 是操作介面
- [ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md) — I1／I4／I5（引擎唯一時間權威、建議帶出處、不得靜默夾擠）

## 程式入口
- 路徑：`src/ddm_v2/services/v2/{zone_service,dsx_client}.py`、`src/ddm_v2/api/routes/v2/zone.py`、`src/ddm_v2/schemas/v2/zone.py`、`src/ddm_v2/models/v2/zone.py`、`migrations/versions_v2/v2_0054_sku_zones.py`
- W7b：`src/ddm_v2/services/v2/{distance_service,policy_service}.py`、`src/ddm_v2/api/routes/v2/distance.py`（檔頭列出 5 個端點）、`src/ddm_v2/schemas/v2/distance.py`、`src/ddm_v2/models/v2/distance.py`、`migrations/versions_v2/v2_0055_distance_suggestions.py`
- graphify 錨點：`zone_service`、`sync_from_dsx`、`set_object_zones`、`worksheet_objects`、`dsx_client`

## 吃哪些欄位／狀態
- `zone_categories`（內建＋admin 新增）、`sku_zones`（中心座標只由同步寫入）、`sku_placement_snapshots`（每 SKU 留 20 份）、`sku_object_zones`（(SKU, work_vocab_item) → 區域）。
- 列上的 `object_vocab_id`／`from_vocab_id`／`to_vocab_id`／`tool_vocab_id`（「這份 WI 用到的物件」）。
- W7b：`wi_row_distance_suggestions`（一列一格 a0／a3／m3／a6）、`modeling_policy_defaults`（新建工時表的建模政策版本）、`modeling_policy_versions.policy_json["distance"]`（門檻、人端偏移；沒有時用凍結的 `DEFAULT_DISTANCE_SETTINGS`）、`wi_rows.distance_status`（W2；套用後 `confirmed`，存檔時距離內容變了會退回）。

## 不變量
見 `docs/agent-team/domains.yaml` domain `spatial-distance` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_zones.py`、`tests/unit/test_dsx_client_w7.py`、`tests/integration/test_distance_suggestions.py`、`tests/unit/test_distance_suggest.py`。
- 缺口：
  - 畫面（W8）尚未實作。
  - 距離設定沒有「指回舊版」的路徑、沒有獨立稽核表、既有工時表不能改用新版本。
  - 重新同步 DSX 後，已 `confirmed` 的列不自動退回，也還沒有畫面提示「已確認的距離與新座標不同」。
  - DSX 方需確認的事項見 [dsx-changes-for-adr-038.md](../architecture/dsx-changes-for-adr-038.md)（待 DSX 回覆，特別是 `anchor_cm` 是否已含旋轉與人端偏移）。
  - a6 的 DSX 實測風險（終點幾何中心造成全落 A24）改用區域中心後預期改善，但**未實測**。
