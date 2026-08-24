# DSX 整合 API 契約草案（MVP，v2）

**狀態：** ⏳ 草案——先建 MVP、邊做邊調（User 2026-08-24 裁決，不卡在 ADR-031 正式核可才動工）
**日期：** 2026-08-24（v2，取代同日 v1——v1 假設「DSX push 給 MOST」的方向錯誤，見 §0.1）
**關聯：**
[ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md)（proposed，距離治理規則 D4／I1／I5／I4 本文直接沿用）、
[ADR-012](../decisions/ADR-012-3d-rendering-architecture.md)（3D 動畫播放，與本文不同功能，pending 不動）、
[ADR-011](../decisions/ADR-011-schema-evolution-and-contract-stability.md)（加法 migration）、
DSX 側對接文件（`/home/howard/workspace/dsx_ai_factory/team_docs/most/02-most-integration-contract.md`、`03-open-questions.md`——**這兩份是 DSX 那個 session 已經對照本 repo 原始碼查證寫死的，優先度高於本文的推測**）

---

## 0. 這版改了什麼（對照 v1）

### 0.1 方向錯誤，已更正

v1 設計「DSX 算完推給 MOST」（`POST /api/v2/dsx/scenes/{id}/placements`）。實際上 DSX 那邊已經做了**反方向**且已查證可行的整合：DSX 主動呼叫 MOST **既有**的 `POST /api/v2/minimost/calculate`（`CycleIn` 形狀已對照 `schemas/v2/most.py` 寫死，我核對過 `ASlot`／`CycleIn` 欄位一致）。**這條路徑不需要 MOST 新建任何端點**，只是 DSX 端目前 `most_api.enabled: false`（因為 ddm-v2 空間模組還沒做）。

但這條路徑解決的是「DSX 自己算完、自己顯示 TMU」，**不是**使用者最初要的「回到 MOST 工作台選工具、看到建議值」。兩者互不衝突、可以並存，本文只管後者。

### 0.2 範圍縮小：只做 a3（物件↔物件移動），不做 a0／a6

DSX 側對這個場景做了實測：人↔物件距離（`a0` 取得、`a6` 返回會用到）**8 個物件全部落在 A24 溢位帶，完全沒有鑑別度**——量測錯點（ADR-031 P4，目前用 bbox 中心而非取放錨點）與人體基準（P10，肩高 140cm 是隨便估的，未經 IE 確認）兩個待決參數同時開著。

**User 裁決（2026-08-24）**：MVP **先只做 a3**（`from_location` → `destination` 的物件間移動距離）。這段不碰人端基準，DSX 側評為「大致可用」，只受 P4 影響（效果有限）。a0／a6 留給 P4／P10 定案後的下一輪。

⚠️ **a3 仍然沒有逃開 P1**（伸手／腳步分界閾值未定——引擎的 `a3` 同時接受 `reach_cm` 與 `foot_cm`，取 `max()`）。MVP 依然**不自動分類**，只顯示原始公分數字，由 IE 手動選要填哪一格。這條原則 v1 就定了，v2 不變。

---

## 1. 範圍界定

### 1.1 這份契約管什麼

使用者在 MOST 工作台編輯某一列（`WiRow`）、指定了 `from_vocab_id`（從哪裡）與 `to_vocab_id`（到哪裡）之後，若這兩個詞彙項在 DSX 場景裡都有登記座標，系統主動向 DSX 查詢兩者間的直線距離，顯示為**建議值**（帶 `provisional` 徽章與出處），IE 手動選歸入 `a3.reach_cm` 還是 `a3.foot_cm`，走既有 cycle 表單存檔即完成確認。

### 1.2 這份契約刻意不做什麼

- **不做 a0／a6**（見 §0.2）
- **不做 CM 序列**——DSX 側已經評估過：CM 的 `distance_cm` 語意跟 GM 的 `a3` 不同，且 M 階梯 >75cm 是錯誤不是飽和，硬套會送出語意錯誤的 payload。這個判斷合理，本文沿用，MVP 只管 GM
- **不建 ADR-031 Phase A 的完整 `stations`／`object_placements`**——理由同 v1：DSX 是編輯與真相來源，MOST 不需要再造一套管理介面。但 v2 比 v1 更進一步簡化：**目前只有一個場景**（DSX 側的 `GB_HDD_SingleStation.usd`，「MOST 單站情境」），MVP 甚至不需要「場景」這個實體——用一個環境變數指向 DSX data-service 的位置即可，多場景是之後的事
- **不解決座標權威歸屬**（DSX 側 A1 提出的問題：`object_placements` 的權威來源是 ddm-v2 還是 USD？）——這題本文不決定，MVP 每次即時查詢 DSX 的即時狀態，不在 MOST 側落地儲存座標本身，只存**查詢結果與出處**（見 §2）

### 1.3 沿用的硬性不變式（ADR-031，DSX 側 `02-most-integration-contract.md` 已同步遵守）

- **I1**：DSX 只能送公分數字，不得算 TMU／band index
- **D4**：DSX 的距離是建議，IE 未確認前不影響 `slot_inputs`
- **I5**：距離超出引擎範圍時顯示「需 IE 裁決」，不 clamp、不歸零
- **I4**：建議值必須帶完整出處，無出處不得顯示——DSX 回應已經帶 `station_id`／`placement_revision`／`measure_from_mode`／`warnings[]`，MOST 端原樣轉存

---

## 2. 資料模型

### 2.1 不需要新表存座標本身（見 §1.2）

### 2.2 ⚠️ 更正（2026-08-24）：不能重用 `wi_row_contexts`，需要一張新表

v1/v2 前一版都寫「`wi_row_contexts` 既有表，`source='system'` 已支援，不需要 migration」——**這個判斷錯了，只查了 ADR-031 的散文描述，沒有實際核對表的 pydantic schema**。實際查證（`schemas/v2/wi_context.py`）：

- `SUPPORTED_SCHEMA_VERSIONS = frozenset({"wi-context-v1"})`——**目前只接受這一個 schema_version**，寫入 `"dsx-a3-suggestion-v1"` 會被 `validate_context_payload` 直接拒絕（`ValueError: unsupported schema_version`），不是「風險」，是**直接炸掉**。
- `WiContextDataV1` 是 `extra="forbid"` 的固定欄位集（`quality_checks`／`safety_notes`／`tool_settings`／`machine_refs`／`visual_refs`／`sop_refs`／`business_tags`）——這張表的實際用途是**品保/安全/工具設定備註**，跟距離建議的出處完全是不同領域。
- `wi_context_service.upsert_context` 是**整列覆蓋**（`UniqueConstraint(wi_row_id)`，一列只能有一筆 context，寫入會取代整個 `schema_version`／`context_data`／`source`）——就算硬塞一個新 schema_version 進去，IE 手動編輯 `safety_notes` 時若沒有把 DSX 建議一起帶回寫，會**靜默清掉**這筆建議。這正是本 repo 記憶體庫已經踩過的形狀（聚合欄位被不同來源覆蓋）。

**修正：新增一張小表 `wi_row_dsx_suggestions`**，不與既有的品保/安全 context 共用同一列：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | uuid pk | |
| `wi_row_id` | uuid, FK→`wi_rows.id`, `ondelete=CASCADE` | |
| `a_slot_key` | text, check ∈ (`a3`) | 這筆建議對應哪個 A 格——MVP 只會出現 `a3`，但先把欄位開好，`a0`／`a6`（見 §6）解禁後不必改表 |
| `from_vocab_id` / `to_vocab_id` | uuid, FK→`work_vocab_items.id` | |
| `raw_distance_cm` | numeric | |
| `dsx_response` | jsonb | DSX 回應**原樣保存**，不做任何轉換或取整——I1 的邊界 MOST 端也要守：不能因為顯示方便就先幫忙分帶或四捨五入 |
| `queried_at` | timestamptz | |
| `ie_action` | text, nullable | `"accepted_as_reach" \| "accepted_as_foot" \| "overridden" \| "dismissed"`——加分項非 MVP 必須（ADR-031 R5：追蹤採用率／改值率） |
| `created_at`/`updated_at` | TimestampMixin | |

`UniqueConstraint(wi_row_id, a_slot_key)`——同一列同一個 A 格只留最新一筆查詢結果，upsert 語意。

**Migration 落在 `migrations/versions_v2/`**（比照既有 `v2_0034_wi_row_contexts.py` 的慣例），純加法，不動任何既有表。

### 2.3 `work_vocab_items.external_code`（既有欄位，不需 migration）——mapping 落在 MOST 端（User 2026-08-24 裁決，取代前一版的「MOST 定 canonical 碼」）

**不要求 DSX 改 `config.yaml` 對齊、不等 IE 定案命名**——MOST 直接把 `external_code` 設成 **DSX 目前實際在用的物件 id**（例如 `"tool_01"`、`"bin_white"`，即 DSX `02-most-integration-contract.md` §6 講的 `data-service/config.yaml` 裡 `objects[].id`；DSX 現有的 `vocab_code` 佔位碼可以無視，不必等它變「最終值」）。這樣：

- **不再需要查詢時的額外解析**（原本設計的「`external_code`→查 DSX vocab 列表→拿物件 id」兩步，因為 `external_code` 直接就是物件 id，省了一次 API 呼叫）
- **mapping 的維護責任在 MOST**：DSX 那邊物件 id 若改了（例如場景重建），由 MOST 這邊更新對應的 `work_vocab_items.external_code`，不需要 DSX 配合改任何東西——這正是 User 裁決「代碼先用 mapping 做在 MOST 端」的意思：耦合面收斂到我們自己控制的一張欄位
- 仍然是一筆**資料準備工作，不需要等 API 開發**：在 `work_vocab_items` 建這個場景對應的 9 個列（`kind` 依 DSX 場景給的 `from`／`to`／`tool` 分類），`external_code` 填 DSX 目前的物件 id。在此之前，§3 的端點對 DSX 側查不到任何真實物件

### 2.4 查詢鍵：直接查表，不再需要額外解析（因 §2.3 的決定而簡化）

`POST /api/v1/distance {from_id, to_id}` 吃 DSX 物件 id（DSX 側 2026-08-24 已確認）。因為 §2.3 讓 `work_vocab_items.external_code` 就是這個 id 本身，MOST 的 client 只需要一次直查：`from_vocab_id`（MOST uuid）→ `work_vocab_items.external_code` → 直接當 `/distance` 的 `from_id` 用，不需要額外呼叫 DSX 的 vocab 列表。

---

## 3. API 端點（MOST 新增，MOST 是呼叫方）

### 3.1 `POST /api/v2/dsx/a3-distance` — 查詢 from/to 兩點間的直線距離

**人類使用者觸發，`require_role("analyst")`**（2026-08-24 checkpoint 修正：草稿原寫 `current_user`，實作時發現這是寫入端點——`wi_row_id` 有值時會 upsert `wi_row_dsx_suggestions`——比照 `wi_context.py` 的既有慣例升級為 analyst 門檻，並加上版本凍結檢查，見 §5）。MOST 是呼叫方，內部先做 §2.4 的查表（`vocab_id`→`external_code`，即 DSX 物件 id），再呼叫 DSX 的 `POST /api/v1/distance`（**不用** `/sentence/resolve`——DSX 側建議：後者會連 a0/a6 一起算，MVP 用不到，`distance` 端點乾淨很多）。

**⚠️ 掛載點更正（2026-08-24，實作中發現）**：原以為的掛載點 `WiItemInspector.tsx`（`workbench-v3/`）編輯的其實是動作模組模板列（`motion_module_versions.rows` JSONB 陣列的元素），**永遠不會有真實 `wi_rows` 記錄的 UUID**——不是暫時沒有，是這個畫面的資料模型本來就不可能有。真正持有真實 `WiRow` 的地方是 `WiWorkbench.tsx` 既有的 a3/from/to 建立器面板；但那裡組的是**尚未存檔**的新列（`id` 只存在瀏覽器端，使用者按「儲存」後才真正寫進 `wi_rows` 表）。**掛載點改為 `WiWorkbench.tsx` 的建立器面板**，並連帶把 `wi_row_id` 從必填改為選填（見下）。

```
Request:
  { "wi_row_id": "<uuid, optional>", "from_vocab_id": "<uuid>", "to_vocab_id": "<uuid>" }

Response 200（兩者都有 DSX 對照碼且查得到）:
  {
    "available": true,
    "distance_cm": 42.0,
    "horizontal_cm": 38.0,
    "vertical_cm": 17.0,
    "provisional": true,
    "measure_from_mode": "...",
    "warnings": ["..."],
    "queried_at": "2026-08-24T13:05:00Z"
  }
```

`horizontal_cm`／`vertical_cm`（2026-08-24 checkpoint 新增）：DSX 回應本來就有這兩個分量，草稿設計時漏接。**MOST 不對這兩個分量做任何拆解判斷**（P1「伸手/腳步分界規則」仍未定案）——純被動傳遞，前端顯示成「僅供參考，非系統自動拆分建議」，DSX 未提供或格式異常時是 `null`，**不影響 `distance_cm` 本身查詢成功與否**（見 §5.2）。

```

Response 200（任一 vocab 沒有 external_code，或 DSX 查無此物件）:
  { "available": false, "reason": "vocab_not_mapped" | "dsx_object_not_found" | "dsx_unreachable" | "integration_disabled" }
```

**`wi_row_id` 選填，這是本 MVP 唯一接受的已知代價（User 2026-08-24 裁決）**：帶了就寫一筆 §2.2 的 `wi_row_dsx_suggestions` 快照（upsert，鍵是 `(wi_row_id, a_slot_key)`）；沒帶（組新列、尚未存檔時的絕大多數查詢）就只回查詢結果，**不寫出處快照**。D4／I1／I5 三條不變式不受影響——沒有任何東西會自動寫進 `slot_inputs`，使用者仍要手動選填、走既有存檔流程；少的只是「這筆建議當初從哪查來的」這筆稽核紀錄，僅限「尚未存檔」這個情境（見 §6）。

**已知後果（DSX 側 409「場景座標尚未就緒」目前併入 `dsx_object_not_found`）**：實作時發現 DSX 對「場景座標還沒同步好」回 HTTP 409，這個狀態契約沒有涵蓋，暫時映成 `dsx_object_not_found`（伺服器端有 log 保留原始 409，不混淆）。使用者看到的訊息因此在這種情況下會說「查無此物件」，而不是更準確的「場景還沒同步好，稍後再試」——這是已知的訊息不夠精準，非阻擋項，未來若要更精準需要契約加第五種 reason。

`dsx_unreachable`——DSX data-service 若離線／逾時，**明確回報，不得偽裝成「沒有建議值可用」**（那會讓使用者以為這個位置組合本來就沒有 3D 資料，而不是服務暫時連不上）。

### 3.2 沒有新的「確認」端點（沿用 v1 §3.4 的設計，理由不變）

前端把 §3.1 回傳的 `distance_cm` 預填進既有 cycle 表單的 `a3.reach_cm` 或 `a3.foot_cm`（使用者手動選，不自動分類），顯示 `provisional` 徽章。使用者按既有的儲存鍵，走既有的 `POST` cycle 端點，`slot_inputs` 落值。**不新建 accept/reject 邏輯。**

---

## 4. 流程圖（文字版）

```
1. 使用者在 WiWorkbench.tsx 的建立器面板組一筆新列，設定 from_vocab_id／to_vocab_id
   （此時這筆列通常尚未存檔，wi_row_id 只存在瀏覽器端）

2. 前端偵測兩者皆已設定 → 呼叫 POST /api/v2/dsx/a3-distance（不帶 wi_row_id）
   → MOST 後端向 DSX data-service 查詢（新 client 模組，方向對稱於 DSX 的 most_client.py）
   → 顯示「建議距離 42cm（DSX 暫定值，量測方式：...）」，不寫出處快照

3. 使用者手動選：這段填 a3 的 reach 還是 foot
   → 填入既有 cycle 表單 → 按儲存 → 走既有 POST worksheet 端點
   → slot_inputs 落值，此時才是「確認」完成
```

---

## 5. 已解決（DSX 側 2026-08-24 回覆，逐項核對過原始碼）

| # | 問題 | 答案 |
|---|---|---|
| 1 | `/distance` 吃哪種 id | DSX 物件 id（見 §2.4），且用 `/distance` 不用 `/sentence/resolve` |
| 3 | `external_code` 由誰定 | **mapping 落在 MOST 端**（見 §2.3，User 2026-08-24 裁決）——`external_code` 直接填 DSX 目前的物件 id，不等 IE 命名、不要求 DSX 對齊改檔 |
| 4 | `component` 要不要管 | 不需要，`DistanceQuery` 只有 `from_id`／`to_id` 兩個欄位 |

## 5.1 認證方式（User 2026-08-24 裁決）

DSX data-service **目前零認證**（`network_mode: host`，dev port 8023，`allow_origins=["*"]`，這台機器 `172.32.3.60` 同時是 Nucleus 的 IP）。

**裁決：兩邊都在內網，MVP 先走 IP 形式即可，不加認證層。** MOST 的 client 模組直接以 IP／內網位址呼叫 DSX data-service。**這不是永久結論**——一旦有跨內網段、對外暴露、或非受信任來源可觸及這個 API 的情境，需要重新評估（比照 CLAUDE.md 對 `preview_server.py` 的既有態度：只綁 loopback／內網時零認證可接受，一旦連得到的人變多就不再成立）。MOST 端仍建議比照 `DDM_WI_AI_ENABLED` 模式加一個功能開關（預設關閉），理由不是認證，是**變更管理**——這個查詢會打外部系統，開關能讓部署環境明確知道這條路徑有沒有被啟用。

## 5.2 第二輪 checkpoint（DSX 3D iframe 入口＋分量顯示，2026-08-24）

在第一輪 checkpoint（§5／§5.1，a3 距離查詢核心）通過並修正之後，追加兩個功能：①「DSX 3D 擺放介面」iframe 入口（`GET /api/v2/dsx/ui-url`＋前端 modal）②把 DSX 回應本來就有、先前設計時漏接的 `horizontal_cm`／`vertical_cm` 補進 `A3DistanceOut`，並依 User 裁決把「填入伸手／填入腳步」的互斥限制拿掉（MOST 引擎 `ASlot` 架構上允許兩者同時有值，`_a_tmu` 取 `max()` 不是相加）。這兩個功能追加後再跑一輪 code-reviewer／security-reviewer／test-engineer，修正結果：

**已修**：
- iframe 補 `sandbox="allow-scripts allow-same-origin"`／`allow="autoplay; fullscreen"`／`referrerPolicy="no-referrer"`（資安＋功能雙重理由：沒有 sandbox 時被嵌入頁面可導航走整個 MOST 分頁；沒有 allow 時跨來源 iframe 可能因 permissions policy 預設值播不出 WebRTC 串流）。**⚠️ 串流播放與滑鼠操作是否受影響，需要人工對真實 DSX 頁面驗證**——這是唯一 agent 無法自行驗證的項目（連上去測會把單一 WebRTC 觀看者踢下線），Howard 或 DSX 側需要找時間手動確認一次。
- `<DsxUiEntry />` 補 `editable` 權限門檻（原本無條件渲染，任何 JIT 建立的 viewer 都能一鍵搶走唯一 WebRTC 觀看者名額）。
- `horizontal_cm`／`vertical_cm` 轉換失敗（DSX 回應格式異常）不再拖垮整筆查詢——這兩個參考欄位獨立容錯，`distance_cm` 主欄位維持嚴格檢查。
- `dsx_ui_url` 加 scheme 驗證（非 `http(s)://` 視同未設定）。
- **e2e 測試套件原本會對真實 DSX 主機（`172.32.3.60:8081`）發出真實網路請求**——已加 route 攔截並用 `request.timing()` 實測證明 DNS/TCP/TLS 階段未發生；同時把「只驗 iframe `src` 屬性」升級成「驗證 iframe 實際內容」，關掉「測試永遠不會變紅」的缺口。
- 水平/垂直分量顯示的 e2e 覆蓋漏洞（對調偵測不出來）、載入/錯誤/未設定三態區分、3D modal 補 Esc 關閉。

**留 backlog（不擋這次 commit）**：伺服器端「誰開了 DSX」的稽核 log（可用性追責，非資安缺陷）、iframe 載入失敗時的「用新分頁開啟」fallback（需要更完整 UX 設計）、已填標記在使用者事後手動改值時未跟著失效（上一輪就有的既有形狀）、完整 modal a11y（focus trap／aria-labelledby）、死 i18n key 清理。

---

## 6. 尚未涵蓋（明確排除，避免被誤讀成「已考慮」）

- a0／a6（人↔物件距離）——等 P4／P10 定案後的下一輪
- CM 序列
- 座標權威歸屬（DSX A1）、Nucleus 唯讀導致調整後座標無處持久化（DSX A2）——MVP 每次即時查詢，不受這個問題影響，但長期解法未定
- ADR-031 Phase A 完整模型、多場景支援
- ADR-012（3D 動畫播放）——與本文無關，pending
- **已存檔 `WiRow` 的重新編輯**：目前整個工作台沒有「把已存檔列載回建立器重新編輯」的功能（`workbench.table.edit`／`editTitle` 這組 i18n key 已存在但未接線，唯一引用它們的 `MiCompositionTable.tsx` 是動作模組庫的編輯/複製，與 `WiRow` 無關）。因此本 MVP 的 DSX 建議查詢**只服務「組新列」情境**，已存檔列事後想補查距離建議目前做不到——這是獨立、有價值的功能缺口，範圍比本 MVP 大（牽動 `WiWorkbench.tsx` 的 `doSave()` 更新既有列 vs 新增列語意），列為後續，不在本次範圍
- **組新列時查到的建議沒有出處快照**（見 §3.1 的 `wi_row_id` 選填說明）——只有已存檔列（未來若做了上一條的重新編輯功能）才會留稽核紀錄
- **DSX 的 409（場景座標未就緒）目前訊息不夠精準**（見 §3.1）
