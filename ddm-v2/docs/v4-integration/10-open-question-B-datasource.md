# 開放問題 B（修正版）：MOST 的輸出是「帶屬性的 DAG」，站別不屬於 MOST

> **User 裁決/糾正（2026-09-04）**：原評估（接 LB 站別回灌 vs v2 手動指派站別）**方向錯誤**。
> 站別的決定**不在 MOST 系統**。以下為修正後的正確邊界與範圍結論。
> 方法：實讀 v2 `export_service.py`、`most_engine/level.py::build_output`，附行號。唯讀分析。
> 日期：2026-09-04

## 正確的系統邊界（User 定義）

- **MOST 系統（v2）職責**：只管**工序的關聯與屬性**。用視覺化把關聯建起來（main／sub／cub），
  設定屬性（群組、不可拆分動作、不可拆分站、可否 offline、quantity、可否平行）。
  **MOST 不決定站、不決定 worker、系統內根本沒有「站」這個型態。**
- **MOST 的輸出**：一個**帶屬性的 DAG**（節點=task，邊=前序/關聯，屬性=群組/不可拆/offline/quantity/可平行…）。
- **另一套 LB 系統職責**：吃這個 DAG，決定**哪個 task 分到哪一站、由哪個 worker 執行**。
  站別指派是 LB 的產物，**不回流 MOST**。

## 這推翻了什麼

v4 的 E-SOP／Line Layout 都是**吃「站別指派」**的下游（`esop_generator.py:145-164` 複製 LB scenario
的 station snapshot；`line_layout.py` 是「站」的視覺布局）。既然站別不在 MOST：

- **Line Layout（工站布局）= 站的視覺化 → 屬於 LB 系統範疇，不是 v2 該做的。移出 v2 整合範疇。**
- **E-SOP 若依賴站別 → 依賴 LB 輸出，v2 無法獨立產出。** E-SOP 的定位需重新界定（見下）。
- 原「開放問題 B（E-SOP/Layout 資料源介面）」本身是個假問題——因為它預設 v2 要處理站別。

## v2 現況：早已定位為「產 DAG 餵外部 LB」（實讀證據）

`src/ddm_v2/services/v2/export_service.py`：
- `lb_api_payload()`（`export_service.py` `lb_api_payload`）註解明寫：
  「LB API adapter：先回『將送出的』payload（build_output 合約）」「**LB request model 由 User 提供後**
  於此對映/POST 到 LB endpoint」「目前為 dry-run」→ **v2 本來就把站別指派留給外部 LB。**
- `to_lb_csv()`／`lb_api_payload()` 的內容來自 `most_engine/level.py::build_output()`，已產出 DAG：
  - `nodes`（task content + second + `levels`/`level_min`/`level_max`/`variable` 自由度）
  - `precedence_edges`（主序 level 推得的前序）
  - `groups`（sub `movable:True` 內部定序 / cub `same_station:True` 不可拆）、`cub_groups`/`sub_groups`/`group_parents`（巢狀）
  - `number_constraints`（nb 分站上限）

## v2 現有 DAG 屬性 vs User 要求的屬性清單（差距）

| User 要求的 DAG 屬性 | v2 現況（證據）| 差距 |
|---|---|---|
| 群組 | ✅ `groups`（sub/cub + parent，`level.py::build_output`）| 無 |
| 不可拆分站（同站）| ✅ cub `same_station:True` | 無 |
| 不可拆分動作 | ⚠️ cub 表達「同站不可拆」；「單一動作內部不可拆」語義需確認是否已涵蓋 | 待確認 |
| 前序/關聯 | ✅ `precedence_edges` + node `levels` 自由度（`1~2`/`1/3` 保留可挪動性）| 無 |
| quantity | ⚠️ 有 `frequency`（`wi_rows.frequency`）；與 LB 要的 quantity 語義是否一致需確認 | 待確認 |
| 可否 offline | ❌ v2 無此屬性 | **需新增** |
| 可否平行 | ⚠️ level 自由度（`variable`）表達部分並行性；「明確可平行」布林屬性未獨立 | 待確認/可能新增 |

## 修正後的範圍結論

1. **整合重點不是 E-SOP/Layout**，而是兩件事：
   - **(1) 視覺化建立關聯的 UX**（= Level System UX，Phase 1，已可動工）——這正是 User 說的
     「透過視覺化把關聯建起來、設定屬性」。
   - **(2) 補齊 DAG 輸出的屬性完整度**：對照 User 的屬性清單，補 v2 `build_output` 尚缺的
     `offline`、確認 `quantity`／`可平行`／`不可拆分動作` 的表達。這是 MOST→LB 契約的擴充。
2. **Line Layout 移出 v2 整合範疇**（站的視覺化屬 LB 系統）。
3. **E-SOP 重新定位**：若 E-SOP 需要站別，它屬於 LB 系統下游、不是 v2 獨立能產的；
   v2 能做的 SOP 類輸出是「工序級」（不含站別指派）的作業說明。**E-SOP 是否仍為 v2 標的，需 User 再裁決**
   （見下方新開放問題 B'）。

## 新的待決點（取代原 B）

**B'：E-SOP 在新邊界下的定位。**
- v4 E-SOP 是「站別 SOP」（一站一頁），依賴 LB 站別指派 → 屬 LB 系統下游。
- v2 若要做 SOP，只能做「**工序級 SOP**」（依 WI/動作，不含站別）。
- 問 User：v2 要不要做「工序級 SOP」？還是 SOP（含站別）整個歸 LB 系統、v2 完全不做？

**B''：DAG 屬性補齊清單確認。**
- 確認 `offline`（新增）、`quantity`（= frequency？或另有語義）、`可平行`（新增布林？或用 level 自由度）、
  `不可拆分動作`（cub 是否已涵蓋）的精確定義，作為 MOST→LB 契約（`build_output`）的擴充規格。

## 對 spec 的影響

- `08` §3.2（E-SOP）改為待 B' 裁決；§3.3（Line Layout）**移出範疇**。
- 新增一個功能域「DAG 輸出屬性補齊」（§3.6，待 B'' 確認屬性清單）——這是扣除 LB/Layout 後，
  MOST 對 LB 契約的真正整合價值所在。
- Phase 2 從「E-SOP/Layout」改為「DAG 屬性補齊 + （若裁決要）工序級 SOP」。
