# ---- Stage 1: 建置 React 前端 → /fe/dist ----
FROM node:20-slim AS frontend
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} NO_PROXY=${NO_PROXY}
WORKDIR /fe
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime（API + 前端 dist 同一容器） ----
FROM python:3.11-slim

# Accept proxy settings as build-time args (forwarded from host env by docker-compose)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DDM_ROOT_DIR=/app \
    DDM_DATA_DIR=/app/data \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy}

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

# ---- 依賴：只從鎖檔安裝，且驗 sha256 ----
# 先單獨 COPY 鎖檔再裝，讓這層在「只改 src/」時能命中 build cache。
#
# `--require-hashes`：釘的是 **artifact 的位元組**，不只版本字串。這是 image 唯一
#   一次對外拉東西的時機，而公司 build 走 HTTP proxy（見上面的 ARG）——proxy 正是
#   「換掉套件內容而不改版號」看不出來的位置。版本相同不等於內容相同。
# 沒有用 `pip install -e .` 一次帶出依賴：那會讓 image 每次 build 都重新解析到當下的
#   最新版，同一份 commit 昨天綠今天紅（本次鎖版機制要根治的正是這件事，
#   見 docs/architecture/legacy-inventory-and-engine-audit.md §12）。
# ⚠️ 這裡**刻意沒有** `pip install --upgrade pip`，請不要「順手」加回去。
#   那行會從 PyPI 抓「當下最新的 pip」——沒有版本、沒有 hash——然後用**剛剛抓來的那個 pip**
#   去驗證下面 800+ 個 sha256。能操控 proxy／索引的人只要回一個「hash 檢查永遠通過」的
#   pip wheel，`--require-hashes` 就整組失效，而鎖檔 diff、CI、docker_smoke 的 pip freeze
#   對照**全部照樣綠**（被換掉的 pip 可以照實回報版本號；smoke 比的是名稱與版本字串，
#   不是位元組）。那是整套控制措施的信任根，卻會是唯一不受該控制措施保護的抓取。
#   `--require-hashes` 從 pip 8（2016）起就支援，base image 自帶的 pip 遠新於此，不必升級。
#   （這裡刻意**不寫死實際版本號**：base image 被上游重建後 pip 版本會變，寫死的數字會無聲
#   變成假話，而它正好是「不必升級」這個論據的依據。用「下界 + 事實」表述才不會過期。）
#   真要升 pip，必須改成「另一份帶 hash 的鎖檔」，不能是裸的 --upgrade。
#
# 兩份鎖檔的順序是必要的：先裝 build 依賴，requirements.lock 才能用 --no-build-isolation。
#   `--no-build-isolation` 加在 requirements.lock 上是為了堵住一個容易被忽略的洞：
#   若鎖檔裡有任何套件在本平台只有 sdist（沒有 wheel），pip 會就地建它 → 觸發 PEP 517
#   隔離環境 → **又一次不驗 hash 的線上抓取兼程式碼執行**。加上這個旗標後，結果只會是
#   「用上面釘死的 setuptools 建」或「大聲失敗」，不會是「安靜地開一個洞」。
COPY requirements.lock requirements-build.lock ./
RUN pip install --require-hashes -r requirements-build.lock \
    && pip install --require-hashes --no-build-isolation -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts ./scripts
COPY entrypoint.sh ./entrypoint.sh
# 前端 build 產物（main.py 會在根目錄服務此 SPA）
COPY --from=frontend /fe/dist ./src/frontend/dist

# `--no-deps` 是刻意的：依賴已由上面的鎖檔裝好，這行只註冊本專案套件本身。
# 少了它，pip 會拿 pyproject 的相容區間再解析一次，**可能把鎖檔釘住的版本升掉**，
# 於是 image 裡實際跑的又不是鎖檔那一組（鎖了等於沒鎖）。
# 代價：若有人在 pyproject 新增依賴卻沒重跑 scripts/lock_deps.sh，image 會 build 成功
# 但 import 時才炸——這個缺口由 CI 的「鎖檔同步」關卡擋（見 .github/workflows/ci.yml）。
#
# `--no-build-isolation` 同樣是刻意的，而且**不能只加這個旗標**（見上面的 requirements-build.lock）：
# `--no-deps` 關掉的只是**執行期**依賴解析，關不掉 PEP 517 build isolation。少了本旗標，
# pip 會在 hash 驗證都通過之後，另開一個隔離環境向索引拉 pyproject `[build-system] requires`
# 的 `setuptools>=68`（上界開放）與 `wheel`，**完全不驗 hash**，然後**執行它們**——
# 而 build backend 正是產生「最終安裝進 image 的 ddm_v2 套件」的那段程式碼。
# 加上 PIP_NO_CACHE_DIR=1，那是每次 build 都必然發生、且同樣經過公司 proxy 的一次抓取。
# 被動手腳的話可以在打包時對 `ddm_v2` 原始碼注入（例如往 auth/ 塞後門），而
# `pip freeze` 對照一致、黃金值 GM=28/CM=29 照樣打得出來——沒有任何現有關卡看得到。
RUN pip install --no-deps --no-build-isolation -e . \
    && mkdir -p /app/data \
    && chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]