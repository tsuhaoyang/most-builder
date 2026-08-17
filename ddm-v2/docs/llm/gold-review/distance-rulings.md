# 距離裁決表 — TMU=0.0 逐筆判（IE 待答）

**文件類型：** IE 覆核材料（D3-023 任務 3；IE 2026-08-17 答案 2「TMU=0.0 看狀況、逐筆判」）
**狀態：** D3-028（2026-08-17）起**無待裁筆**——11 筆全部有裁決，內容均為「維持資訊不足」；改判永遠開放（流程見下）
**產生輪次：** 第六輪 harvest（X/I 參與判型上線後）
**維護：** 工程端依 harvest／gold 現況重列；IE 的答案落地後走留痕流程更新本表

---

## 背景（為什麼 TMU 會是 0.0）

引擎口徑：CM 序列的 M 參數按**距離階梯**取值，距離未述＝0cm → M 階梯 0→0；
linker 只掛 core 參數（CM 的 G 等伴隨 slot 不填）→ 整條 cycle 合計 0.0 TMU。
**complete 是結構完成度，不是 TMU 可信度**——TMU=0.0 非真值（D3-018 M1）。

先前處理：第四輪（D3-019）IE 對當時的 9 筆照預設答「資訊不足」
（`zero_tmu_ruling: distance_unstated`），其中 7 筆已以
`expected_incomplete_reason` 轉正、2 筆後續隨 D3-022 重切轉正（g30/g32 的
單一 cycle）。本輪（D3-023）IE 明示**不做一刀切**：逐筆判「補典型距離幾 cm」
或「維持資訊不足」。已按「資訊不足」轉正的筆一併列出——**改判是合法的**，
走留痕流程（見文末）。

## 改判的落地流程（IE 答完後由工程端執行，全程留痕）

- **草稿改判補距離**：IE 給距離 → plan 補 `roles.distance`（cm）＋
  `review_status: "ie_edited"` → `--recompile` 重算（TMU 唯一出處＝most_engine）
  → state entry 宣告 `ie_modified: true` 後走 `--promote`（D3-022 前例）。
- **已轉正 gold 改判補距離**：正式 gold 的 expected_* 是鎖點——顯式
  `--recompile <gold> --relock-approved --reason "IE 距離改判（distance-rulings）"`
  （reason 寫進檔案 notes），並同步更新該筆 `expected_incomplete_reason`／
  state entry 的 zero_tmu 面向與 worklog。
- **維持資訊不足**：不動（草稿 d003 已裁維持現狀；d038 落 `zero_tmu_ruling`
  後進轉正資格）。

---

## 清單（11 筆；不預填答案。**D3-028 起全數已裁**，見下方「D3-028 落地」）

逐筆問題皆為：**「此句的 M 動作應補典型距離幾 cm？或維持『資訊不足』
（expected_incomplete_reason=distance_unstated）？」**

### A. 已按「資訊不足」轉正的正式 gold（9 筆——列出供 IE 改判；不改則維持）

| # | 案例 | 句子 | 命中動詞→option | 缺的物理量 | 目前狀態 | TMU=0 的 cycle | IE 裁決（補距離 cm／維持資訊不足） |
|---|---|---|---|---|---|---|---|
| 1 | `g10_push_press_fixture` | 雙手接觸DIMM壓合治具推至規定位置 | 推至→`m_push` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 2 | `g11_pull_press_fixture` | 雙手接觸DIMM壓合治具拉至規定位置 | 拉至→`m_pull` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 3 | `g12_push_dimm_latches_confirm` | 雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位 | 推至→`m_push` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 4 | `g17_remove_board_bag` | 左手抓握主板的包装袋去除 | 去除→`m_remove` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 5 | `g20_attach_label_to_board` | 右手從DIMM材料盒拿取Label貼附至主板 | 貼附→`m_attach` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 6 | `g21_pull_fixture_base` | 右手接觸DIMM壓合治具的底板拉至對應的點位 | 拉至→`m_pull` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 7 | `g23_tear_dummy_dimm_bag` | 右手抓握假DIMM的包裝袋撕除 | 撕除→`m_teartape` | M 距離（cm） | 已轉正（split=test） | a1：`A0 B0 G0 M0 X0 I0 A0` | （待答） |
| 8 | `g30_pick_dummy_dimm_debag` | 從料架上拿取假DIMM，去除其包裝袋 | 去除→`m_remove` | a2 的 M 距離（cm） | 已轉正（D3-022 重切，ie_modified=true） | a2：`A0 B0 G0 M0 X0 I0 A0`（a1 acquire＝10.0 不在此列） | （待答） |
| 9 | `g32_pick_board_debag_place_bench` | 拿取主板，去除包裝袋，將主板放置工作台 | 去除→`m_remove` | a2 的 M 距離（cm） | 已轉正（D3-022 重切，ie_modified=true） | a2：`A0 B0 G0 M0 X0 I0 A0`（a1=10.0／a3=6.0 不在此列） | （待答） |

### B. 草稿——已裁「資訊不足」（1 筆；改判同樣開放）

| # | 案例 | 句子 | 命中動詞→option | 缺的物理量 | 目前狀態 | TMU=0 的 cycle | IE 裁決（補距離 cm／維持資訊不足） |
|---|---|---|---|---|---|---|---|
| 10 | `g53_attach_label_to_board_position`（原草稿 `d004_51518399`） | 貼附Label到主板規定位置處 | 貼附→`m_attach` | M 距離（cm） | **已轉正**（D3-028 Q2：切分批次確認補齊 → 誠實 incomplete 轉正，reason=`distance_unstated`） | a1：`A0 B0 G0 M0 X0 I0 A0` | 維持資訊不足（距離改判仍開放，走文首「已轉正 gold 改判補距離」流程） |

### C. **已裁**（1 筆；D3-021 起懸置，D3-028 結案）

| # | 案例 | 句子 | 命中動詞→option | 缺的物理量 | 目前狀態 | TMU=0 的 cycle | IE 裁決（補距離 cm／維持資訊不足） |
|---|---|---|---|---|---|---|---|
| 11 | `g54_tear_screen_film`（原草稿 `d029_7f085e02`） | 撕除螢幕保護膜 | 撕除→`m_teartape` | M 距離（cm） | **已轉正**（D3-028 Q3：切分批次確認＋距離裁決一併補齊 → 誠實 incomplete，reason=`distance_unstated`） | a1：`A0 B0 G0 M0 X0 I0 A0` | **已裁：維持資訊不足**（IE 原話「維持不考慮要撕多遠」，2026-08-17） |

---

## D3-028 落地（2026-08-17）

- **本表唯一未裁筆（#11 `7f085e02` 撕除螢幕保護膜）結案**：IE 原話
  **「維持不考慮要撕多遠」** → `zero_tmu_ruling: distance_unstated`
  （IEC141289，2026-08-17）。**注意這是「維持資訊不足」不是「補了距離」**——
  轉正後的 `g54_tear_screen_film` 不帶工時，是誠實記錄資訊不足。
- #10（`51518399` 貼附 Label）同輪一併轉正（`g53`），裁決值不變
  （D3-019 已裁 `distance_unstated`），本輪補的是**切分**面向。
- **A 段 9 筆與上列 2 筆的距離改判仍全部開放**：本表不因轉正而關閉——
  IE 任何一筆要補距離，走文首的 `--relock-approved` 留痕流程。
- 待裁筆數：**11 → 0**（全數有裁決；裁決內容全為「維持資訊不足」）。

---

## 本輪新增與誠實邊界

- **第六輪（X/I 參與判型）新增 TMU=0.0：0 筆**——X/I 命中把句子判型解鎖為
  CM，但 X/I slot 不由 linker 掛值（per-action linking 只掛 core 參數），
  這批 cycle 是 incomplete（`missing_core_m`）而非 complete＋0.0，不進本表。
- 任務預期「現有 10 筆」，實列 **11 筆**：9 筆已轉正（7 首批整句＋g30/g32
  重切後的單一 cycle）＋2 筆草稿（1 已裁＋1 未裁）——逐筆自 gold／draft
  檔案實數，不湊任務數字。
- 本表**不預填任何距離**：典型距離是 IE 的工程判斷（現場量測／製程知識），
  不是語料可推的值——預填即發明資料。
