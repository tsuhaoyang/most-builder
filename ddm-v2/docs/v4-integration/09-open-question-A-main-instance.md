# 開放問題 A 技術評估：v4 main_instance 硬鏈是否需要在 v2 加欄

> **裁決結果（User 2026-09-04）：採 (i) — 用 v2 既有 cub group 語義表達硬鏈，不加欄，零 schema 變更。**
> Phase 1 Level UX 據此解除阻擋、可動工。以下為裁決依據原文。
>
> 目的：為 `08-implementation-spec.md` §3.1.5（Phase 1 Level UX 唯一資料模型決策）提供裁決依據。
> 方法：實讀 v4 與 v2 相關程式碼，附 `檔案:行號`。唯讀分析，不改程式碼。
> 日期：2026-09-04

## 問題重述

`07-level-system-ux-gap.md` §3 把 v4 的 **main_instance 硬鏈** 標為 v2 最大缺口：v4 有一個
「hidden group identity」把多列綁成一個不可拆、內部有序的主序實例；`07` 判定 v2 的
`countersignature`／`parent_countersignature` 與之「不等價」。問題 A：v2 要如何表達它——
(i) 用既有語義，或 (ii) 最小加一個 `main_instance_id` 欄。

## 關鍵發現：main_instance 主要是「餵 LB solver 的排程約束」，不是 Level 標註本身的必要語義

實讀 v4 對 main_instance 的**實際消費點**（grep 全 app）：

- `services/line_balance.py:9-13`（docstring 定義其語義）：
  > - inside one main_instance: the declared order is a **hard chain** (C before D)
  > - two main_instances of the SAME main may be run in **either order**
  > - the solver schedules **whole** [chains]
  `line_balance.py:53` `item.main_instance_id or f"pool:{item.id}"`、`:80` 把 instance 當排程單位。
- `routes/line_layout.py:93/106/114/178`：用 main_instance 判定「可互換群組」，缺 id 時報錯
  「請重新執行 Line Balance Simulation」。
- `routes/level_system.py`：只**存/傳** main_instance_id/name（`:59-60/:113-114/:186`），
  **未**用它做 Level 本身的結構驗證。
- `models/most.py:417-418`：欄位定義（`main_instance_id` = hidden group identity）。

**結論**：main_instance 的兩個消費者是 **Line Balance solver 與 Line Layout**——兩者都是
**不整合**的功能域（User 裁決：LB 另有系統；Layout 的資料源介面待定且依賴 LB 產出）。
Level System 本身（標註 + R1–R9 驗證）**不需要** main_instance 才能成立。

## v2 既有語義已能表達「不可拆、內部有序的 chain」

v2 `most_engine/level.py::build_output()`（對 LB 的約束模型）已產出等價結構：

- **cub group**：`same_station: True`、`movable: False`、`members`（依 order 排序）
  → 語義正是「**同站、不可拆、內部有序的一條鏈**」（`level.py` build_output §1/§2）。
  這對應 v4 main_instance 的「hard chain（不可拆 + 內部定序）」。
- **sub group**：`movable: True` + ordered members → 「可移動、內部定序」。
- `precedence_edges`（主序 level 推先後）、`number_constraints`（nb 分站上限）。

v2 缺的只有 v4 的一個**額外自由度提示**：「同一 main 的多個 instance 可互換順序」——
但這個提示的**唯一用途是給 LB solver 更大的排程自由度**。LB 不整合，這個提示在 v2 沒有消費者。

## 建議裁決

**採 (i)：用 v2 既有語義表達，不加 `main_instance_id` 欄。**

理由：
1. **main_instance 的消費者（LB／Layout）不整合**，在 v2 沒有讀取端；加欄會是「無人消費的欄位」，
   違反最小加法原則（ADR-011 精神）。
2. **v2 既有 cub group 語義**（同站不可拆 + ordered members）已能表達「硬鏈」這個 Level 層面的意義；
   Level UX 只需讓使用者把一組動作圈成一個 cub（🔒），就達成 v4 main_instance 在 Level 標註上的等價效果。
3. **不破壞 v2 治理**：不動 `level_entries` schema、不動 R1–R9 驗證、golden 不受影響（C1）。
4. **可逆**：若日後 User 決定整合某種需要「可互換 instance」自由度的下游（例如接外部 LB 的回饋），
   屆時再以加法補 `main_instance_id`，並在其真正的消費端一起落地——那時才有讀取端，加欄才有意義。

**落地方式（Phase 1 Level UX）**：
- 前端：拖拉圈選一組動作 → 建 cub 群組（v2 既有 `createGroup('cub', ...)` + `is_cub_locked` 概念，
  對應 `countersignature=cubN` + `order`）。這就是 v4「把多列綁成硬鏈」的 v2 等價操作。
- 資料：落 `level_entries` 既有欄（`countersignature`/`parent_countersignature`/`order`），無新欄。
- 不做：v4 的「同 main 多 instance 可互換」自由度提示（無消費者）。

## 若 User 仍傾向 (ii) 最小加欄

若基於未來規劃仍要加 `main_instance_id`：
- 範圍：`level_entries` 加一個 nullable `main_instance_id`（String），純標註、不進 TMU 路徑（C1 安全）。
- 代價：需 migration + 一個目前無讀取端的欄位；建議同時寫清楚「未來消費端」以免變孤兒欄。
- 仍須：不改 R1–R9、golden 全綠。

## 一句話

main_instance 是 v4 為了餵 LB solver 而設的排程身分；**LB 不整合 → v2 用既有 cub group 表達硬鏈即可，
不需加欄**。這讓 Phase 1 Level UX 可在零 schema 變更下動工。
