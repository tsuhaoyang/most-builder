"""v2 詞彙庫主數據 API 契約（FE-5）。

字串一律 strip——詞彙名是英文敘事的受詞來源（`most_engine/narrative_en._noun`），
存進一筆純空白的名字，Phase C 之後會在**讀取時**組句才爆（讀模組/版本/工作表 500），
毒源卻在 `work_vocab_items`，改被讀的那筆資料修不好。所以在入口擋掉：

- `name_zh`：strip 後不得為空 → 422。詞彙沒有中文名等於沒有名字，回退鏈也救不了。
- `name_en`：strip 後為空 → **正規化為 None**（不是 422）。「清掉英文名」是合法操作，
  `name_en or name_zh` 的回退鏈本來就吃 None。
- `external_code`：只 strip，空字串留給 route 的 `or None` 收（維持既有清空語意）。
"""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints

VocabKind = Literal["object", "component", "tool", "from", "to", "hand"]


def _blank_to_none(v: str | None) -> str | None:
    return v or None


Stripped = Annotated[str, StringConstraints(strip_whitespace=True)]
NameZh = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
NameEn = Annotated[Stripped | None, AfterValidator(_blank_to_none)]


class VocabItemIn(BaseModel):
    kind: VocabKind
    name_zh: NameZh
    name_en: NameEn = None
    external_code: Stripped | None = None
    source_system: str = "local"
    site_id: uuid.UUID | None = None


class VocabPatchIn(BaseModel):
    name_zh: NameZh | None = None
    name_en: NameEn = None
    external_code: Stripped | None = None
    is_active: bool | None = None


class VocabItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    name_zh: str
    name_en: str | None
    external_code: str | None
    source_system: str
    is_active: bool
