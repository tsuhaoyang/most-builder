# ---- Stage 1: 建置 React 前端 → /fe/dist ----
#
# ==== base image 以 digest 釘死（pin 日期 2026-08-15）====================
# 這段說明對本檔兩個 FROM 都適用，Stage 2 不再重複。
#
# 為什麼 tag 之外還要 digest：
#   tag 是**可變指標**。上游 rebuild 後 `node:20-slim` / `python:3.11-slim` 會指到不同的
#   位元組，而 Dockerfile 沒變、鎖檔 diff 空的、CI 全綠——同一份 commit 昨天與今天 build
#   出來的 image 不同，且沒有任何現有關卡看得見這件事。
#   對比之下，本檔下面 800+ 個 wheel 每一個都驗 sha256（requirements*.lock 的
#   --require-hashes）。但**那整套驗證是跑在這兩個 base image 裡面的**：驗 hash 的 pip、
#   解壓的 tar、跑 build backend 的直譯器，全部來自 base image。base image 是整套控制措施
#   的信任根，卻曾是唯一沒被釘住的一環——而且自從移除 `pip install --upgrade pip`
#   （見下方 Stage 2 的長註解）之後，它是**唯一**的單點。釘 digest ＝ 讓信任根也有
#   位元組級的身分，與底下 800+ 個 wheel 同一個等級。
#
# ⚠️ 釘的必須是 **manifest list（OCI image index）** 的 digest，不是單一平台 image 的。
#   釘錯層級的症狀：在非 amd64 的機器（arm64 開發機、arm runner）上 build 會以
#   「no match for platform in manifest」失敗，而那個錯訊完全看不出根因是釘錯了層級。
#   取值與驗證層級——**一次抓取同時得到兩者**（分兩次抓，中間上游剛好 rebuild 就會
#   拿到「A 的 digest ＋ B 的層級」，而那正是本段要防的錯）：
#     docker buildx imagetools inspect node:20-slim --raw > /tmp/mf.json
#     echo "sha256:$(sha256sum /tmp/mf.json | cut -d' ' -f1)"   # ← 貼到 FROM 後面的值
#     python3 -c 'import json;print(json.load(open("/tmp/mf.json"))["mediaType"])'
#   後者必須印出 application/vnd.oci.image.index.v1+json；
#   若是 ...image.manifest.v1+json 就是單平台的，**不要用**。
#
#   為什麼推薦這條：digest 的定義就是 manifest 位元組的 sha256，所以它是**自我驗證**的，
#   不依賴任何人類可讀輸出的格式維持穩定。
#   （2026-08-15 實測 docker 29.3.0 / buildx v0.31.1：--raw 給的是 registry 上的原始
#    位元組、不重新序列化，結尾也沒有多餘換行，算出來的值與 registry 的 digest 相符。）
#
#   ⚠️ 判層級**一定要真的解析 JSON**，不要用 grep 湊。2026-08-15 實測：
#   `python:3.11-slim` 的 index manifest 是**壓成一行**的，而且 `"manifests"` 排在頂層
#   `"mediaType"` **前面**——於是 `grep -o '"mediaType"...' | head -1` 取到的是**子 manifest**
#   的型別（...image.manifest.v1+json），看起來就像「這是單平台的、不能用」，
#   會把一次完全合法的 base image 升級擋掉。（node:20-slim 的則是多行縮排格式，
#   grep 剛好會對——「在一個 tag 上試通了就當通用」正是這個坑的入口。）
#
#   人工要快速看一眼，用不帶旗標的版本就好（頂層 Digest: 與 MediaType: 兩行都在）：
#     docker buildx imagetools inspect node:20-slim
#   要在腳本裡取裸值：
#     docker buildx imagetools inspect node:20-slim | awk '/^Digest:/{print $2; exit}'
#
#   ⚠️ **不要**用 `--format '{{.Manifest.Digest}}'` 或 `'{{.Manifest.MediaType}}'`。
#   實測（同上版本）：格式字串若**只由一個 .Manifest 選擇子構成**，buildx 會忽略它、
#   改印整段人類可讀的預設輸出，而且 **exit 0、stderr 全空**——照這個寫自動化比對會
#   恆不相等，卻沒有任何錯誤訊號可循（本專案最不能忍受的那種失敗形態）。
#   （成因是「只有選擇子」這個形狀：`{{println .Manifest.Digest}}`、
#    `{{printf "%s" .Manifest.Digest}}`、前面多一個字元都能正常印出裸值。
#    但既然只需記一條，記上面那條自我驗證的。）
#   （同理不要用 `docker pull` + `docker images --digests` 之類的迂迴作法取值：那取到什麼
#    層級取決於本機 daemon 當下拉了哪個平台，正是上面那個釘錯層級的來源。）
#
# tag 保留不刪：同時給 tag 與 digest 時 **Docker 只認 digest**，tag 純粹是給人看的
#   「這是哪一條線」。刪掉 tag 會讓下次升級的人不知道該回哪個 tag 去查新 digest。
#
# 升級程序（何時做：base image 有安全更新、或例行複查發現 pin 已久）：
#   1. 跑上面的 `--raw` 那三行取新 digest（同一份輸出順便確認 mediaType 是 index）
#   2. 換掉 FROM 行的 sha256，並更新該行上方的「pin 日期 / tag 當下解析到什麼」
#   3. ./scripts/docker_smoke.sh 必須綠（build + 起容器 + 端點 + GM=28/CM=29）
#   詳見 docs/CI_GATES.md「依賴鎖版與安全稽核」。
#
# ⚠️ 釘死換來的是「不再有無聲漂移」，代價是「**不再自動拿到 base image 的安全修補**」。
#   這個代價是刻意接受的（無聲換掉信任根 > 修補延遲），但它需要有人定期複查——
#   在釘死之前，nightly 的 docker-image job 會因為上游 rebuild 而順帶碰到新 base image；
#   釘死之後**它不會了**。nightly.yml 與 CI_GATES.md 的相關敘述已同步更新為此現實。
#
# 本行 pin 記錄：tag `20-slim` 於 2026-08-15 解析到 node 20-bookworm-slim
#   （上游建置時間 2026-04-22）。
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS frontend
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
# digest 釘死（pin 日期 2026-08-15）。理由、取得指令、驗證是不是 index、升級程序：
#   一律見 Stage 1 上方那段說明，此處不重複一份（重複的說明會各自腐爛）。
# 本行 pin 記錄：tag `3.11-slim` 於 2026-08-15 解析到 python 3.11.16-slim-trixie
#   （上游建置時間 2026-08-13）。
#
# ⚠️ 這一行順帶釘住了 **base image 自帶的 pip**，而那正是下面「不得 pip install --upgrade pip」
#   那段論據的主詞：整套 --require-hashes 是由「base image 內建的那個 pip」執行的。
#   釘 digest 之前，那個 pip 是誰會隨上游 rebuild 無聲改變（論據的前提浮動）；
#   釘之後它是固定的位元組。換句話說本行不只是可重現性，它把該段安全論證的前提補實了。
#   注意這只是**收窄**而非消除：升 digest 就會換掉 pip，所以下面刻意不寫死 pip 版本號
#   仍然是對的。
FROM python:3.11-slim@sha256:a630a63cdb314e2d138a2fca3e375e319e8568346ffafac5b980f888630ac4f1

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