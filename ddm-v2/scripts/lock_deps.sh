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

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 需要 uv（https://docs.astral.sh/uv/）。安裝：curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

# --universal：跨 OS / 跨 Python 版本解析一組，用 marker 標註平台差異。
#   本專案 requires-python = ">=3.11"，CI 與 Dockerfile 是 3.11、開發機是 3.12；
#   universal 讓同一份鎖檔在兩者上都成立。
# --generate-hashes：釘到 artifact 的 sha256，不只釘版本字串（見 docs/CI_GATES.md）。
COMMON_ARGS=(
    --universal
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
echo "[3/3] 由 pyproject [build-system].requires 生成 requirements-build.in → requirements-build.lock"

# 讀 TOML 需要 tomllib（Python >= 3.11）。CI 的 `python3` 是 3.11，但開發機的 `python3`
# 可能還是系統的 3.10（本專案 requires-python >= 3.11，開發用的是 .venv / python3.12）。
# 這裡挑第一個「真的 import 得到 tomllib」的直譯器，而不是假設 `python3` 夠新——
# 假設錯的話這支腳本會在開發機上炸，然後大家改成手寫 .in，同步關卡就白做了。
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
