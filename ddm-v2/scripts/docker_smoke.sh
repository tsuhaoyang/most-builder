#!/usr/bin/env bash
# 容器 smoke：build image → 起全新 postgres → 起容器 → 打幾個端點。
#
# 為什麼需要這支（而不是「pytest 綠了就好」）：
#   host 上的 pytest **完全不經過 image**。Dockerfile 的 COPY 路徑、依賴安裝方式、
#   entrypoint 的 alembic/seed 流程壞掉時，711 條測試照樣全綠。
#   vault 先例（Docker-Compose-Stale-Baked-Engine-Image）：pytest 91 passed，
#   但容器內跑的是舊引擎，症狀直到手動 rebuild 才現形。
#
# 用法：
#   ./scripts/docker_smoke.sh              # build + smoke
#   SKIP_BUILD=1 ./scripts/docker_smoke.sh # 用既有的 $IMAGE 直接 smoke
#
# 刻意設計成**完全隔離**：獨立 network、用完即棄的 postgres、非預設 port、獨立 image tag。
# 不碰任何既有的 ddm-v2 / ddm-v2-db 容器與 volume（開發機上那套可能正在被使用）。
set -uo pipefail

cd "$(dirname "$0")/.."

IMAGE="${IMAGE:-ddm-v2:smoketest}"
PORT="${PORT:-18877}"
NET=ddm-smoke-net-$$
DB=ddm-smoke-db-$$
APP=ddm-smoke-app-$$
BASE="http://127.0.0.1:${PORT}"
H='X-Username: IEC141289'
rc=0

cleanup() {
    docker rm -f "$APP" "$DB" >/dev/null 2>&1
    docker network rm "$NET" >/dev/null 2>&1
}
trap cleanup EXIT

fail() { echo "SMOKE FAIL: $*" >&2; rc=1; }

# 期望某個端點回特定狀態碼，並印出 body（證據要看得到，不是只看綠燈）
expect_status() {
    local desc="$1" want="$2" got body
    shift 2
    body=$(curl -s -w '\n%{http_code}' "$@")
    got="${body##*$'\n'}"
    body="${body%$'\n'*}"
    printf '%-52s HTTP %s (期望 %s)\n' "$desc" "$got" "$want"
    [ -n "$body" ] && printf '    %s\n' "$(printf '%s' "$body" | head -c 400)"
    [ "$got" = "$want" ] || fail "$desc：期望 $want 得到 $got"
}

if [ "${SKIP_BUILD:-0}" != "1" ]; then
    echo "=== docker build -t $IMAGE ==="
    docker build --network host -t "$IMAGE" . || { echo "BUILD FAILED"; exit 1; }
fi

echo "=== 起全新 postgres（用完即棄）==="
docker network create "$NET" >/dev/null
docker run -d --name "$DB" --network "$NET" \
    -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD=smoke -e POSTGRES_DB=smoke \
    pgvector/pgvector:pg16 >/dev/null
for i in $(seq 1 60); do
    docker exec "$DB" pg_isready -U smoke -d smoke >/dev/null 2>&1 && break
    sleep 1
done
echo "postgres ready after ${i}s"

echo "=== 起 app 容器（entrypoint 會跑 alembic upgrade + seed）==="
docker run -d --name "$APP" --network "$NET" \
    -p "127.0.0.1:${PORT}:8000" \
    -e DATABASE_URL="postgresql+asyncpg://smoke:smoke@${DB}:5432/smoke" \
    -e DDM_SEED_DEMO=true \
    -e DDM_ADMIN_EMPLOYEE_NO=IEC141289 \
    -e DDM_SECRET_KEY=smoke-only-not-a-real-secret-value-32chars \
    "$IMAGE" >/dev/null

# readiness 問「有沒有回 200」，且**帶認證 header**。
# （不帶 header 會拿到 401，用 `curl -f` 會誤判成服務沒起來。）
UP=NO
for i in $(seq 1 90); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' -H "$H" "$BASE/api/v2/rule-sets/active")" = "200" ] \
        && { UP=YES; break; }
    sleep 2
done
echo "service ready after ${i} polls; up=$UP"
if [ "$UP" != "YES" ]; then
    echo "!!! 服務未起來，以下為容器 log："
    docker logs "$APP" 2>&1 | tail -60
    exit 1
fi

echo
echo "=== 容器內套件 vs 鎖檔（requirements.lock + requirements-build.lock）==="
# 要驗的性質是「**image 裡的每一個套件都是我們釘死且驗過 sha256 的**」，
# 所以期望集合是兩份鎖檔的聯集，不只 requirements.lock：
#   Dockerfile 為了關掉 PEP 517 build isolation，必須先把 build 依賴
#   （setuptools/wheel，及其相依 packaging）**實際裝進 runtime 環境**再用
#   --no-build-isolation。它們因此合法地留在 image 裡。這比改動前更嚴格而不是更鬆：
#   改動前 image 裡是 base image 自帶、我們沒釘也沒稽核的 setuptools/wheel；
#   現在是釘死版本 + 驗過 hash + 進 scripts/audit_deps.sh 的無豁免稽核。
#
# 兩類要從期望集合剔除，否則會對出假的差異：
#   colorama  → marker 是 sys_platform == 'win32'，Linux 容器本來就不該有。
#   setuptools/wheel → `pip freeze` **預設就不列**它們（連同 pip、distribute）。
#                      留在期望集合裡會變成「期望有、實際沒有」的假紅。
docker exec "$APP" pip freeze --exclude-editable | tr 'A-Z_' 'a-z-' | sort > /tmp/smoke-installed.txt
cat requirements.lock requirements-build.lock \
    | grep -oE '^[a-zA-Z0-9._-]+==[^ ]+' | tr 'A-Z_' 'a-z-' | sort -u \
    | grep -vE '^(colorama|setuptools|wheel)==' > /tmp/smoke-locked.txt
if diff /tmp/smoke-locked.txt /tmp/smoke-installed.txt; then
    echo "OK：容器內 $(wc -l < /tmp/smoke-installed.txt) 個套件全部來自鎖檔（皆帶 sha256）"
else
    fail "容器內套件與鎖檔不一致（見上方 diff）"
fi

# build 依賴本身也要對版：它們是「產生最終 ddm_v2 套件」的那段程式碼，
# 版本漂掉等於 --no-build-isolation 的保證漂掉（pip freeze 看不到，只能直接問）。
echo "--- build 依賴實裝版本 vs requirements-build.lock ---"
docker exec "$APP" python -c "import setuptools, wheel; print(f'setuptools=={setuptools.__version__}'); print(f'wheel=={wheel.__version__}')" \
    | tr 'A-Z_' 'a-z-' | sort > /tmp/smoke-build-installed.txt
grep -oE '^(setuptools|wheel)==[^ ]+' requirements-build.lock | tr 'A-Z_' 'a-z-' | sort > /tmp/smoke-build-locked.txt
if diff /tmp/smoke-build-locked.txt /tmp/smoke-build-installed.txt; then
    echo "OK：$(tr '\n' ' ' < /tmp/smoke-build-installed.txt)與 requirements-build.lock 一致"
else
    fail "容器內 build 依賴與 requirements-build.lock 不一致（見上方 diff）"
fi

# production image 不該含 dev 工具鏈
devcount=$(docker exec "$APP" pip freeze --exclude-editable | grep -icE '^(pytest|ruff|mypy|coverage)')
echo "production image 內的 dev 工具數量: $devcount（期望 0）"
[ "$devcount" = "0" ] || fail "production image 混入 dev 工具"

# 上面那條只看 **Python** 套件，偵測不到 JS 側。開發機跑過 `npm install` 之後
# `src/frontend/node_modules` 是 130 MB＋（含 vite/esbuild/playwright 與原生二進位），
# 而 `COPY src ./src` 會整棵帶進最終 image——擋住它的只有 `.dockerignore` 一行。
# `.dockerignore` 是**沉默的守衛**：有人手滑刪掉那行，image 會安靜地變胖並夾帶整套
# 建置工具鏈，現有關卡一個都看不到。更糟的是 production image 是在**開發者機器上**
# 建的（compose 的 `image: ddm-v2:202603-rc1`，CI 不 push registry），而 CI/nightly 跑在
# **乾淨 checkout**、那裡根本沒有 node_modules → 驗過的 image 與實際部署的 image 不同。
# 這行把那個沉默前提變成會紅的檢查。
nm=$(docker exec "$APP" find / -xdev -name node_modules -type d 2>/dev/null | head -5)
if [ -n "$nm" ]; then
    printf '    %s\n' "$nm"
    fail "image 內含 node_modules（.dockerignore 的 **/node_modules 失效？）"
else
    echo "image 內 node_modules 數量: 0（期望 0）"
fi

# 同一類問題的 Python 側，而且後果**比 node_modules 嚴重**：node_modules 進 image 是變胖
# 兼夾帶工具鏈，.pyc 進 image 是**會被直接執行的程式碼**。
# CPython 預設的失效判斷（pyc header flags=0）只比對 header 內嵌的來源 mtime+size，而
# `COPY` 保留 mtime——所以工作樹裡一個 header 對得上的
# `src/ddm_v2/auth/__pycache__/identity.cpython-311.pyc` 進了 image，3.11 就會**採用那份
# bytecode 而完全不解析 identity.py**。`PYTHONDONTWRITEBYTECODE=1` 只擋寫入、不擋讀取，
# 所以它擋不住這條（順帶：本檢查同時也是那個環境變數還在的證據）。
# 威脅模型與 node_modules 那條同源：production image 在**開發者機器上**建，
# 任何能寫入工作樹的東西（postinstall script、被投毒的 pytest plugin）都能放這個檔，
# 而 git diff 乾淨、pip freeze 對照乾淨、800+ 個 sha256 全綠、GM=28/CM=29 照樣打得出來。
# 檢查範圍是 image 內三棵**我們自己 COPY 進來的原始碼樹**（site-packages 在 /usr/local，
# 那裡的 .pyc 是 pip 正常編譯的產物，不在本檢查範圍）。
PYCDIRS="/app/src /app/migrations /app/scripts"
pyc=$(docker exec "$APP" sh -c "find $PYCDIRS -name '*.pyc' 2>/dev/null | wc -l" | tr -d '[:space:]')
echo "image 內原始碼樹（$PYCDIRS）的 .pyc 數量: $pyc（期望 0）"
if [ "$pyc" != "0" ]; then
    docker exec "$APP" sh -c "find $PYCDIRS -name '*.pyc' 2>/dev/null | head -5" \
        | while read -r f; do printf '    %s\n' "$f"; done
    fail "image 內含 .pyc（.dockerignore 的 **/__pycache__ 失效？）"
fi

echo
echo "=== 背景 worker（ai_parse_jobs）的部署面 ==="
# 為什麼要有這段：本輪真的踩到了——工作樹裡有 services/v2/parse_job_worker.py，
# 但既有的 ddm-v2:smoketest image 裡**沒有**這個檔（image 比程式碼舊），而上面每一條檢查
# （套件對鎖檔、無 dev 工具、無 node_modules、無 .pyc）連同下面的端點與黃金值
# **全部照樣綠**：那些驗的是「image 內部自洽」，不是「image 是不是由這份程式碼建出來的」。
# 於是「worker 根本沒被部署進去」對所有現有關卡都是隱形的——vault 先例
# Docker-Compose-Stale-Baked-Engine-Image 的同一個病，換了一個模組再犯一次。
WORKER_PY=/app/src/ddm_v2/services/v2/parse_job_worker.py
if docker exec "$APP" test -f "$WORKER_PY"; then
    echo "worker 模組存在: $WORKER_PY"
else
    fail "image 內找不到 $WORKER_PY —— image 比程式碼舊，請重 build"
fi

# 有檔案 ≠ 會跑。真正決定的是容器**當下這組環境變數**解出來的 settings，所以這裡不讀
# 原始碼、直接問容器；docker exec 繼承容器環境，問到的與 app 進程啟動時看到的是同一組。
# 刻意**不比對 interval/batch 的具體數值**：那是後端可調的預設值，寫死在這裡只會變成
# 「每次調參都得順手改 smoke」的假關卡。只驗「有啟用」與「值合理」，數值原樣印出當證據。
echo "--- 容器內實際生效的 worker 設定 ---"
worker_out=$(docker exec "$APP" python -c '
from ddm_v2.settings import get_settings

s = get_settings()
print(f"enabled={s.parse_worker_enabled} interval_s={s.parse_worker_interval_s} batch={s.parse_worker_batch}")

problems = []
if not s.parse_worker_enabled:
    problems.append("worker 被關閉：批次 job 建了不會自己跑，只能靠 API 手動 tick")
if s.parse_worker_interval_s <= 0:
    problems.append("interval_s 必須 > 0")
if s.parse_worker_batch < 1:
    problems.append("batch 必須 >= 1")

if problems:
    print("VERDICT_BAD: " + "；".join(problems))
else:
    print("VERDICT_OK")
' 2>&1)
while IFS= read -r line; do printf '    %s\n' "$line"; done <<< "$worker_out"
case "$worker_out" in
    *VERDICT_OK*)  ;;
    *VERDICT_BAD*) fail "背景 worker 設定不可用（見上）" ;;
    *)             fail "讀不到容器內 worker 設定（settings 沒有 parse_worker_* 欄位？image 比程式碼舊）" ;;
esac

# ⚠️ 尚未涵蓋：**行為**斷言（建一個 job，斷言它未經手動 tick 就自行推進）。
# 刻意不寫進本腳本，因為它在 smoke 環境**無法成立**，硬寫只會多一條永遠紅或永遠被
# 跳過的假關卡（本專案最該避免的東西）。三個前提在此都不存在：
#   1. 建 job 需要一筆已 map 且含 description 的 import 暫存列——smoke 容器沒有匯入資料。
#   2. 建 job 需要 status=active 的 AiDeploymentBundle，而**沒有任何 seed 會建它**
#      （全 repo grep：只有 models/ 與 services/ 提到，seed/ 零命中），
#      所以 POST /api/v2/imports/{id}/parse-jobs 在 smoke 容器必定 503
#      「ai deployment bundle missing or inactive」。
#   3. 要真的推進 item 還需要連得到的 LLM，smoke 容器沒有。
# 在 shell 裡湊出 1+2 只能直接對 DB 灌 fixture，那會讓本腳本綁死 ai_ops 的表結構。
# 行為覆蓋應留在 tests/integration/test_parse_job_worker.py（fixture 屬於那一層）。
# 另有一個獨立障礙：worker 的 logger.info（啟動行、每輪推進筆數）在部署設定下**看不到**
# ——uvicorn 預設 LOGGING_CONFIG 沒有 root 設定，root 停在 WARNING 且無 handler，
# 於是「worker 沒起來」與「worker 正常但沒事做」在容器 log 裡完全長一樣。
# 補上 root logging 設定之後，這裡才可能加一條 log-based 的存活斷言。

echo
echo "=== 端點 ==="
expect_status "GET /api/v2/rule-sets/active" 200 -H "$H" "$BASE/api/v2/rule-sets/active"
expect_status "GET /api/v2/me" 200 -H "$H" "$BASE/api/v2/me"
expect_status "GET / (SPA)" 200 "$BASE/"
expect_status "GET /api/v2/rule-sets/active（未認證）" 401 "$BASE/api/v2/rule-sets/active"

echo
echo "=== 黃金值（容器內的引擎，不是 host 的）==="
gm=$(curl -s -H "$H" -H 'Content-Type: application/json' \
    -d '{"seq":"GM","rule_set_code":"MINIMOST_FACTORY_V2","a0":{"reach_cm":20},"g2":{"g_code":"g_grasp"},"a3":{"reach_cm":25},"p5":{"p_base_code":"p_place_none"}}' \
    "$BASE/api/v2/minimost/calculate")
echo "GM: $gm"
printf '%s' "$gm" | grep -q '"total_tmu":28' || fail "GM 黃金值不是 28"

cm=$(curl -s -H "$H" -H 'Content-Type: application/json' \
    -d '{"seq":"CM","rule_set_code":"MINIMOST_FACTORY_V2","a0":{"reach_cm":25},"g2":{"g_code":"g_touch"},"m3":{"m_components":[{"verb_code":"m_push","distance_cm":45}]},"x4":{"x_code":"x_none"},"i5":{"i_code":"i_none"}}' \
    "$BASE/api/v2/minimost/calculate")
echo "CM: $cm"
printf '%s' "$cm" | grep -q '"total_tmu":29' || fail "CM 黃金值不是 29（推 45cm）"

echo
if [ $rc -eq 0 ]; then echo "✅ docker smoke 全部通過"; else echo "❌ docker smoke 有失敗項（見上）"; fi
exit $rc
