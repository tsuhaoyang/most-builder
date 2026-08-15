# ADR-029: Python 依賴鎖版與阻斷式依賴安全稽核

**狀態：** accepted（2026-08-15，User 核可）
**日期：** 2026-08-12（accepted 2026-08-15）
**關聯：** [ADR-028](ADR-028-most-engine-boundary-validation-and-single-authority.md)（同一輪稽核的另一半：
那份管「引擎算什麼」，本份管「引擎跑在哪一組依賴上」）、
[引擎與 legacy 稽核 §12](../architecture/legacy-inventory-and-engine-audit.md)（事實基礎，每個版本數字都有 overlay／拆 wheel 實測）、
[CI 驗證關卡](../CI_GATES.md)（〈依賴鎖版與安全稽核〉一節為本 ADR 的操作面）、
`ddm-v2/pyproject.toml`（每個下界的實測依據寫在該檔註解）

## 脈絡

### 病：同一份 commit，CI 與本機跑的不是同一組依賴

鎖版之前，CI 與 Docker build 都是 `pip install -e ".[dev]"`——**每次重裝都重新解析到當下的
最新版**，而本機 `.venv` 是幾個月前裝的。這不是「環境設定沒統一」這種程度的問題，而是
**同一個 git sha 沒有唯一的執行語意**：昨天綠今天紅，而本機永遠複現不出來。

漂移有**兩條軸**，稽核當時只看到第一條：

| 軸 | 本機 `.venv` | CI / Dockerfile | 狀態 |
|---|---|---|---|
| 套件版本 | fastapi 0.136.0 / starlette 1.0.0 | fastapi **0.141.1** / starlette **1.6.0** | 已是事故成因 |
| 直譯器版本 | Python **3.12.13**（`CLAUDE.md` 的 setup 就寫 `python3.12 -m venv`） | Python **3.11**（`actions/setup-python` 與 `FROM python:3.11-slim`） | 稽核文件原本誤寫「宣告／CI／Dockerfile 三者一致」——**漏比了開發機** |

### 三起已發生的事故（都已修，根因同一個）

1. **fastapi 0.136 vs 0.141.1 → 兩條 unit「CI 紅、本機綠」。** 0.141 改了 `include_router()`
   的資料結構（子路由改放延遲展開的 `_IncludedRouter` 節點），走訪 `app.routes` 看不到任何
   API。**但 app 本身正常**：`app.openapi()` 有 84 條 path、415 條 integration 全綠——壞掉的
   只有「走訪路由表」。已由 `api/route_registry.py` 修掉（驗結構而非驗 API 存在）。
2. **starlette 1.0.0 命中兩支 CVE，其中一支在本 app pre-auth 可利用。** CVE-2026-54283
   （form limits 在 urlencoded 分支被靜默忽略）：`POST /api/v2/imports/upload` 宣告
   `UploadFile = File(...)`，FastAPI 先 `await request.form()` 才 `solve_dependencies()`
   （`require_role("analyst")` 在後者），所以 parser 全收完才輪到認證。實測未認證送 5000 欄
   （上限 1000）：1.0.0／1.3.0 回 401、1.3.1 回 400。
   **這是人工發現的，不是管線發現的——當時 CI 完全沒有依賴安全檢查。**
3. **`python-multipart>=0.0.9` 的下界涵蓋 CVE-2024-53981**，同一個端點、同一條 pre-auth 路徑。
   實測 200 KB 垃圾 epilogue：0.0.9／0.0.17 產生 200,000 筆 log event（0.93 s），0.0.18 只有 1 筆。

事故 1 的直接修法（`route_registry`）與事故 2/3 的直接修法（把下界改成實測值）已於前一批
落地。但**下界修正只消掉「宣稱支援但會 crash」的區間，沒有消除「昨天綠今天紅」**——
`fastapi>=0.133,<1.0` 之間仍橫跨數十個可破壞的 minor 版（0.x 依慣例 minor 就能破壞相容）。

### 為什麼現在、為什麼只有 Python 側

前端早就是鎖的（`npm ci` + `package-lock.json`，Dockerfile stage 1 也走 `npm ci`）。
Python 側是唯一缺口，而且是**同時**影響 CI、本機與 production image 的那個缺口。
另外，CI 是這一輪才修活的（見稽核 §10）——修活之後第一次真的跑測試就撞上這件事，
代表這個缺口不是理論風險。

## 決策

### 1. 鎖檔格式用 pip requirements，不用 `uv.lock`；uv 不進部署路徑

產生器是 `uv pip compile`（`scripts/lock_deps.sh`），但**輸出是標準 pip requirements 格式**。
決定性理由是部署面而非工具偏好：CI 與 Dockerfile 用**原生 pip** 就能安裝，
**image 內不需要 uv**。uv 只在「重新產生鎖檔」時出現在開發者與 `deps` job 的機器上，
不是 runtime 依賴、不進 production image、不增加 image 的攻擊面。

### 2. 三份鎖檔，且 dev 以 runtime 為 constraints（順序不可顛倒）

| 檔案 | 內容 | 誰用 |
|---|---|---|
| `requirements.lock` | runtime 封閉集合，34 條 pin（Linux CPython 實裝 33，`colorama` 帶 `sys_platform == 'win32'`） | Dockerfile（production image） |
| `requirements-dev.lock` | runtime + dev 工具鏈的**超集合**，47 條 pin（實裝 46），以 `requirements.lock` 為 `--constraints` 解析 | CI 各 job、本機開發 |
| `requirements-build.lock` | **PEP 517 build backend** 集合：`setuptools` / `wheel` / `packaging`，3 條 pin | Dockerfile、CI 各 job（見決策 3b） |

`requirements-build.in` 由 `lock_deps.sh` 從 `pyproject` `[build-system].requires` **生成**
（非手寫），因此「改了 build 依賴卻沒重鎖」會被 `deps` job 的同步關卡擋下。

先解 runtime、再以它為約束解 dev，保證**「pytest 綠的那一組」與「部署的那一組」在 runtime
套件上逐一同版**。反過來（先 dev 後 runtime）或兩份獨立解析，都可能讓測試環境的 sqlalchemy
與 image 裡的不是同一版——那等於把「本機與 CI 裝到不同版」這個病換個地方再得一次。

### 3. hash-pinned（`--generate-hashes` + 安裝時 `--require-hashes`）

理由不是「一般而言比較安全」，而是本專案特有的：**公司 build 走 HTTP proxy**
（`Dockerfile` 的 `HTTP_PROXY`／`HTTPS_PROXY` ARG，由 compose 從 host env 轉入）。
proxy 正是「**換掉套件內容而不改版號**」最不容易被發現的位置——版本相同 ≠ 內容相同，
而 image build 是整條流程唯一一次對外拉東西的時機。

成本已實測，很低：`lock_deps.sh` 重跑一次約 1 秒（warm cache 實測 runtime 0.58 s + dev 0.39 s）；
`--require-hashes` 只作用在該次安裝指令內，不影響日常 `pip install`。

### 3b. 堵住 `--require-hashes` 的兩個旁路（資安審查 High-1／High-2）

`--require-hashes` 本身不是密封的。初版落地後的資安審查找出**兩個繞過它的抓取**，
兩者都在同一條 proxy 上、都不驗 hash，而且**現有關卡全部照樣綠**——
鎖檔 diff、CI、`docker_smoke.sh` 的 `pip freeze` 對照比的是名稱與版本字串，不是位元組；
黃金值 GM=28／CM=29 也照樣打得出來。

| 旁路 | 機制 | 處置 |
|---|---|---|
| **H-1**：`pip install --upgrade pip` | 從 PyPI 抓「當下最新的 pip」，**無版本、無 hash**，再用**剛抓來的那個 pip** 去驗證全部 sha256。這是整套控制措施的**信任根**，卻是唯一不受該措施保護的抓取——換一個「hash 檢查永遠回 True」的 pip，`--require-hashes` 就整組失效 | **刪除該行**。base image 內建 pip 24.0，自 pip 8 起即支援 `--require-hashes`，本來就不需要升級。要升 pip 必須另立帶 hash 的鎖檔，不能是裸的 `--upgrade` |
| **H-2**：`pip install --no-deps -e .` | `--no-deps` 關掉的只是**執行期**依賴解析，**關不掉 PEP 517 build isolation**。pip 仍會另開隔離環境向索引拉 `[build-system].requires` 的 `setuptools>=68`（上界開放）與 `wheel`，**不驗 hash**，然後**執行它們**——而 build backend 正是產生「最終安裝進 image 的 `ddm_v2` 套件」的那段程式碼，可在打包時對原始碼注入 | 新增 `requirements-build.lock`（釘版 + hash），**先裝**再改用 `--no-deps --no-build-isolation -e .` |

實測證據（`--network none`，完全斷網）：舊寫法 `--no-deps -e .` 會去打
`/simple/setuptools/`、重試 5 次後 `ERROR: Could not find a version that satisfies the
requirement setuptools>=68`；新寫法 `--no-deps --no-build-isolation -e .` **零連線即完成**。
這證明該抓取真實存在，且確實被關掉了。

`requirements.lock` 的安裝也一併加上 `--no-build-isolation`：若鎖檔裡有任何套件在本平台
只有 sdist，pip 會就地建它 → 又一次隔離環境的無 hash 抓取。加上旗標後，結果只會是
「用釘死的 setuptools 建」或「大聲失敗」，不會是「安靜地開一個洞」。

附帶效果（可接受，且比改動前嚴格）：build 依賴會留在 production image 裡。
改動前 image 內是 base image 自帶、**我們沒釘也沒稽核**的 setuptools 79.0.1／wheel 0.45.1；
改動後是釘死 + 驗過 hash + 納入 `audit_deps.sh` 無豁免稽核的 84.0.0／0.48.0。

### 4. `--universal` ＋ `--python-version`：對付第二條漂移軸（3.11 vs 3.12），但不強迫降級

`--universal` 跨 OS／架構／直譯器解析同一組，平台差異用 marker 標註
（`colorama ; sys_platform == 'win32'`、`uvloop ; platform_python_implementation != 'PyPy' and
sys_platform != 'cygwin' and sys_platform != 'win32'`、dev 的 `librt ; platform_python_implementation != 'PyPy'`
與 `tomli ; python_full_version <= '3.11'`）。

因此**不強迫開發機降級到 3.11**：目前的狀態是「兩個版本都支援、且有測試證明」，
由 nightly 的 py3.11+py3.12 矩陣持續證明。這**不是**「已經對齊」——見〈不由本 ADR 決定〉1。

> **2026-08-12 更正：本節原文有兩處錯，且原文的錯法正是本 ADR 要防的那一種。**
>
> 原文寫「實測目前解析結果沒有任何 `python_version` 條件分歧」。那次實測是在 **3.12 開發機**
> 上做的，而 3.12 恰好是**看不到分歧的那一側**——因為 `uv pip compile` 解析範圍的**下界
> 預設取自「跑的人那台機器上被 uv 挑到的直譯器」**，不是 `pyproject.toml` 的
> `requires-python`（`uv help pip compile` 對 `--python-version` 寫得很白：
> 「Defaults to the version of the Python interpreter used for resolution.」
> 「Defines the minimum Python version that must be supported by the resolved requirements.」）。
> 開發機解的是 [3.12, ∞)、CI 解的是 [3.11, ∞)，後者多一個
> `tomli ; python_full_version <= '3.11'`（`coverage` 在該區間的相依）。
>
> 兩處錯：
> 1. **確實有 `python_version` 分歧**，只是在 3.12 那側的解析範圍不涵蓋 3.11，所以看不見。
>    「實測沒有」實際上是「用一台看不到的機器測的」。
> 2. **`--universal` 不保證輸出可重現。** 它保證的是「鎖檔對*範圍內*所有平台與版本都有效」，
>    不保證「*範圍本身*是誰跑都一樣」。後者只有 `--python-version` 給得了。
>    舊註解寫「universal 讓同一份鎖檔在兩者上都成立」——這句沒錯，但讀者會順勢以為
>    它也保證了可重現性，於是**註解宣稱了程式碼沒做到的保證**。
>
> 後果比 diff 噪音嚴重一級：下界由執行者決定，代表在 3.12 開發機鎖出來的那份，
> **解析範圍根本不涵蓋 3.11**，而它正是要拿去 `python:3.11-slim` 安裝的那一份——
> 解析器從來沒有被要求為部署目標負責過。
> 實際症狀則只有 `deps` job 假紅（CI run 31591161223）：後端 job 用同一份鎖檔在 3.11
> 安裝與測試全綠，因為 `tomli` 的 marker 在 3.11.15 上為 False，**它從頭到尾沒被裝過**。
> 也就是說**唯一壞掉的是同步關卡自己**。
>
> **修法**：`scripts/lock_deps.sh` 的三個 compile 一律帶 `--python-version`，值由腳本讀
> `pyproject.toml` 的 `requires-python` 下界得到（目前 `>=3.11` → `3.11`），寫法看不懂就
> 大聲失敗。**刻意不寫死常數**：寫死等於再開一條「宣告與實作各說各話」的縫（改了
> `requires-python` 卻沒人改腳本，不會有任何關卡發現）。
> 這也順帶修掉資安重審列為 Low 的 `requirements-build.lock`——那份輸入是純 `.in`、
> 沒有 `requires-python` 可依循，所以它比另外兩份**更**依賴這個旗標。
>
> **驗證**：3.11 與 3.12 兩種直譯器下跑 `lock_deps.sh`，四份產出位元組相同（含無 `.venv`
> 的 CI 形狀環境）；兩版本各建乾淨 venv 以 `--require-hashes` 安裝成功、`pip list` 集合相同、
> unit 各 296 passed；3.11 另跑 integration 415 passed + 1 skipped 與黃金值 167 全過。
> CI 的同步關卡邏輯**一個字沒改**——要修的是鎖檔的可重現性，不是把關卡放寬。

### 5. `pyproject.toml` 的相容區間完整保留，一個字沒改

**區間＝「這份程式碼支援什麼」；鎖檔＝「我們實際部署哪一組」。兩件不同的事，都要留著。**
鎖檔不取代區間宣告：區間是給人與解析器看的相容性契約（每個下界都有 overlay 實測依據寫在
該檔註解），鎖檔是可重現性的產物。本次未放寬、未收緊任何一格。

特別是**上界維持 `<1.0` 而不是收成 `<0.142`**：把上界貼著現況收會讓 `pip install -e .`
在上游每次發版時**硬性解不出來**，而那個失敗模式必須有人手動追版才能解除；
0.x 的破壞性變更改由 `route_registry` 的結構偵測 + `test_route_mounting.py` 的 OpenAPI
對照擋——**用會說話的守門擋，不用版本天花板擋**。

### 6. 鎖「新的那一組」（fastapi 0.141.1 / starlette 1.6.0），本機同步過去

不是鎖回本機舊的 0.136.0。理由：0.141 的走訪不相容**已經在 `route_registry` 修掉**，
且 415 條 integration 是在 0.141 下驗過的；鎖回 0.136 等於刻意部署一組**沒有人在驗**的版本。
本機 `.venv` 已同步（27 個套件變動），同步後 296 unit / 415 integration + 1 skipped /
167 core-logic 與乾淨 3.11 venv 數字完全相同。

「宣告與實際脫節」正是本 ADR 要根治的病，不能一邊修一邊複製它。

### 7. `pip-audit` 是**阻斷式**，不是 warn；放行走具名豁免

`scripts/audit_deps.sh` + `.pip-audit-ignore`，**CI 與本機跑同一支腳本、同一份清單**。

warn 的守門等於沒有守門：「零告警」會同時代表「沒事」與「根本沒在跑」，而這兩者**必須
能被分辨**（先例 `Built-Gate-Never-Executed`：三層機密守門設計品質很高，13 天內保護了零次，
因為 hooks 從沒被安裝——驗收一道守門的問題不是「寫好了嗎」而是「它執行過幾次」）。
改成阻斷 + 具名豁免之後，放行必須留下 vulnerability ID、「為什麼本 app 不受影響」與
`REVIEW-BY` 日期，**而且會出現在 PR diff 裡被看到**。腳本另有 `REVIEW-BY` 過期檢查：
過期就紅，不讓任何「暫時」豁免活成永久豁免。

**三份鎖檔的豁免政策刻意不同：**

- `requirements.lock`（會被部署出去）→ **不接受任何豁免**。要放行只能升版或換套件。
- `requirements-build.lock`（build backend）→ **不接受任何豁免**。它在 build 時**被執行**，
  且為了 `--no-build-isolation` 也實際留在 production image 裡。
- `requirements-dev.lock`（開發／CI 工具鏈）→ 允許具名豁免。

目前狀態（2026-08-12 獨立複驗）：runtime **0 findings**；dev **1 筆**具名豁免
`PYSEC-2026-1845`（pytest ≤ 9.0.2 的 `/tmp/pytest-of-{user}` 可被同主機其他本機使用者
DoS/提權）。豁免的三個獨立理由：不在 production image、威脅前提（同一台主機上的另一個
本機使用者）在一次性 CI runner 與單人 WSL2 開發機都不成立、修正版 pytest 9.0.3 **超出**
宣告區間 `pytest>=8.3,<9.0`（跨大版號會動到 711 條測試與 pytest-asyncio 相容性，
是另一件要獨立驗證的事）。`REVIEW-BY: 2026-11-30`。

**「上游今天發 CVE、明天 CI 就紅」這個代價是刻意接受的**：紅的理由是真的（我們確實裝著
一個有已知漏洞的套件），修法很便宜（重跑 lock 升版），而 nightly 的 `audit-latest` 會讓它
通常先在半夜紅，而不是砸在隔天某個無關的 feature PR 上。

### 8. `deps` job 的同步關卡靠「冪等」成立

`lock_deps.sh` **不帶 `--upgrade`**——`uv pip compile` 會把既有 `.lock` 的 pin 當偏好值，
於是它是冪等的（實測：重跑後兩檔在 header 之後 byte 完全相同）。CI 因此可以用
「重跑一次、`git diff` 必須為空」當同步關卡，而**這一關不會因為上游發了新版就無故變紅**。

這一關擋的是鎖檔唯一會腐爛的方式：**有人改了 `pyproject` 卻沒重跑 `lock_deps.sh`**。
因為安裝路徑是 `pip install --no-deps --no-build-isolation -e .`（`--no-deps` 是刻意的：
少了它，pip 會拿相容區間再解析一次，**可能把鎖檔釘住的版本升掉**，鎖了等於沒鎖；
`--no-build-isolation` 的理由見決策 3b），漏掉的依賴會讓 image
**build 成功但 import 時才炸**。

另外「只裝宣告的依賴 → 漏宣告 runtime 依賴（如 openpyxl）會爆」這個既有性質**完整保留**：
鎖檔是從 `pyproject` 宣告解析出來的封閉集合，沒宣告的套件不會出現在鎖檔裡。
CI gate #1（runtime deps 必須宣告）不因鎖版而失效。

### 9. nightly 把「決定性」的代價買回來

走鎖檔之後主 CI 是完全決定性的。好處是 PR 不再被上游發版波及；
代價是**我們也不再知道上游有沒有把我們弄壞**，直到某天有人重跑 lock 才一次爆出來。
`.github/workflows/nightly.yml` 三個 job 就是買回這個代價：

| job | 做什麼 | 抓什麼 |
|---|---|---|
| `latest-resolution`（py3.11 + py3.12 矩陣） | **刻意不用鎖檔**、`pip install -e ".[dev]"` 解析最新版，跑 core_logic + unit + integration + ruff，並把「最新解析 vs 鎖檔」的 diff 印進 step summary | 上游破壞性變更。**在 nightly 紅，不在無辜的 feature PR 上紅** |
| `audit-latest` | 對鎖檔重跑 `audit_deps.sh` | 新 CVE 公告是**隨時間**出現的，不是隨 commit 出現的 |
| `docker-image` | `scripts/docker_smoke.sh`：build image → 起用完即棄的 postgres → 打端點 + 驗容器內 GM=28／CM=29 + 比對容器內套件與鎖檔聯集（`requirements.lock` + `requirements-build.lock`）+ 驗 image 內無 `node_modules` | host 上的 pytest **完全不經過 image**（先例 `Docker-Compose-Stale-Baked-Engine-Image`：pytest 91 passed 但容器內是舊引擎）；以及 base image 被上游重建的漂移 |

矩陣跑兩個 Python 版本的理由見決策 4：`requires-python` 宣告 `>=3.11`，
只跑一條就是**讓宣告又一次說謊**。

**兩支 workflow 都宣告 `permissions: contents: read`**（資安審查 Medium-A）。
不宣告時 `GITHUB_TOKEN` 會落在 repo/org 預設值（多數設定是 read/write），
而 CI 每個 job 都會安裝並執行第三方程式碼（`setup.py`／PEP 517 build backend／pytest plugin）。
`latest-resolution` 尤其明顯：它**在設計上**就是「抓今天上游最新的東西並執行它」——
那正是供應鏈投毒最常見的落點。一旦命中，惡意程式碼會在一個可寫 repo 的環境裡執行，
能改 repo 內容**包含鎖檔本身**，等於用「偵測漂移的機制」把防漂移的機制拆掉。
兩支檔案全檔無任何 `secrets.*` 參照，nightly 只由 `schedule`／`workflow_dispatch` 觸發、
`ci.yml` 用的是 `pull_request` 而非 `pull_request_target`，所以唯讀權限完全夠用。

## 考慮過的選項

### A. 維持現狀（不鎖），只把下界修對

否決。下界修正處理的是「宣稱支援但會 crash」，與「同一份 commit 昨天綠今天紅」是兩件事。
現狀下 CI、本機與 production image 三者的依賴各自隨時間漂移，而且**沒有任何一個地方會
記錄當時裝的是哪一組**——事故 1 花掉的追查成本（一路追到拆 wheel 比對三組 overlay）
就是這個缺口的定價。

### B. 只收緊 `pyproject.toml` 上界（例如 `fastapi<0.142`），不用鎖檔

否決，三個理由：

1. **保護不完整**：上界只釘直接依賴。事故 2 的 starlette 當時**連宣告都沒有**（由 fastapi
   遞移帶入），本機 1.0.0 / CI 1.6.0。遞移依賴才是漂移的大宗（34 條 pin 裡直接宣告只有 13 條）。
2. **失敗模式更糟**：貼著現況的上界會讓 `pip install -e .` 在上游每次發版時硬性解不出來，
   必須有人手動追版才能解除；而鎖檔的「舊版本繼續用」是安靜且正確的預設。
3. **把區間當鎖檔用會毀掉區間的語意**：區間一旦被拿來表達「我們現在部署哪一組」，
   就再也讀不出「這份程式碼支援什麼」——決策 5 的兩件事會被壓成一件。

### C. `uv.lock` + `uv sync`

否決。`uv.lock` 是更好的鎖格式（多平台 resolution 一等公民），但它要求
**image 內必須有 uv**（或多一個 export 步驟）。為了鎖版而把一個新工具放進部署路徑，
換來的好處在本專案是零——我們沒有多套 workspace、沒有跨 platform 分支解析的需求
（實測零個 `python_version` 分歧）。`uv pip compile` 輸出 pip 格式已完全滿足，
且 CI／Dockerfile 的安裝命令維持人人看得懂的 `pip install -r`。

保留的門是：uv 仍是產生器，將來真的需要 `uv.lock` 的能力時，切換成本只在 `lock_deps.sh`。

### D. `pip freeze > constraints.txt`

否決。freeze 的內容是「這台機器上現在裝了什麼」，不是「pyproject 解出來是什麼」：
沒有 hash、沒有 marker、且**會把本機的髒東西一起鎖進去**。這不是假設性風險——
本機 `.venv` 現在就有 `psycopg2-binary 2.9.11`，而全 repo 對它**零引用**（見〈不由本 ADR 決定〉5）。
freeze 會讓這個殘留變成正式部署的一部分。

### E. `pip-audit` 採 warn-only（不阻斷）

否決。理由已寫在決策 7：warn 的守門無法與「沒在跑」區分。這裡再補一個本專案特有的理由——
**事故 2 是人工發現的**。一個依賴 CVE 已經以人工方式咬過我們一次，而人工複查的頻率是不可
承諾的；把它降級成告警，等於承諾一件我們已經證明做不到的事。

至於「阻斷會擋住無關的 PR」這個反對意見：它是對的，而且我們接受（決策 7 末段）。
差別在**紅的理由是真的**，且解法是一行 `lock_deps.sh --upgrade-package`。

### F. 單一鎖檔（不分 runtime / dev）

否決，兩個理由：

1. **production image 會混入 dev 工具鏈**（pytest／ruff／mypy／coverage），純粹擴大攻擊面與
   image 體積。`docker_smoke.sh` 現在有一條斷言就是「production image 內 dev 工具數 = 0」。
2. **豁免政策無法分級**：目前那筆 pytest 豁免之所以可接受，第一個理由就是「不在 production
   image」。合併成一份之後，這個理由消失——要嘛整體被迫接受一個部署得出去的漏洞，
   要嘛被迫在鎖版這一批順手做 pytest 9 大版號升級。**分兩份讓「不接受任何豁免」在
   production 側是可執行的，而不是一句願望。**

### G. docker smoke 也放進每個 PR

暫緩（不是否決）。走鎖檔之後 image 內容只在 `Dockerfile`／`*.lock`／`src` 變動時才會變，
PR 級的重複建置價值低而成本（每個 PR 的 CI 時間）是每次都付。
若要更嚴，正確做法是**路徑觸發**（`Dockerfile`／`requirements*.lock` 有動才跑），
不是無條件跑——見〈不由本 ADR 決定〉3。

## 驗收斷言清單

每條都可機械驗證。「實測」欄是 2026-08-12 在開發機獨立複跑的結果（不是引用實作者的自陳）。

**鎖檔本身**

| # | 斷言（可直接執行） | 實測 |
|---|---|---|
| 1 | `grep -cE '^[a-zA-Z0-9._-]+==' requirements.lock` = **34**（Linux CPython 實裝 33；`colorama` 為 win32-only） | 34 ✅ |
| 2 | `grep -cE '^[a-zA-Z0-9._-]+==' requirements-dev.lock` = **47**（實裝 46），dev-only 13 個 | 47 ✅ |
| 3 | **每一條 pin 都有 hash**：`awk` 掃「pin 的下一行不是 `--hash=sha256:`」→ 零命中；`grep -c 'sha256:' requirements.lock` = 832、dev = 1170 | 0 命中 ✅ |
| 4 | **零 `python_version` 分歧**：`grep -c python_version requirements*.lock` = 0（決策 4 的前提） | 0 ✅ |
| 5 | **dev ⊇ runtime 且共用套件逐一同版**：`comm -12` 兩檔的 `name==version` 集合 = **34**（＝runtime 全部） | 34 ✅ |
| 6 | **冪等**：重跑 `uv pip compile`（同參數）後，兩檔在 header 之後 byte 完全相同 → `deps` job 的同步關卡成立 | 相同 ✅（runtime 0.58 s／dev 0.39 s） |

**稽核關卡**

| # | 斷言 | 實測 |
|---|---|---|
| 7 | `pip-audit --no-deps --strict -r requirements.lock` → **0 findings**（production 不接受豁免，所以這一條必須恆成立） | 0 ✅ |
| 8 | `pip-audit --no-deps --strict -r requirements-dev.lock` → **恰 1 筆**：`pytest 8.4.2 / PYSEC-2026-1845 / fix 9.0.3` | 1 ✅ |
| 9 | 同上加 `--ignore-vuln PYSEC-2026-1845` → `No known vulnerabilities found, 1 ignored` | ✅ |
| 10 | `.pip-audit-ignore` 的 ID **只**作用於 dev lock（`audit_deps.sh` 不把 `--ignore-vuln` 傳給 runtime 段） | 程式碼為真；**尚無自動化測試**（見代價） |
| 11 | `REVIEW-BY` 過期 → `audit_deps.sh` 非 0 退出 | 程式碼為真；**尚無自動化測試** |

**安裝路徑**

| # | 斷言 | 實測 |
|---|---|---|
| 12 | `ci.yml` 內零個 `pip install -e ".[dev]"`；backend／e2e 皆為 `--require-hashes -r requirements-build.lock` → `--require-hashes --no-build-isolation -r requirements-dev.lock` → `--no-deps --no-build-isolation -e .` | ✅ |
| 13 | `nightly.yml` 的 `latest-resolution` **刻意**是 `pip install -e ".[dev]"`（不是遺漏） | ✅ |
| 14 | `Dockerfile` 只從鎖檔裝且 `--require-hashes`；本專案以 `--no-deps --no-build-isolation -e .` 註冊；**無 `--upgrade pip`** | ✅ |
| 15 | `docker_smoke.sh` 斷言容器內 `pip freeze` == 鎖檔聯集減 `colorama`/`setuptools`/`wheel`，build 依賴版本對得上，dev 工具數 = 0，image 內 `node_modules` = 0，且容器內 GM=28／CM=29 | ✅ **已實際執行並全綠**（2026-08-12 本機 `docker_smoke.sh`：34 套件一致、setuptools==84.0.0／wheel==0.48.0、dev 工具 0、node_modules 0、GM=28／CM=29） |
| 18 | **build 全程無未鎖抓取**：`--no-cache --progress=plain` 全新 build，log 內 36 個 `Downloading` artifact **逐一比對兩份鎖檔皆命中**（0 個未涵蓋）；零筆 `Downloading pip-`；零筆 `Installing build dependencies` | ✅ |
| 19 | **build isolation 確實被關掉**（`--network none` A/B）：舊寫法打 `/simple/setuptools/` 後失敗；新寫法零連線完成 | ✅ |
| 20 | `pip-audit` 對 `requirements-build.lock` → **0 findings**（無豁免政策） | ✅ |

**本機與鎖檔一致**

| # | 斷言 | 實測 |
|---|---|---|
| 16 | `.venv` 的 fastapi / starlette / pytest / python-multipart == 鎖檔（0.141.1 / 1.6.0 / 8.4.2 / 0.0.32） | ✅ |
| 17 | `.venv` 不含鎖檔以外的套件 | ✅ **2026-08-15 關閉**。`psycopg2-binary 2.9.11` 已從 `.venv` 移除。移除前查證：`src/`／`scripts/`／`tests/`／`migrations/` 零引用、三份鎖檔皆無、`pip show` 的 `Required-by` 為空；移除後 unit 453／integration 425／golden 全綠，`alembic current` 仍為 `v2_0035 (head)`（本專案走 asyncpg，同步驅動非必要） |
| 18 | 開發文件不再教人用未鎖的安裝方式 | ✅ **2026-08-15 關閉**。`CLAUDE.md`、`README.md`、`QUICKSTART.md` 三份都改為鎖檔安裝。<br>**本斷言原本的證據不完整**：它只點名 `CLAUDE.md` 與 `README.md`，漏了 `QUICKSTART.md`——而後者正是 `README.md` 指過去的那份，也就是新人實際會照著做的那份。修正時一併發現這三份寫 `python3.12`、DB 名寫 `ddm_v2`（實際是 `ddm_v2_most`），皆已對齊。<br>這正是斷言原文引用的 `Unfalsifiable-Security-Claim-Doc-Gate-Drift` 的下一層：**連「哪些文件會漂移」的清單本身也會漏**。 |

## 後果

### 好處

- **同一個 git sha 有唯一的執行語意**：CI、本機、production image 裝到同一組版本 + 同一批
  位元組。事故 1 那種「CI 紅本機綠」在依賴這一軸上不再可能發生。
- **供應鏈：版本相同 ≠ 內容相同這件事被真的擋住了**（hash + `--require-hashes`），
  而擋住的位置正是本專案唯一的對外拉取點（走公司 proxy 的 image build）。
- **依賴 CVE 從「人工偶然發現」變成「管線每次 PR 都問一次」**，且 production 那一組
  不接受消音。事故 2 的發現方式（人工）不再是唯一的發現方式。
- **決定性的代價有被買回來**：nightly 的三個 job 讓上游破壞在半夜紅，而不是在某個
  無辜的 feature PR 上紅——這是一個「誰承擔紅燈」的分配決策，不只是多跑一次測試。
- **鎖檔 diff 變成可讀的稽核物**：升級哪個套件、連帶動了什麼，都在 PR diff 裡。

### 代價

- **升級摩擦**：任何依賴變動都必須重跑 `lock_deps.sh` 並 commit 兩個 `.lock`，忘了就是 `deps` 紅。
  （這是刻意的：忘了的後果原本是「image build 成功但 import 時才炸」。）
- **上游發 CVE 明天就紅**：已在決策 7 明說接受。修法是 `--upgrade-package`，但那會是一個
  非計畫內的插隊工作。
- **豁免清單本身需要維護**：`REVIEW-BY` 到期會紅，而到期時要做的是「重新判斷」而不是
  「延期」——這一點只有靠人自律，腳本擋不住把日期往後改。
- **稽核工具鏈自己沒被鎖**：`pip-audit` 不在任何 `.lock` 裡，版本 `2.10.1` 分別硬編在
  `ci.yml` 與 `nightly.yml`（兩處重複），本機則完全沒裝（`audit_deps.sh` 會直接報錯退出）。
  同理 `uv` 的版本只在 `ci.yml` 的安裝 URL 裡釘死，`lock_deps.sh` **不檢查 uv 版本**——
  本機 uv 版本若與 CI 不同，「重跑 diff 必須為空」這一關可能因輸出格式差異而紅，
  而症狀會長得像「我的鎖檔壞了」。（今天兩邊都是 0.11.21，所以尚未咬人。）
- **hash 保護的邊界要說清楚**：釘住的是**應用程式依賴的封閉集合**，不含 build 工具鏈——
  Dockerfile 的 `pip install --upgrade pip`、`[build-system] requires = ["setuptools>=68", "wheel"]`
  以及 `npm ci` 之外的 node base image 都不在 hash 覆蓋範圍內。這不是漏洞，是**已知邊界**，
  寫下來以免下次有人把「全部鎖住了」當成事實句（先例：不可證偽的安全宣稱最危險）。
- **`docker_smoke.sh` 的套件比對硬編了 `colorama` 這個唯一的平台例外**。將來 universal
  解析若多出一個 Linux 不裝的 pin，這條比對會**假紅**；反過來若 marker 語意改變也可能假綠。
  正確做法是依 marker 求值而非 `grep -v` 單一名字——今天成本大於價值，記在這裡。

### 重評訊號

- **`deps` job 開始頻繁地因非本 PR 的原因變紅**（例如每週多次）：代表阻斷式的定價估錯了，
  應改為「runtime 阻斷、dev 降為 warn + nightly 阻斷」的分級，而不是整體降級。
- **3.11 與 3.12 上「實際安裝到的套件集合」開始不同**：決策 4「不強迫降級」的前提消失，
  必須立刻做 3.11/3.12 收斂（殘留 1）。nightly 矩陣是這個訊號的偵測器。
  > **2026-08-12 修訂措辭。** 原文寫的是「出現任何一個 `python_version` 條件分歧的 pin」，
  > 那個判準**太寬且會誤報**：今天 dev 鎖檔已經有一個
  > `tomli ; python_full_version <= '3.11'`，但該 marker 在 3.11.15 與 3.12.13 上**皆為 False**，
  > 兩邊 `pip list` 實測完全相同——存在一個帶 marker 的 pin，不等於兩個版本會裝到不同東西。
  > 會咬人的是**求值後**的集合分歧，訊號要盯的是那個。
  > （反過來說，這也表示不能用「鎖檔裡有沒有 marker」當偵測器，必須實際在兩版本安裝後比對，
  > 即 nightly 矩陣在做的事。）
- **鎖檔升級開始需要 `pyproject` 放寬區間才解得出來**：代表區間已落後於實際生態，
  該重新走一次下界的實測流程（不是直接放寬）。
- **`.pip-audit-ignore` 出現第二筆、第三筆豁免**：豁免從例外變成常態，代表 dev 工具鏈的
  版本政策（`pytest<9.0` 這類上界）本身需要重議。

## 不由本 ADR 決定

1. **Python 3.11 vs 3.12 的最終收斂。** 目前狀態是「兩個版本都支援、且有測試證明」，
   **不是「已經對齊」**。要真正收斂有兩條路：把開發機降到 3.11（成本低，但放棄 3.12），
   或把 CI／Dockerfile 升到 3.12（動到部署基底 `python:3.11-slim`，需要重驗整條 image 路徑）。
   本 ADR 只決定「在收斂之前，兩條都必須有 nightly 證據」。
2. **nightly 的第一次真實執行。** GitHub 的 `schedule` **只在預設分支 `202603-rc1` 上觸發**——
   這個檔在合併進預設分支之前，**排程一次都不會跑**（而且它目前還是 untracked）。
   合併後必須手動 `workflow_dispatch` 觸發一次並確認綠燈，否則就是又一個
   `Built-Gate-Never-Executed`：設計得很好、然後保護了零次。**誰在合併後負責觸發、
   以及沒觸發要不要視為交付未完成，不由本 ADR 決定。**
3. **docker smoke 是否升為 PR 關卡。** 選項 G 已分析；要做就做路徑觸發
   （`Dockerfile`／`requirements*.lock`／`entrypoint.sh` 有動才跑），代價是那類 PR 的 CI 時間。
4. **pytest 9 升級**（跨大版號 + pytest-asyncio 相容性 + 711 條測試），完成後移除唯一那筆豁免。
   `REVIEW-BY: 2026-11-30` 是這件事的截止提醒，不是承諾日期。
5. ~~**`psycopg2-binary` 的處置。**~~ **2026-08-15 關閉：已移除**（見斷言 17）。
6. **`starlette 1.6.0` 起的 `Using httpx with starlette.testclient is deprecated` 警告。**
   未來某版可能移除支援，屆時 711 條測試會一起受影響。要不要現在就改用官方建議的用法、
   還是等它真的移除再處理，需要獨立評估（涉及所有 integration 測試的 client fixture）。
7. ~~**文件面的收尾**~~ **2026-08-15 關閉**（見斷言 18）：`CLAUDE.md`、`README.md`、`QUICKSTART.md`
   三份皆已改為鎖檔安裝。原文只列了前兩份——**漏掉的 `QUICKSTART.md` 正是 `README.md` 指過去、
   新人實際會照做的那份**。教訓記在斷言 18 的儲存格裡。
