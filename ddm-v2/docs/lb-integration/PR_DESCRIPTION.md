implements ADR-035: LB projection layer & motion decomposition (WP0–WP12)

MOST worksheet → Line Balance 的確定性翻譯層（`src/ddm_v2/lb_projection/`）：把七格 GM/CM motion
翻成 LB 的 24 欄 task CSV（`most-lb-csv-v1.1`）。最終驗收＝`fixtures/server_node_worksheet.json`
投影後與 `server_node_tasks.expected.csv` **逐位元相等**。

分支：`feature/lb-projection`（commit 範圍 `abc259a..HEAD`）。權威順序：Spec ＞ ADR-035 ＞ MOST_LB_CONTRACT ＞ 程式碼。

---

## WP 對照（每 WP 一組 commit）

| WP | 內容 | commit | Spec 條號 |
|---|---|---|---|
| 前置 | Spec/ADR/實作書/fixtures/steering | `abc259a` (+v1.1 同步) | — |
| WP0 | skeleton + 24 欄 contract freeze | `d194868` | §6、§10 |
| WP2 | ProjectionRow models + adapter（不碰 DB） | `081e570` | §1、§2 |
| WP3 | TmuDecomposer 分桶（static/engine 兩路徑守恆） | `8e35a5d`→`e475ab7` | §3.3 |
| WP4 | ToolLifecycleResolver（Pattern A/B、§4.3 2/3 列） | `19e3e58` | §4 |
| WP5 | PrecedenceProjector（層範圍、傳遞縮減、Kahn 編號） | `d91d339`→`247dcca` | §5 |
| WP6 | QuantityProjector + mappers + RowEmitter + project（**golden 逐位元**） | `ab913dc` | §3.2、§6 |
| WP7 | CsvContractValidator（§7 不變量 + 無主碼；34 碼全反例） | `e6b16ec`→`87f684d`→`639bce0` | §7、§8.1 |
| WP1 | level_entries 8 欄 migration v2_0046 + LevelFieldsIn + save/read + api.d.ts | `3555a03` | D7 |
| WP8 | export 端點 + LbExportBlocked（ADR-034 信封）+ lb-report + lb-api payload | `3f3dd43`+`d106a85`+`b37cdc1` | §8、§8.2 |
| WP9 | NL compiler QuantityPolicyV2（resolve_multiplier；TMU 中性） | `9f78263`+`61fb5dc` | §3.2、D4 |
| WP10 | 跨 repo LB check（reader/quantity/group/general 通過） | `e570e2a` | §10 |
| WP11 | 文件同步（9 處，加法「更新（ADR-035）」段落） | `7ac2ea3`+`7b9fed3` | §5 |
| WP12 | Level System UI（LB 標記）+ E2E + 截圖 | `4ada705`+`d73467f` | §6、§8、D10 |
| 收尾 | DoD 打勾 + §3 sha 表 + D18 已落地 | `f269c47` | — |

契約 v1.1 文件（架構師）：`7ac2ea3`（general_role 欄、action_type 標籤、分桶規則、task 31 傳遞縮減）。

---

## 測試數字（本輪總驗）

- `PYTHONPATH=src pytest tests/unit -q` → **1643 passed**（tests/unit 與 tests/integration 有同名檔 `test_search.py`，依 CI_GATES 必須**分開跑**）。
- `PYTHONPATH=src pytest tests/integration -q` → **603 passed, 1 skipped**（含 3 個 WP8 export 案 + WP1 lb_tags roundtrip）。
- `python3 scripts/core_logic/run_all.py` → **✅ 全部通過**（引擎黃金值全程未動）。
- `ruff check`：ADR-035 全部新增/修改檔案乾淨（repo 另有 63 個 **pre-existing** 錯誤，全在未觸碰檔案：`rule_set.py`/`llm_planner.py`/`prompts/*`/`rule_plan_adapter.py`/英文解析測試——不在本 PR 範圍，已回報 Howard）。
- 前端 `npm run typecheck && npm run build` → **通過**。
- Playwright E2E（`wp12-lb-tags.spec.ts`）→ **3 passed**：main（存 3 列於 wcub20+offline → lb-report `atomic_groups['20']==[1,2,3]`）、deep（`toggleOffline` 同 wcub 傳染真 store 驗證）、reverse（freq>1 → assignWcub 擋、wcubError 亮）。
- 截圖：`docs/lb-integration/screenshots/level-system-lb-tags.png`（wcub 紫 chip + 列級工具列 offline/pin/general/merge_lock/action_type + worker_cub 正交約束區 + LB 投影匯出面板，一張全景）。

---

## 與 Spec 的關鍵對照

- **§3.3 分桶**：use 段重複區塊 R 切三桶（setup_pre / N×use_once / setup_post）；靜態逐格 `slot_tmus[s]/N`、引擎 `compute_cycle(strip_repeats(slots=R))`；兩路徑皆驗守恆。
- **§4.3**：Pattern B 同 chain 向後看決 2/3 列；N>1 setup_post 併 acquire、N=1 併 use。
- **§5.5**：層間邊＝`hi_Y<lo_X` 偏序的**傳遞縮減**（golden 42 邊；task 31 = `{6,12,15,21,27,30}`）；`build_output().precedence_edges` **不沿用**。
- **§6**：24 欄凍結；`p2`/`complexity_level` 恆空；`qty_scope` 不輸出 `auto`；不輸出 `machine_count`/`manpower`（D16）。
- **§7.1**：TMU 守恆在 TMU 域比（`Σ_motions(total×freq) == Σ_tasks(once×quantity-if-cyclic)`）；取放等長比 ms。
- **§8.1**：34 個 E/W 碼每碼至少一反例（覆蓋矩陣見 WP7 commit）。

---

## 三個裁決紀錄

1. **v1.1 版本字串**（唯一權威＝Spec §0 標題 `most-lb-csv-v1.1`）——6 檔版本字串同步。
2. **分桶規則**（(c)，2026-09-12）：use 段部分格 repeat 合法，採「連續重複區塊」分桶；連續性只看非零工時格；夾心 → 新碼 `E_REPEAT_NONCONTIGUOUS`。
3. **action_type 標籤優先**（(B)，2026-09-12）：fixture 無 slot 結構碼，附錄 A 推不出 remove/test 等語意 → `lb_tags.action_type`（IE 標定）為 §6 第③級來源，附錄 A 降為有 slot_inputs 時的 fallback（`test_lb_projection_action_type_fallback.py` 覆蓋，不進 golden）。
   （另有裁決 A：task 31 傳遞縮減、golden 由架構師修正並重過 LB 驗證。）

---

## 已知限制

1. **client 端 tool-held 偵測靠後端**：前端 `Row` 型別無工具欄，`assignWcub` 只能精確擋 `freq>1`；tool-held 的 wcub 由後端 `E_ATOMIC_ON_TOOL_MOTION`（validator）+ lb-report 顯示 E 碼擋下（符合「UI 擋不到靠 lb-report」設計）。
2. **SIMO 從屬列不輸出**：`simo_group_id` 非空的列不進 DAG（§5.2）；validator 對其發 `W_SIMO_COLLAPSED`。
3. **`E_TOOL_ID_SHARED_ACROSS_LOT` 為過渡 E 碼**：LB ADR-001 追記缺口的守衛；待 LB WP-L2 release（`detect_merge_candidates` 改回 `MergeDetection` 型別、修好 `_clean_release_excluded_by_universe` NameError）後降為 W。跨 repo check 腳本已用 `getattr(result,"candidate_groups",result)` 兩型別皆接，LB 一修即可驗「scanner 恰 1 組、electric_driver 0 組」。
4. **`E_NARRATIVE_EN_MISSING` 在 save 路徑不可達**（save 一律 `build_narrative_en` 合成英文，D14）；以 raw `UPDATE most_cycles SET narrative_en=NULL`（模擬舊資料／匯入列，backfill 對象）驗 422 信封。

---

## 合併注意

- `src/frontend/openapi.json` 維持 gitignored（build 產物）；`api.d.ts` 已提交。
- migration `v2_0046` 已在 live DB 驗 upgrade/downgrade/re-upgrade 可逆。
- `main.tsx` 的 `window.__ddmTest` 僅 `import.meta.env.DEV` 暴露，正式 build 不掛（零 production 影響）。
