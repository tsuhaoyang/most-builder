# DDM v2 測試 Checklist

每次 refactor / 上線前**逐項打勾**。這份清單是針對實際踩過的回歸設計的：依賴漏宣告、種子資料缺、auth 模式、port 衝突、UI 退步。

> 原則：「本機測試過」≠「容器/正式跑得起來」。本機 `.venv` 常有額外套件、有種子資料、無 proxy —— 會把問題遮住。**乾淨環境才算數。**

---

## 0. 自動化（每次都先跑）

```bash
# 後端
PYTHONPATH=src pytest -q                                   # unit + integration（需 DATABASE_URL）
PYTHONPATH=src python scripts/core_logic/run_all.py        # 核心邏輯黃金/反例（GM=28 / CM=29）
# 前端
cd src/frontend && npm run typecheck && npm run build
E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test     # 需 preview_server 在跑
```

- [ ] pytest 全綠（含 test_export / test_import — 守 openpyxl 等 runtime 依賴）
- [ ] core_logic 黃金值正確
- [ ] typecheck + build 綠
- [ ] Playwright smoke 綠

## 1. 依賴完整性（踩過：httpx、openpyxl 漏宣告）

- [ ] 凡 `src/` 內 `import` 的第三方套件，**都在 `pyproject.toml` 的 `dependencies`**（不是只在 dev）
  - 快速檢查：`grep -rhoE "^(import|from) [a-z_]+" src/ | sort -u` 對照 dependencies
- [ ] **乾淨環境**驗證：`pip install -e .`（不含 dev）後 import 全部服務不報錯
  - `python -c "import ddm_v2.services.v2.export_service, ddm_v2.services.v2.import_service"`
- [ ] lazy import（函式內 import）也算依賴 —— 它不會讓 app 起不來，但**呼叫端點時才 500**，最容易漏

## 2. 後端端點 smoke（逐 feature）

以 admin 身分（`AUTH_DEV_USER` 或 verify cookie）打：

- [ ] `GET /api/v2/me` → 身分正確
- [ ] `GET /api/v2/rule-sets/MINIMOST_FACTORY_V1/options` → 200（**沒種 rule-set 會 404**）
- [ ] `POST /api/v2/minimost/calculate`（GM 黃金）→ total_tmu 正確
- [ ] `GET /api/v2/vocab` → 詞彙清單；`POST /api/v2/vocab`（IE+）建立成功
- [ ] `GET /api/v2/worksheets/{ws}` → 列出工序（**沒種 worksheet 會 404**）
- [ ] `PUT /api/v2/worksheets/{ws}` → 存整表（含 cycle+level）
- [ ] `GET .../export/wi-preview` / `.../export/excel`（**openpyxl**）/ `.../export/lb-csv` / `POST .../export/lb-api`
- [ ] `POST /api/v2/imports/upload` → `…/map` → `…/profiles`（**openpyxl**）
- [ ] `GET .../versions` / `POST .../publish`(manager) / `POST .../clone`(IE)
- [ ] `GET /api/v2/admin/users`(admin) + `PATCH`（角色/停用）
- [ ] RBAC：viewer 打需 IE 的端點 → 403

## 3. 前端逐分頁（瀏覽器實跑，不是只 build）

- [ ] **① WI**：精確模式是**口語句子填空**（非裸 A0/B/G）；物件/從/到是**可搜尋下拉**且輸入新詞有「＋新增」並寫回主數據；改 GM/CM 切換；TMU 即時算；加入工時表；**儲存**；重整後資料還在
- [ ] **② Level**：巢狀群組盒拖放（sub⊃cub）；~// 變動度；nb；存後保留
- [ ] **③ 主數據**：詞彙 CRUD；在此新增的詞彙 → ① 下拉立即出現
- [ ] **④ Rule-set**：規則表唯讀檢視，11 區塊有資料
- [ ] **⑤ SOP**：版本清單；發布(manager)；另存新檔(IE)；切換版本 → WI/Level 載入該版
- [ ] **⑥ 匯出**：下載 Excel / LB CSV（**openpyxl**）；LB API dry-run
- [ ] **⑦ 使用者**(admin)：列表、角色勾選、啟用切換
- [ ] **📥 匯入**：上傳 xlsx → 選分頁/表頭 → 對應 → 預覽（**openpyxl**）→ 存 profile
- [ ] Console 無紅字（F12）；無 404 的 `/api/v2/...`

## 4. 部署 / 整合（踩過：port、種子、auth、proxy）

- [ ] **DB 不對 host 開**：`docker compose -f docker-compose.yml config` 確認 db 無 published port（不撞既有 5432）
- [ ] **app port** `DDM_PORT` 選空閒（預設 8877）；`docker compose ps` 看 `0.0.0.0:8877->8000`
- [ ] **種子**：首次部署 `DDM_SEED_DEMO=true`（否則 rule-set/worksheet 缺 → 前端 404）；`logs | grep seed`
- [ ] **auth 模式**：
  - verify：`DDM_AUTH_MODE=verify` + `DDM_LB_VERIFY_URL=http://<ip>:<LB對外port>/auth/verify`（**要帶 LB 真實 port**）
  - 容器內測通：`docker compose exec ddm-v2 python -c "import os,httpx;print(httpx.get(os.environ['DDM_LB_VERIFY_URL'],headers={'Cookie':'session_id=bogus'},timeout=5).status_code)"` → 401＝通
  - 登入 LB 與開 MOST **用同一個 host 字串**（cookie 才會帶）
- [ ] **proxy**：build 走 host 網路（`build.network: host`）；runtime `NO_PROXY` 含內網（`10.0.0.0/8` 等），否則 verify 被導去 proxy
- [ ] **scripts 在 image**：`docker compose exec ddm-v2 ls scripts/`（種子/灌資料要用）
- [ ] 灌 demo 工序：`docker compose exec ddm-v2 python scripts/dev_seed_30rows.py`（⚠️ 會覆蓋 worksheet 5555 整表）

---

## 已知回歸類型（提醒）

| 症狀 | 根因 | 防線 |
|------|------|------|
| 端點 500 ModuleNotFound | 第三方套件只在 dev 依賴 / lazy import 漏宣告 | §1 + test_export/test_import |
| 前端一堆 404 `/api/v2` | DB 沒種 rule-set/worksheet | §4 種子 |
| WI 看不懂、不能加詞彙 | UI 退步成裸技術格 / 普通 select | §3 ① |
| verify 一直 401 | URL 沒帶 LB port / host 不一致 / 連不到 | §4 auth |
| build pip 連不上 | build 容器路由不到 proxy | §4 proxy |
| 容器起不來 / 連不到 | host port 衝突（5432 / 8000） | §4 port |
