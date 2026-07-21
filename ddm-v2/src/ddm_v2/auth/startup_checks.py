"""身分設定的啟動期安全告警（ADR-023 D7 / D7b · C-1）。

**為什麼獨立成一個模組**：D7 把 gateway 信任警告掛在 `main.create_app()` 裡，等於
「任何不走 factory 的入口都默默拿不到警告」——而 `scripts/preview_server.py` 正是這種
入口（它自己組 FastAPI 逐一 include_router），也正是 CLAUDE.md 的主要啟動方式。
警告搬到這裡後，**每一個入口都只需呼叫 `warn_if_identity_config_insecure()` 一次**，
且 `tests/unit/test_startup_security.py` 會掃描所有 `uvicorn.run(...)` 的入口，
確認它們都呼叫了——新增入口而忘了叫，測試會紅，不會再默默失去警告。

兩個獨立的告警來源（可同時成立，各發一筆）：

1. **gateway 信任前提**：`DDM_AUTH_MODE=gateway`（預設）時 `auth/identity.py`
   無條件採信入站的 `X-Username`，安全性 100% 依賴「本服務只經 gateway 可達」。
2. **dev override**：`AUTH_DEV_USER` 有值時（且非 production），**連 header 都不用偽造**
   ——所有請求一律是那個員編。本地預覽預設就是 admin 員編，所以只要 port 綁出
   loopback 之外，等同開放零憑證 admin。

**純 log**：不擋啟動、不改變任何行為（本機開發與 CI 必須照常跑）。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 營運者用來「宣告本服務只經可信 gateway 可達」的環境變數。設了就不再發 C-1 警告。
# 刻意只當旗標、不做來源 IP/CIDR 比對：本專案的部署防線是拓撲（Traefik ForwardAuth ＋
# 只綁 loopback 的 port），在 app 內再加一層 IP 比對會讓本機開發與 CI 破功，收益卻有限。
TRUSTED_GATEWAY_ENV = "DDM_TRUSTED_GATEWAY"

DEV_USER_ENV = "AUTH_DEV_USER"


def _is_production() -> bool:
    return os.getenv("ENV", "development").lower() in {"production", "prod"}


def _warn_if_gateway_trust_unconfirmed() -> None:
    """gateway 模式且未宣告可信來源 → WARNING（ADR-023 D7 / C-1）。

    這個前提在程式碼裡看不出來，所以至少要在啟動時講出來。已宣告時改記 INFO：
    「已宣告」本身是稽核上有意義的事實（且它是**宣告**不是驗證），不該完全無痕。
    """
    if os.getenv("DDM_AUTH_MODE", "gateway").lower() != "gateway":
        return
    if os.getenv(TRUSTED_GATEWAY_ENV):
        logger.info(
            "%s 已宣告：略過 gateway 信任警告。注意這是**營運者的宣告**，不是驗證——"
            "本服務不會比對來源 IP，仍會無條件採信入站的 X-Username header。",
            TRUSTED_GATEWAY_ENV,
        )
        return
    logger.warning(
        "DDM_AUTH_MODE=gateway：本服務**信任入站的 X-Username header** 作為身分來源，"
        "沒有任何憑證檢查。請確認本服務只經 gateway（Traefik ForwardAuth）可達；"
        "若 app port 曝露到 loopback 以外，等同開放無認證的 admin 存取。"
        f"確認後設 {TRUSTED_GATEWAY_ENV}=1 可關閉本警告；"
        "需直接對外請改用 DDM_AUTH_MODE=verify。"
    )


def _warn_if_dev_identity_override() -> None:
    """`AUTH_DEV_USER` 有值 → WARNING：本服務以該員編免認證運作（D7b / C-1 殘留）。

    比 gateway 前提更嚴重：gateway 模式下攻擊者至少要偽造一個 header，dev override
    連偽造都不必——`resolve_identity()` 在無 header/無 session 時直接回傳這個身分。
    production 下 `identity.py` 會忽略它，故只在非 production 發（並說明已被忽略）。
    """
    dev_user = (os.getenv(DEV_USER_ENV) or "").strip()
    if not dev_user:
        return
    if _is_production():
        logger.warning(
            "%s=%s 已設定但 ENV=production → 被忽略（identity.py 不在 production 套用 "
            "dev override）。請把它從 production 環境移除以免誤導。",
            DEV_USER_ENV, dev_user,
        )
        return
    logger.warning(
        "%s=%s：本服務以 %s 的身分**免認證**運作——所有請求都會被當成這個員編，"
        "連 X-Username header 都不需要偽造。請確認服務 port 只綁 loopback；"
        "要對外提供服務請清掉 %s 並改用 gateway/verify 模式。",
        DEV_USER_ENV, dev_user, dev_user, DEV_USER_ENV,
    )


def warn_if_identity_config_insecure() -> None:
    """所有入口（`create_app()` 與任何自組 app 的 script）都必須呼叫的啟動期告警。"""
    _warn_if_gateway_trust_unconfirmed()
    _warn_if_dev_identity_override()
