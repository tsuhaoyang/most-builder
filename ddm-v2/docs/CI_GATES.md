# CI 門檻：重大驗證測試點

**這些過了，CI 才綠**（`.github/workflows/ci.yml`）。每個功能都有對應的 testing script；新增/改功能時，先在這裡補上驗證點與測試，再寫實作。

## 規則（硬性）

1. **凡 `src/` import 的第三方套件，必在 `pyproject.toml` `dependencies`**（不是只 dev）。CI 用宣告的依賴跑 → 漏宣告會紅。
2. **每個 feature（每組端點）至少一個整合測試**涵蓋：正常路徑 + 一個邊界/RBAC。
3. 改核心邏輯（引擎/rule-set/level）→ 必過 `core_logic/run_all.py` 黃金值。
4. **值權威（ADR-014）**：黃金錨＝`MINIMOST_FACTORY_V2`（v3 IE 認證字典）；`rule_set_seed_v2.py` 為 converter 產物**禁手改**（改值＝改字典 JSON 後重跑 `scripts/import_v3_dictionary.py`）；V1 回放測試必須維持綠（快照隔離）。
5. 前端改動 → typecheck + build + Playwright smoke 綠。

## Feature → 驗證測試點 → script

| Feature | 重大驗證測試點 | Script |
|---|---|---|
| MOST 引擎 | GM=28 / CM=29 黃金；TMU=Σindex×1；邊界 | `tests/unit/test_most_engine.py`、`scripts/core_logic/run_all.py` |
| Level System | R1–R9 填表規則；巢狀；變動度 | `tests/unit/test_level_engine.py` |
| 身分/RBAC | `/me` 身分；viewer 打 IE 端點→403 | `tests/integration/test_v2_api.py` |
| 計算 | `POST /minimost/calculate` GM 黃金 | `tests/integration/test_v2_api.py` |
| 範本庫 | CRUD + 治理(promote) + `/match`；RBAC | `tests/integration/test_v2_api.py` |
| **Rule-set** | list / options / full（11 區塊有資料） | `tests/integration/test_rule_set.py` |
| **主數據詞彙** | create→list→delete；viewer 403 | `tests/integration/test_vocab.py` |
| **Worksheet 存讀** | PUT→GET roundtrip，TMU 引擎算=28 | `tests/integration/test_worksheet.py` |
| **SOP 版本** | versions / clone / publish / 再發布 409 / RBAC | `tests/integration/test_worksheet.py` |
| **使用者管理** | list / upsert / patch；bad role 422；自鎖 409；404；viewer 403 | `tests/integration/test_admin_users.py` |
| **目錄/結構** | Site→Product→Sku→建立工序表；停用(is_active)；RBAC 403；404；重複 sku 409 | `tests/integration/test_catalog.py` |
| **計算 V2（ADR-014）** | `POST /minimost/calculate` 走 `MINIMOST_FACTORY_V2`：GM=28 / CM=29（推45cm=18吋檔）/ 推18cm→M10 反例；覆寫值取代+tech_line 標 `*` | `tests/integration/test_calculate_v2.py` |
| **計算錯誤碼（E1/E3/E4/E7）** | API 422：`A_RETURN_COMPONENT` / `P_ADDON_CONFLICT` / `OVERRIDE_INVALID`（檢 `detail.code`）；repeat 超界（0/100/1.5）422（schema 攔） | `tests/integration/test_calculate_v2.py` |
| **Worksheet SIMO（E5）** | `simo_with_row_id` 配對→存檔正規化為同一 `simo_group_id`、合計取群組 max；配對指向不存在列/自指 → 422 `SIMO_PAIR_INVALID` | `tests/integration/test_worksheet_v2_engine.py` |
| **Worksheet repeat/覆寫（E4/E7）** | repeat+manual_override 經 CycleIn 存→讀回：`slot_inputs` 原樣保留、TMU 乘算/覆寫正確、tech_line 含 `M48`/`G10*`、narrative 含 `×3`；repeat=0 存檔 422 | `tests/integration/test_worksheet_v2_engine.py` |
| **匯出** | wi-preview / excel(openpyxl) / lb-csv / lb-api | `tests/integration/test_export.py` |
| **匯入** | upload→map(正規化/警告/分秒) / profile；RBAC；openpyxl | `tests/integration/test_import.py` |
| **Excel 匯入 2b submit（ADR-013）** | submit happy-path、uploaded→409、ws不存在→404、viewer→403、重複提交→409 | `tests/integration/test_import.py` |
| **Motion Modules（impl-04）** | create→get；SM-1 IDOR；SM-2 max rows；SM-3 scope escalation；SM-4 owner immutable；SM-5 publish guard；SM-6 reorder RBAC；SM-7 apply-back version increment；DELETE happy+409；clone；instantiate；**ADR-019 Option A 迴歸（viewer 可讀任意 worksheet→200）** | `tests/integration/test_motion_modules.py` |
| **搜尋基礎設施（impl-03）** | normalize 標點/空白/lower；build_content_norm 多欄串接；NullProvider 降級 semantic=False；空查詢不碰 DB；RRF 融合：兩路共鍵排首且 match_type=fused；單路鍵 rank=1000 懲罰、仍在結果、match_type=fused | `tests/unit/test_search.py` |
| **NLP 同義詞 + nl-draft（impl-05）** | synonyms list(200)/create IE(201)/duplicate(409+SYNONYM_CONFLICT)/viewer(403)/delete(204)；**option_code 不存在→422 OPTION_CODE_NOT_FOUND（Fix-T1）**；**全形空白 normalize 後空→422 VALIDATION_ERROR（Fix-T3）**；nl-draft GM 治具防護(F-05 §4.1)；v3 治具全套單元（壓合站/壓合位置/治具→GM；執行/進行/**機台（CM 觸發詞，Fix-T2）**→CM）；normalize OR 兜底消除（Fix-Low-T：測试机器→測試機器；機台機臺→機臺機臺） | `tests/unit/test_nlp.py`、`tests/integration/test_nlp_api.py` |
| 前端（全分頁） | 載入/身分/分頁渲染/匯入精靈 | `src/frontend/e2e/smoke.spec.ts` |
| 依賴完整性 | `create_app()` 乾淨 import；端點測試抓 lazy import | CI「乾淨 import」step + 上列各端點測試 |

## CI jobs（`.github/workflows/ci.yml`）

- **backend**：postgres service → 裝宣告依賴 → 乾淨 import → migrate+seed → core_logic → `pytest`
- **frontend**：`npm ci` → typecheck → build
- **e2e**：full stack（seed + build + preview_server :8099）→ Playwright

## 本機快速重現 CI

```bash
cd ddm-v2
pip install -e ".[dev]"
DATABASE_URL=... PYTHONPATH=src alembic upgrade head
DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_v2.py
DATABASE_URL=... PYTHONPATH=src python scripts/core_logic/run_all.py
DATABASE_URL=... PYTHONPATH=src pytest -q
( cd src/frontend && npm run typecheck && npm run build )
```
