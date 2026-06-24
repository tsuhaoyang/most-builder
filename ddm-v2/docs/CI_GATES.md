# CI 門檻：重大驗證測試點

**這些過了，CI 才綠**（`.github/workflows/ci.yml`）。每個功能都有對應的 testing script；新增/改功能時，先在這裡補上驗證點與測試，再寫實作。

## 規則（硬性）

1. **凡 `src/` import 的第三方套件，必在 `pyproject.toml` `dependencies`**（不是只 dev）。CI 用宣告的依賴跑 → 漏宣告會紅。
2. **每個 feature（每組端點）至少一個整合測試**涵蓋：正常路徑 + 一個邊界/RBAC。
3. 改核心邏輯（引擎/rule-set/level）→ 必過 `core_logic/run_all.py` 黃金值。
4. 前端改動 → typecheck + build + Playwright smoke 綠。

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
| **匯出** | wi-preview / excel(openpyxl) / lb-csv / lb-api | `tests/integration/test_export.py` |
| **匯入** | upload→map(正規化/警告/分秒) / profile；RBAC；openpyxl | `tests/integration/test_import.py` |
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
