# ADR-038 對 DSX 的配合與確認事項

**文件類型：** 跨專案交接（MOST → DSX；由 Howard 轉交 DSX repo）
**建立日期：** 2026-11-24
**依據：** [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md) D5（含 2026-11-23 修訂）、
[ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md)（proposed）
**MOST 實作：** W7a（區域、座標快照、物件歸區）、W7b（算距離與建議）

## 狀態

📤 待 DSX 方確認。本案只改 MOST（Howard 2026-11-23）。下列事項不需要 DSX 改程式就能上線；標「需確認」的是 MOST 依現行行為做的假設，DSX 若不同，請回覆。

## 1. 方向改變：距離改由 MOST 算

| 項目 | 以前 | 現在（ADR-038 D5.4） |
|---|---|---|
| 誰算距離 | MOST 每次呼叫 DSX `POST /api/v1/distance` | MOST 用自己存的座標快照算 |
| 座標從哪來 | DSX 即時回 | 使用者在 MOST 按「從 DSX 同步」時，MOST 呼叫 DSX `GET /api/v1/placements`，存一份快照 |
| 3D 裡拖動物件 | 下次查詢立刻生效 | **不影響** MOST 已存的座標，直到使用者再按一次同步 |
| 舊的 a3 查詢 | — | `POST /api/v1/distance` 仍在用（MOST 的 `POST /api/v2/dsx/a3-distance`），新畫面上線後再評估移除 |

**請 DSX 方知道：** `dsx-integration-api-contract-draft.md` 描述的「MOST 每次查 DSX」方向已反轉。

## 2. MOST 使用的 DSX API（都是既有的，不需要新增）

| API | 用途 | MOST 讀的欄位 |
|---|---|---|
| `GET /api/v1/objects` | 區域綁定 DSX 物件時的下拉清單 | `objects[].id`、`label_zh`、`vocab_code`、`visible` |
| `GET /api/v1/placements` | 同步座標 | `ready`、`station_id`、`placement_revision`、`placements[].object_id`、`placements[].anchor_cm`（沒有時用 `station_local_cm`） |

MOST 對回應的限制（超過就整份拒絕，畫面顯示「DSX 無法連線」）：本文 ≤ 2 MB、物件與擺放各 ≤ 2000 筆、字串 ≤ 200 字、座標絕對值 ≤ 1000 cm、`object_id` 不重複、`station_id` 必填、`placement_revision` 為 0～2^31−1 的整數。座標未就緒（HTTP 409 或 `ready=false`）時，畫面顯示「DSX 座標尚未就緒」，不會同步。

## 3. 需確認

1. **座標系（需確認）。** MOST 假設站內座標是**公分、Z 軸朝上**（依 DSX `config.yaml` 的 `meters_per_unit: 0.01`、`up_axis: Z`）。MOST 的人端偏移 `[0, 0, 140]`（肩高）只在 Z 朝上時成立；若 DSX 場景改成 Y 朝上或改單位，請先通知 MOST，否則 a0／a6 會算錯。
2. **`anchor_cm` 的定義（部分已知，需確認旋轉）。** MOST 用 `anchor_cm` 當物件（區域）的量測點，理由是它代表「手會去的地方」，不是 bbox 中心（DSX 實測 P4：用 bbox 中心時 8 個物件全落 A24）。DSX `schema.py` 已寫明它是「套用 anchor 後的實際量測點（站內局部）」。請確認：
   - `anchor_cm` **不含**人端偏移（肩高）。MOST 自己在人那一端加偏移（預設 `[0, 0, 140]`，可由 MOST admin 調整）。
   - `offset` 模式的錨點，是否已套用物件旋轉（物件轉了 90°，錨點跟著轉）。
3. **作業員物件（role: origin）。** MOST 把人的位置當成站內原點 `(0, 0, 0)` 加偏移，不讀作業員物件的 placement。請確認 `station_local_cm` 的原點永遠是作業員站位，作業員物件本身的 `station_local_cm` 為 `(0, 0, 0)`。
4. **`placement_revision` 目前是靜態值（已確認，供參考）。** DSX 讀 `config.yaml` 的 `station.placement_revision`（`vocab_map.py`），使用者在 3D 裡拖動物件不會改變它。所以 MOST 只把它記在快照上供查，**不用它判斷座標有沒有變**；畫面以同步時間為準。若 DSX 之後讓它隨拖動遞增，請告知，MOST 可以改用它提示「與上次同步不同」。
5. **共用場景（ADR-038 D5.4）。** DSX 只有一個場景，所有 SKU 共用。使用者在 DSX 調好擺放後，在 MOST 選定 SKU 按同步。請 DSX 的畫面顯示「目前在調整哪個 SKU」——MOST 無法從 DSX 回應得知這件事。建議 DSX 畫面提供一個文字欄位或下拉讓使用者標示 SKU（只顯示用，MOST 不讀）。

6. **不採用的欄位（供參考）。** DSX 距離回應裡的 `measure_from_mode`、`provisional`、`warnings` 屬於 DSX 自己算距離的出處；MOST 改成自己算之後不讀這些欄位，改記 MOST 端的出處（人端偏移、門檻、快照、`point_source`）。

## 4. 之後可能需要 DSX 配合（不在 12 月底範圍）

- **座標有變的通知（ADR-038 D5.4 末段）。** 若之後要即時提示，DSX 只需送「座標有變」通知，MOST 提示使用者重新同步；資料仍由 MOST 拉。
- **物件級座標（ADR-038 D5.5）。** 現在距離一律量到區域中心（區域綁的那個 DSX 物件的錨點）。資料面已預留物件座標欄位；之後若 DSX 能提供「同一區域內不同物件」的錨點，MOST 可直接填入。
- **取放錨點一個物件多個（ADR-031 P4）。** 例如料架有多層，目前一個物件一個錨點。

## 5. MOST 端的對應（給 DSX 方參考）

- 區域（按 SKU）綁一個 DSX 物件 id；同步時區域中心＝快照中該物件的 `anchor_cm`，並記錄 `point_source`（`anchor`｜`station_local`）。
- 快照裡找不到區域綁的物件 → MOST 清空該區域座標並提示，不沿用舊值。
- 算距離：`a0`＝人 → 從哪裡；`a3`／M＝從哪裡 → 到哪裡；`a6`＝到哪裡 → 人（與 DSX `schema.py` 語句模型的 A 格端點相同）。列上沒有「從哪裡」時，a0 與 a3／M 的起點都改用「物件」所在的區域。直線 3D 距離；≤ 門檻（預設 70 cm）填伸手、> 門檻填走動；a6 超過門檻、M 超過 75 cm 交 IE 裁決。
- 結果是建議，使用者確認後才寫進工時表；TMU 一律由 MOST 引擎算（ADR-031 I1）。
