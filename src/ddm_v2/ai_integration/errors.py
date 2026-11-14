"""ai_service 呼叫結果的錯誤分類（MOST 內部；ADR-037 D2）。

這裡的 `AiServiceErrorKind` 是 **MOST 內部的分類**，不是對前端的錯誤碼：S2 沒有任何路由把它
送出去。S3 接上 nl-draft 時，降級原因以 routing reason／provenance 呈現；需要對外報錯的
情形再登記進 `ddm_v2.errors.registry.ErrorCode`，並補 zh-TW／en 訊息（ADR-034、ADR-032）。

ai_service 的錯誤一律依 `error.code` 分類，**不解析 message**（ai_service api spec §2.2：
message 是英文、不本地化、不保證穩定）。ai_service 的 `error.message` 不原樣轉給使用者
（ADR-037 D7）；`AiServiceError` 只保留 upstream code 與 HTTP 狀態。
"""
from __future__ import annotations

from enum import Enum


class AiServiceErrorKind(str, Enum):
    """呼叫 ai_service 失敗的分類；每一種都對應「降級到 rule_based」，差別在是否值得重試。"""

    DISABLED = "disabled"  # 開關關閉或設定不完整（不嘗試連線）
    MISCONFIGURED = "misconfigured"  # 設定存在但不合法（base URL 未通過安全檢查、金鑰太短）
    CIRCUIT_OPEN = "circuit_open"  # 熔斷中，不嘗試連線
    UNREACHABLE = "unreachable"  # 連線失敗、DNS 失敗、連到非預期位址
    TIMEOUT = "timeout"  # 總時限或 upstream 504
    RATE_LIMITED = "rate_limited"  # 429 ADMISSION_REJECTED
    AUTH = "auth"  # 401／403：金鑰或身分 header 被拒
    BUNDLE_NOT_RUNNABLE = "bundle_not_runnable"  # 409 BUNDLE_NOT_RUNNABLE（bundle 不是 shadow／active）
    UPSTREAM = "upstream"  # 其他 5xx（provider 暫時失敗）
    DEPLOYMENT = "deployment"  # 503 部署不一致（prompt 資產、renderer、tool schema、provider 未設定）：重試不會變好
    MODEL_OUTPUT_INVALID = "model_output_invalid"  # 422 SCHEMA_VALIDATION_FAILED（重試後仍不合 schema）
    REQUEST_REJECTED = "request_rejected"  # 其他 4xx（請求不合 ai_service 契約——MOST 端的 bug）
    CONTRACT_MISMATCH = "contract_mismatch"  # 回應形狀或 contract_version 不符 MOST 預期
    RESPONSE_TOO_LARGE = "response_too_large"


# 值得在同一次請求內重試的分類（其他分類重試也不會變好，或會放大成本）
#
# TIMEOUT 刻意不重試：ai_service 可能已經跑完 LLM，只是回應晚到；重送會重複計費，且 ai_service
# 自己也有一層重試（`retry_count`），兩層相乘（ADR-037 D8 成本）。
RETRYABLE_KINDS = frozenset({AiServiceErrorKind.RATE_LIMITED, AiServiceErrorKind.UPSTREAM})

# 計入熔斷失敗次數的分類：服務本身不健康。呼叫端錯（REQUEST_REJECTED）、模型輸出錯、
# 准入拒絕不算——那些不代表服務掛了，熔斷只會讓正常請求一起失敗。
CIRCUIT_COUNTED_KINDS = frozenset(
    {
        AiServiceErrorKind.UNREACHABLE,
        AiServiceErrorKind.TIMEOUT,
        AiServiceErrorKind.UPSTREAM,
        AiServiceErrorKind.DEPLOYMENT,
    }
)


class AiServiceError(Exception):
    """一次 ai_service 呼叫的失敗。訊息只含分類與 upstream code，不含金鑰、URL 或 upstream message。"""

    def __init__(
        self,
        kind: AiServiceErrorKind,
        *,
        upstream_code: str | None = None,
        http_status: int | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        self.kind = kind
        self.upstream_code = upstream_code
        self.http_status = http_status
        self.retry_after_s = retry_after_s
        parts = [kind.value]
        if upstream_code:
            parts.append(upstream_code)
        if http_status is not None:
            parts.append(f"http={http_status}")
        super().__init__(":".join(parts))
