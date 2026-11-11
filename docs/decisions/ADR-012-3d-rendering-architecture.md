# ADR-012: 3D 動作/組裝模擬的渲染架構

**狀態：** accepted
**日期：** 2026-06-21
**關聯：** [3d-simulation skill]、[../architecture/system-architecture-v2-spec.md](../architecture/system-architecture-v2-spec.md)、[ADR-011-schema-evolution-and-contract-stability.md](ADR-011-schema-evolution-and-contract-stability.md)

## 脈絡

Phase 3/4 要做 **3D 動作/組裝模擬**（動作 motion / 器具 tools / 機械 machines），3D 內容**由 Unreal 產生**。需決定：Unreal 的 3D 如何送到使用者眼前、MOST 資料如何驅動它。
限制與偏好（User 2026-06-21）：**優先低成本/易擴展**；「工具內視覺化理解」與「高擬真模擬」**兩者都想要**（主次尚在思考）。

## 決策

以 **A：Web 3D 資產管線** 為**基礎架構**：
- Unreal 當**製作工具**，匯出模型/動畫（glTF）為資產。
- **Web（Three.js/Babylon 類）在瀏覽器渲染**，呈現於 **workbench 內的新「3D」分頁**。
- 由 MOST 的 cycle 序列 + **權威秒數**驅動動畫（播放長度對齊 `total_seconds`）。
- 資產對應：`詞彙(物件/器具/機械) → 3D 模型`、`cycle/動作 → 動畫`。

**B：Pixel Streaming** 保留為**未來可選的高擬真模式**（不現在實作）。關鍵：A 與 B **吃同一份資料合約**（工序序列 + 時間 + 群組/約束），只有「誰渲染」不同 → 之後對特定高擬真情境加 B，不需重做核心。

## 考慮過的選項

- **A. Web 3D 資產管線（選定）** — 低成本、易擴展、內嵌 workbench、任何瀏覽器可看；代價：擬真度較 Unreal 原生低、需建資產匯出管線與對應表。**符合「低成本/易擴展優先」**。
- **B. Pixel Streaming** — 完整 Unreal 擬真，但每個同時使用者需一顆 GPU、貴、延遲、擴展成本高。→ **延後為可選高擬真模式**。
- **C. 獨立 Unreal 桌面程式** — 完整能力但不在瀏覽器、需安裝散佈、與 workbench 整合弱、兩套程式。→ **不選**。

## 後果

- **資料模型（加法）**：需 `詞彙→模型`、`cycle/範本→動畫` 的對應（如 `work_vocab_items.model_ref`、`motion_templates.animation_ref`，或獨立 `asset_manifest` 表）。屬加法 migration，符合 ADR-011。
- **時間對齊**：動畫長度依 MOST 權威 `total_seconds`，維持單一真相（3D 不自定義工時）。
- **管線**：Unreal → glTF(含動畫) → 靜態/物件儲存 → web 依 asset ref 載入；需資產版本管理。
- **架構契合**：3D 是 API/合約的**消費者**，不新增第二引擎；Unreal 資產經**防腐層**（asset manifest）對應內部模型 → 符合 hexagonal/ports-adapters。
- **前端**：workbench 加 3D 分頁（WebGL canvas）；建議 lazy-load，避免拖累主頁。
- **保留 B 的路**：選 A 不排除未來加 Pixel Streaming（合約相同）。
- **風險**：glTF 擬真度低於 Unreal 原生；資產↔詞彙/cycle 對應需保持同步；複雜場景的 WebGL 效能。

## 尚待後續決（不影響本架構決策）

資產檔格式細節與儲存位置（靜態 dir vs 物件儲存 vs CDN）、動畫與七格時序的精確對齊方式、資產版本/命名約定 — 於 Phase 3/4 實作前再定（可各自小決策或補 ADR）。
