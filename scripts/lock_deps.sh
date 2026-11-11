#!/usr/bin/env bash
# 重新產生 Python 依賴鎖檔（requirements.lock / requirements-dev.lock）。
#
# 什麼時候要跑這支：
#   1. 動了 pyproject.toml 的 [dependencies] 或 [optional-dependencies].dev（加/刪/改區間）
#   2. 要刻意升級某個套件（帶 --upgrade 或 --upgrade-package <name>）
#   3. CI 的「鎖檔與 pyproject 同步」關卡紅了
#
# 什麼時候**不要**跑：日常開發、只改 src/ 或 tests/。鎖檔不隨程式碼變動。
#
# 為什麼是兩個檔、且有先後順序：
#   requirements.lock 是**會進 production image 的那一組**，先獨立解析。
#   requirements-dev.lock 再以它為 constraints 解析，保證「dev 環境裡的 runtime 套件版本
#   與 image 裡的完全相同」——否則 pytest 綠的那一組與部署的那一組可以是兩組，
#   等於把「本機與 CI 裝到不同版」這個病換個地方再得一次。
#
# 為什麼不帶 --upgrade：uv pip compile 會把既有 output 檔的 pin 當作偏好值。
#   不帶 --upgrade ＝「只解 pyproject 改動所必需的最小變動」，於是這支是冪等的，
#   CI 才能用「重跑一次、diff 必須為空」當同步關卡（見 .github/workflows/ci.yml）。
#   要升級請顯式：./scripts/lock_deps.sh --upgrade-package fastapi
set -euo pipefail

# --- uv 版本閘 ---------------------------------------------------------------
# 下面第 90 行起花了十幾行論證「同一份 pyproject、**同一版 uv**」是鎖檔可重現的前提，
# 但在此之前那個前提從來沒有被檢查過——只檢查了 `command -v uv`（uv 存不存在），
# 沒檢查是哪一版。這正是本專案一路在防的那個病：**註解宣稱了一個程式碼沒有驗證的前提**。
#
# 沒有這道閘的實際後果：uv 的 resolver 改版（新的回溯策略、新的 marker 正規化、輸出格式
# 微調）會讓同一份 pyproject 解出不同的鎖檔。於是 CI 的同步關卡（重跑 lock_deps.sh、
# git diff 必須為空）就會在**沒有任何人改過依賴**的情況下變紅，而 diff 看起來像是
# 依賴真的變了。這種假紅的辨識成本極高——CI run 31591161223 那次（下界問題，不是版本問題）
# 就燒掉了一輪，而那次至少 diff 只有一行 `tomli`；resolver 改版的 diff 會是整份檔。
#
# 這個常數目前有**第二份拷貝**在 `.github/workflows/ci.yml`（安裝 uv 那步的 URL 版本號）。
# 兩份必須一起動。為了讓 CI 那份可以停止手抄，本腳本提供：
#     ./scripts/lock_deps.sh --print-expected-uv-version
#
# ⚠️ 要用它，**必須先賦值再驗證**，不可以直接把 $(...) 塞進 URL 裡：
#     UV_VERSION="$(./scripts/lock_deps.sh --print-expected-uv-version)"
#     [ -n "$UV_VERSION" ] || { echo "無法取得 EXPECTED_UV_VERSION"; exit 1; }
#     curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
#
# 為什麼不能寫成一行 `curl -LsSf https://astral.sh/uv/$(...)/install.sh | sh`——
# 2026-08-15 實測（bash -e，GitHub Actions 的 run: 預設就是 `bash -e {0}`，無 pipefail）：
#   1. 命令替換用在**命令的參數位置**時，即使被替換的指令失敗，`-e` 也**不會**中止；
#      整段照跑，只是替換成空字串 → URL 塌成 `https://astral.sh/uv//install.sh`。
#   2. 那個 URL **不是 404**：astral.sh 回 200 並 302 到
#      `releases.astral.sh/installers/uv/latest/uv-installer.sh`，也就是 **latest**。
#      實測當下 latest 是 uv 0.12.5，與下面 EXPECTED_UV_VERSION 釘的並非同一版。
#   3. 於是它會**安靜地裝上錯的 uv 版本**——正是本檔整段版本閘要防的那件事，
#      而 curl exit 0、sh exit 0、`-e` 全程沒有話說。（加 pipefail 也救不了，
#      因為每一環的退出碼都真的是 0。）
#   對照組：版本號打錯字（例 `9.9.9-nope`）反而會 404，`-f` 讓 curl 退 22——
#   但沒有 pipefail 時 pipeline 仍以 sh 的 0 收場，一樣不中止，只是變成「沒裝到」。
# 賦值形式則相反：`VAR="$(失敗的指令)"` 的退出碼就是該指令的退出碼，`-e` 會確實中止；
# 再加一道顯式空值檢查，連「替換成功但印出空字串」也一併擋掉。
#
# 之後就只剩這裡一個真相來源。（本輪未改 ci.yml：該檔另有他人在動。）
#
# 怎麼升 uv（完整程序，不要只改這個常數就收工）：
#   1. 本機裝新版 uv，並把 EXPECTED_UV_VERSION 改成新版號
#   2. 重跑 ./scripts/lock_deps.sh —— **預期會產生 diff**（resolver 換版了）
#   3. 把 diff 逐行看過：版本升降是否合理？有沒有莫名多／少套件？
#   4. 三份 .lock（+ requirements-build.in）與本檔一起 commit，缺一 CI 同步關卡會紅
#   5. 同步改 .github/workflows/ci.yml 安裝 uv 那步的版本號（或改成上面那個 $() 寫法）
#   6. 跑完整驗證：pytest unit + integration、./scripts/audit_deps.sh、./scripts/docker_smoke.sh
#      （鎖檔換版＝實際部署的那一組換了，不是文件變更）
EXPECTED_UV_VERSION="0.11.21"

cd "$(dirname "$0")/.."

# 讓 CI／其他腳本能取得期望版本而不必手抄一份（見上）。放在 uv 檢查**之前**：
# 會問這個問題的時機正是「uv 還沒裝，要知道該裝哪一版」。
if [ "${1:-}" = "--print-expected-uv-version" ]; then
    echo "$EXPECTED_UV_VERSION"
    exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 需要 uv（https://docs.astral.sh/uv/）。" >&2
    echo "       本專案釘死 uv ${EXPECTED_UV_VERSION}，請裝**這一版**（不要裝 latest）：" >&2
    echo "         curl -LsSf https://astral.sh/uv/${EXPECTED_UV_VERSION}/install.sh | sh" >&2
    exit 1
fi

# `uv --version` 輸出形如 `uv 0.11.21 (x86_64-unknown-linux-gnu)`；取第二欄。
ACTUAL_UV_VERSION="$(uv --version 2>/dev/null | awk '{print $2}')"

if [ "$ACTUAL_UV_VERSION" != "$EXPECTED_UV_VERSION" ]; then
    echo "ERROR: uv 版本不符——本腳本拒絕以非預期版本產生鎖檔。" >&2
    echo "       實際版本：${ACTUAL_UV_VERSION:-<解析不到，uv --version 輸出格式變了？>}" >&2
    echo "       期望版本：${EXPECTED_UV_VERSION}" >&2
    echo "" >&2
    echo "       為什麼擋：不同版本的 uv（resolver 改版）對同一份 pyproject 可能解出不同的鎖檔，" >&2
    echo "       於是 CI 的同步關卡會在沒有人改過依賴的情況下變紅，且 diff 看起來像依賴真的變了。" >&2
    echo "" >&2
    echo "       兩條路，二選一：" >&2
    echo "       (a) 裝對版本（多數情況選這條）：" >&2
    echo "             curl -LsSf https://astral.sh/uv/${EXPECTED_UV_VERSION}/install.sh | sh" >&2
    echo "       (b) 確實要升級 uv：更新本檔頂部的 EXPECTED_UV_VERSION，**並重新產生三份鎖檔**" >&2
    echo "           （requirements.lock / requirements-dev.lock / requirements-build.lock）" >&2
    echo "           一起 commit，同時同步 .github/workflows/ci.yml 的 uv 版本。" >&2
    echo "           完整程序見本檔頂部「怎麼升 uv」註解——只改常數不重鎖，CI 會紅。" >&2
    exit 1
fi

# 讀 TOML 需要 tomllib（Python >= 3.11）。CI 的 `python3` 是 3.11，但開發機的 `python3`
# 可能還是系統的 3.10（本專案 requires-python >= 3.11，開發用的是 .venv / python3.12）。
# 這裡挑第一個「真的 import 得到 tomllib」的直譯器，而不是假設 `python3` 夠新——
# 假設錯的話這支腳本會在開發機上炸，然後大家改成手寫 .in，同步關卡就白做了。
#
# 注意：這個直譯器只用來**讀 pyproject.toml**，不影響解析結果。uv 是獨立的 Rust 執行檔，
# 它挑哪個直譯器與這裡挑哪個無關（見下方 --python-version）。
PYBIN=""
for cand in python3 python3.13 python3.12 python3.11; do
    command -v "$cand" >/dev/null 2>&1 || continue
    if "$cand" -c 'import tomllib' >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then
    echo "ERROR: 找不到具備 tomllib 的 Python（需要 >= 3.11）。" >&2
    echo "       本專案 requires-python = '>=3.11'，請安裝 python3.11+ 後重跑。" >&2
    exit 1
fi

# --- 解析目標的 Python 下界 --------------------------------------------------
# 有兩個很容易被混為一談的保證。舊版註解只寫了 (a)，但讀起來像是連 (b) 一起保證了，
# 而 (b) 其實是假的——這正是本專案一路在防的「註解宣稱了程式碼沒做到的保證」。
#
#   (a)「同一份鎖檔在 3.11 與 3.12 上都裝得起來」← 這個由 --universal 提供，屬實。
#       universal 解析不綁單一 OS／架構／直譯器，差異用 environment marker 標註，
#       安裝端各取所需（例：`colorama ; sys_platform == 'win32'`）。
#
#   (b)「同一份輸入在不同機器上跑出同一份鎖檔」← --universal **不**提供。
#       uv 自己的說明寫得很白（`uv help pip compile` 的 --python-version）：
#         「Defaults to the version of the Python interpreter used for resolution.」
#         「Defines the minimum Python version that must be supported by the resolved
#           requirements.」
#       也就是解析範圍的**下界預設取自「uv 在這台機器上挑到的直譯器」**，
#       而不是 pyproject 的 requires-python。於是：
#         開發機（uv 挑到 .venv = 3.12）→ 解析範圍 [3.12, ∞)
#         CI（setup-python 3.11，無 .venv）→ 解析範圍 [3.11, ∞)，多解出一個
#           `tomli ; python_full_version <= '3.11'`（coverage 在該區間的相依）
#       同一份 pyproject、同一版 uv，兩份不同的鎖檔 → 同步關卡假紅（CI run 31591161223）。
#
#       而且這不只是 diff 噪音：下界由「誰跑的」決定，代表在 3.12 開發機鎖出來的那份，
#       其解析範圍**根本不涵蓋 3.11**——偏偏那正是 Dockerfile（python:3.11-slim）與 CI
#       要拿去裝的版本。解析器沒有被要求為 3.11 負責過，卻由它產出部署用的鎖檔。
#
# 對策：用 --python-version 顯式釘死下界，讓輸出與執行者的直譯器無關。
# 值直接讀 pyproject 的 requires-python，**不在這裡另寫一份常數**：寫死就是再開一條
# 「宣告與實作各說各話」的縫（改了 requires-python 卻沒人改這支腳本，沒有任何東西會發現）。
PY_FLOOR="$("$PYBIN" - <<'PY'
import re
import sys
import tomllib

with open("pyproject.toml", "rb") as fh:
    spec = tomllib.load(fh)["project"]["requires-python"]

# 只認得 ">=X.Y" 這一種寫法。看不懂就大聲失敗，而不是猜一個下界然後靜靜鎖錯——
# 猜錯的後果是鎖檔的解析範圍與宣告的相容區間不一致，且沒有任何關卡會發現。
m = re.fullmatch(r">=\s*(\d+\.\d+)", spec.strip())
if not m:
    sys.exit(
        f"ERROR: 看不懂 requires-python = {spec!r}；本腳本只支援 '>=X.Y'。\n"
        "       若確實要改寫法，請一併更新 scripts/lock_deps.sh 的下界解析。"
    )
print(m.group(1))
PY
)"

echo "解析目標：Python >= ${PY_FLOOR}（取自 pyproject.toml 的 requires-python）"

# --universal：跨 OS／架構／直譯器解析同一組，差異用 marker 標註 → 上面的保證 (a)。
# --python-version：釘死解析範圍的下界 → 上面的保證 (b)，即「換台機器跑，輸出位元組相同」。
#   兩者合起來才是「鎖檔對 [PY_FLOOR, ∞) 全程有效，且產生過程可重現」。
# --generate-hashes：釘到 artifact 的 sha256，不只釘版本字串（見 docs/CI_GATES.md）。
COMMON_ARGS=(
    --universal
    --python-version "$PY_FLOOR"
    --generate-hashes
    --quiet
)

echo "[1/3] 解析 runtime 依賴 → requirements.lock"
uv pip compile pyproject.toml \
    "${COMMON_ARGS[@]}" \
    --output-file requirements.lock \
    "$@"

echo "[2/3] 解析 runtime+dev 依賴（以 requirements.lock 為 constraints）→ requirements-dev.lock"
uv pip compile pyproject.toml --extra dev \
    "${COMMON_ARGS[@]}" \
    --constraints requirements.lock \
    --output-file requirements-dev.lock \
    "$@"

# --- build 依賴（PEP 517 backend）-------------------------------------------
# 為什麼需要第三份鎖檔：`pip install --no-deps -e .` 關掉的只是**執行期**依賴解析，
#   關不掉 PEP 517 build isolation。pip 仍會另開一個隔離環境，向索引抓 pyproject
#   `[build-system] requires` 的 setuptools/wheel（**完全不驗 hash**）然後**執行它們**
#   ——而 build backend 正是產生「最終安裝進 image 的 ddm_v2 套件」的那段程式碼。
#   結果：image 每次 build 都有一次不受 `--require-hashes` 保護的線上抓取兼程式碼執行，
#   而且 `pip freeze` 對照、鎖檔 diff、黃金值全都照樣綠（被動手腳的是打包過程，不是版本號）。
#   對策：build 依賴也鎖成帶 hash 的一份，先裝好，安裝本專案時再加 `--no-build-isolation`。
#
# 這份 .in 是**從 pyproject 的 [build-system].requires 生成**、不是手寫：手寫會與 pyproject
#   各說各話，而生成 + CI「重跑後 diff 必須為空」剛好能擋住「改了 build-system.requires
#   卻忘記重鎖」——那會讓 Docker build 在 --no-build-isolation 下缺套件而炸。
#
# 這份 .in 沒有 requires-python 可依循（純 requirements 格式），所以它比前兩份**更**依賴
#   COMMON_ARGS 裡的 --python-version：少了它，uv 只能退回用當下挑到的直譯器當下界。
echo "[3/3] 由 pyproject [build-system].requires 生成 requirements-build.in → requirements-build.lock"

"$PYBIN" - <<'PY' > requirements-build.in
import tomllib

with open("pyproject.toml", "rb") as fh:
    requires = tomllib.load(fh)["build-system"]["requires"]

print("# 由 scripts/lock_deps.sh 從 pyproject.toml 的 [build-system].requires 生成——請勿手改。")
print("# 改 build 依賴請改 pyproject.toml，然後重跑 ./scripts/lock_deps.sh。")
for req in requires:
    print(req)
PY

uv pip compile requirements-build.in \
    "${COMMON_ARGS[@]}" \
    --output-file requirements-build.lock \
    "$@"

echo
echo "完成。requirements-dev.lock 是 requirements.lock 的超集合（共用套件版本必須一致）。"
echo "requirements-build.lock 是 PEP 517 build backend（setuptools/wheel）那一組，獨立於上面兩份。"
echo "請把四個檔（含 requirements-build.in）一起 commit——只 commit 一部分會讓 CI 的同步關卡紅。"
