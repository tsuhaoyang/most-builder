"""Locale 碼的唯一定義處（ADR-032 D3.1／I6）。

I6：「語系碼與欄位後綴的對照唯一……不得在程式碼裡各自維護一份對照」——這個模組
是 Phase A 的落點。Phase B 讀 `label_en`／`sentence_text_en` 時，欄位後綴對照
（`zh-TW`→`_zh`、`en`→`_en`）也應從這裡衍生，不要在別處重新硬編一份 locale 清單。

`DEFAULT_LOCALE`：`app_users.locale IS NULL` 時的回退值（D3.1——「未設定」不是
「無語言」）。解析發生在讀取端（`/api/v2/me`），資料庫欄位本身維持 NULL 以便
日後系統預設變更時，未表態的使用者能自動套用新預設。
"""
from __future__ import annotations

from typing import Literal, get_args

Locale = Literal["zh-TW", "en"]

SUPPORTED_LOCALES: tuple[Locale, ...] = get_args(Locale)

DEFAULT_LOCALE: Locale = "zh-TW"


def resolve_locale(stored: str | None) -> Locale:
    """`app_users.locale`（可能 NULL）→ 解析後的有效語系（D3.1 回退規則）。"""
    if stored in SUPPORTED_LOCALES:
        return stored  # type: ignore[return-value]
    return DEFAULT_LOCALE
