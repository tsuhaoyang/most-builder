#!/usr/bin/env bash
# 依賴安全稽核。CI 與本機跑的是**同一支腳本、同一份豁免清單**——
# 「本機跑的跟 CI 跑的不是同一件事」正是這一整串事故的病根，不在守門上再得一次。
#
# 用法：
#   ./scripts/audit_deps.sh              # 兩份鎖檔都稽核（CI 的行為）
#   ./scripts/audit_deps.sh runtime      # 只稽核 requirements.lock（會進 image 的那一組）
#
# 三份鎖檔的豁免政策**刻意不同**：
#   requirements.lock（production image）→ **無豁免**。會被部署出去的東西不接受消音，
#                                          要放行只能升版或換套件。
#   requirements-build.lock（PEP 517 build backend）→ **無豁免**，理由比上面更強：
#       這組是「產生最終安裝進 image 的 ddm_v2 套件」的那段程式碼，build 時**會被執行**，
#       而且為了 --no-build-isolation 也**實際留在 production image 裡**。
#       一個有洞的 setuptools 在這裡的影響是「打包過程本身可被影響」，不是普通的執行期依賴。
#   requirements-dev.lock（開發/CI 工具鏈）→ 允許 .pip-audit-ignore 的具名豁免，
#                                          每筆需理由 + REVIEW-BY 日期。
set -uo pipefail

cd "$(dirname "$0")/.."

IGNORE_FILE=".pip-audit-ignore"
TARGET="${1:-all}"

if ! command -v pip-audit >/dev/null 2>&1; then
    echo "ERROR: 找不到 pip-audit。安裝：pip install pip-audit" >&2
    exit 2
fi

# --- 豁免清單過期檢查：不讓任何豁免無限期沉默下去 ---------------------------
# 沒有這段的話，一筆「暫時」豁免會活成永久豁免，而且沒有人會發現。
check_review_dates() {
    [ -f "$IGNORE_FILE" ] || return 0
    local today expired=0
    today=$(date +%Y-%m-%d)
    while IFS= read -r line; do
        case "$line" in
            *REVIEW-BY:*)
                local d
                d=$(printf '%s\n' "$line" | sed -n 's/.*REVIEW-BY:[[:space:]]*\([0-9-]*\).*/\1/p')
                if [ -n "$d" ] && [ "$d" \< "$today" ]; then
                    echo "ERROR: $IGNORE_FILE 有過期的豁免（REVIEW-BY: $d < 今天 $today）。" >&2
                    echo "       請重新評估該筆漏洞：能升版就升版，仍要豁免就更新 REVIEW-BY 並補上當前理由。" >&2
                    expired=1
                fi
                ;;
        esac
    done < "$IGNORE_FILE"
    return $expired
}

# --- 讀豁免清單 → --ignore-vuln 參數 ---------------------------------------
IGNORE_ARGS=()
IGNORED_IDS=()
if [ -f "$IGNORE_FILE" ]; then
    while IFS= read -r line; do
        line="${line%%#*}"                       # 去註解
        line="$(printf '%s' "$line" | tr -d '[:space:]')"
        [ -z "$line" ] && continue
        IGNORE_ARGS+=(--ignore-vuln "$line")
        IGNORED_IDS+=("$line")
    done < "$IGNORE_FILE"
fi

# --no-deps：鎖檔已是完整且逐一釘死的清單，不需要（也不該）再連線做依賴解析。
# --strict ：任何一個依賴「稽核不到」就整體失敗。少了它，稽核不到會被當成沒問題，
#            又是一次「零告警不等於安全」。
AUDIT_COMMON=(--no-deps --strict --desc on)

rc=0

if [ "$TARGET" = "all" ] || [ "$TARGET" = "runtime" ]; then
    echo "################ requirements.lock（production image）— 無豁免 ################"
    pip-audit "${AUDIT_COMMON[@]}" -r requirements.lock || rc=1
    echo

    echo "################ requirements-build.lock（PEP 517 build backend）— 無豁免 ################"
    pip-audit "${AUDIT_COMMON[@]}" -r requirements-build.lock || rc=1
    echo
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "dev" ]; then
    echo "################ requirements-dev.lock（開發/CI 工具鏈）################"
    if [ ${#IGNORED_IDS[@]} -gt 0 ]; then
        echo "# 具名豁免（理由見 $IGNORE_FILE）：${IGNORED_IDS[*]}"
    else
        echo "# 目前無豁免項目。"
    fi
    pip-audit "${AUDIT_COMMON[@]}" "${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"}" -r requirements-dev.lock || rc=1
    echo
    check_review_dates || rc=1
fi

if [ $rc -ne 0 ]; then
    echo "稽核未通過。處理順序：(1) 重跑 ./scripts/lock_deps.sh --upgrade-package <pkg> 升到修正版；" >&2
    echo "(2) 升不了才考慮在 $IGNORE_FILE 具名豁免，並寫清楚為何本 app 不受影響 + REVIEW-BY。" >&2
    echo "**requirements.lock 的項目不接受豁免**——那一組會被部署出去。" >&2
fi
exit $rc
