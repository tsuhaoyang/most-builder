# ADR-034：語言感知錯誤契約 — 結構化錯誤碼與前端在地化

- **狀態**：**accepted**（2026-09-03，User 核可）
- **日期**：2026-09-03
- **決策者**：Howard（IE，裁決範圍與權威模式）＋ 架構師（論證與契約提案）
- **關聯**：
  - [ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（加法演進與契約穩定——本 ADR 會**改變錯誤信封形狀**，屬受管制的契約變更，見 §5 風險）
  - [ADR-032](ADR-032-bilingual-ui-and-data-label-layer.md)（雙語 UI 與資料標籤層——本 ADR **啟動其 D9(3) 明確標為「本輪不做」的項目**，觸發條件 (a) 成立：即將有英文語系一般使用者）
  - 業界標準：**RFC 9457 Problem Details for HTTP APIs**（取代 RFC 7807）；前端 **react-i18next / ICU MessageFormat**（複數、性別、參數插值）

---

## 1. 脈絡

### 1.1 為什麼現在決（ADR-032 D9 的觸發條件已成立）

ADR-032 D9(3) 把「錯誤訊息／API i18n」明確列為**本輪不做**，並記下觸發條件：
> (a) 有英文語系的一般使用者回報看不懂錯誤；或 (b) 需要對外開放 API 給第三方。

User 於 2026-09-03 裁決：**「中英文切換務必以最業界標準來做，因為未來的使用者會有外國人」**。
這使觸發條件 (a) 成立——不是回報，而是**預先確立**外國使用者是既定需求。因此本項從
「本輪不做」升級為需要獨立決策，本 ADR 即為該決策。

### 1.2 程式碼現況（2026-09-03 實測，非推測）

錯誤體系目前是**三種信封並存且不一致**：

1. **`DomainError` 家族**（`src/ddm_v2/exceptions.py` L11-45）：`DomainError(message, detail)` 為基別，
   子類 `NotFoundError`/`ValidationError`/`ConflictError`/`ForbiddenError`/`UnauthorizedError`。
   由 `api/error_handlers.py::register_exception_handlers` 產出統一信封
   `{error:{code,message,detail}}`（schema：`schemas/common.py` `ErrorDetail`/`ErrorResponse`）。**這是治理良好的一條。**
2. **裸 `HTTPException`**：route 層 **124 處 / 16 檔** 直接 `raise HTTPException(detail=...)`，
   **繞過 DomainError 信封**，產出 FastAPI 原生 `{detail}`（有時是 str、有時是帶 code 的 dict）。
3. **FastAPI 預設 422**：全庫**無** `RequestValidationError` 自訂 handler，Pydantic request 驗證
   走預設，`msg` 為**英文**。與 service 層中文自訂錯誤並存 → **同一畫面中英夾雜**。

錯誤碼：約 **33 個**穩定字串碼（大寫底線常數），但**無中央 registry**，散在 handler／route／service
三層。`error_handlers.py` L54-56 甚至靠 `message.lower()` 字串比對反推 code（如比對「published」／
「time_source」）——**這在 i18n 後會直接壞掉**（訊息一翻成英文，字串比對就失配）。

中文綁死程度：**嚴重**。message 幾乎都是中文 f-string 直寫在 raise 點，且**變數被插進中文句子**
（如 `f"模組不存在：{module_id}"`、`f"simo_pair_index={pi!r} 須指向..."`）。前端就算拿到 code，
也**無法用參數重建英文句**，因為參數已經被格式化進中文字串裡。

前端：`ApiError`（`src/frontend/src/shared/api/client.ts`）已能取 `code`（L20-24），但
`humanMessage`（L28-33）與 `workbench-v3/api.ts::apiErrorMessage`（L130-160）都只是
**「不吐原始 JSON」的解包，不是翻譯層**。i18n 錯誤外殼 key 已備妥（`zh-TW.ts`／`en.ts` 各 44 個
`{{message}}`），但插進去的 message 本體是**後端未翻譯原字串**。errorCode→i18n 對照表
**完全不存在**（grep `errorCatalog`/`codeToMessage`/`errors.` 皆 0 命中）；唯一特例是
`dictionary/api.ts` 的 `describeInUse()` 只人性化了 `RULE_SET_IN_USE` 一個碼。另有 5-6 個
呈現點連 i18n 外殼都沒有，直接 `setErr((e as Error).message)`。

### 1.3 業界標準（本 ADR 的取捨依據）

- **後端錯誤格式：RFC 9457 Problem Details**。以 `application/problem+json` 回傳，攜帶
  **機器可讀、穩定的錯誤識別**（本 ADR 採 `code` 欄）＋**結構化擴充成員**（參數）。
  這讓客戶端能對錯誤採取程式化動作，而非解析人類語句。
- **在地化的位置：後端回穩定 code + 結構化參數，前端依 locale 用 message catalog 組句。**
  這是 i18n 社群的主流共識，且與 ADR-032 D3.3「API 語言中立、語言選擇發生在呈現層」**完全一致**。
- **禁止字串串接組句**：ICU MessageFormat 的核心告誡是「string concatenation is the original
  localization sin」——英文能動、德文靜默失敗、阿拉伯文直接壞。複數／性別／語序差異必須由
  catalog 的 ICU 語法處理，不能靠前端拼字串。

---

## 2. 決策

### D1 錯誤契約統一為單一信封（RFC 9457 對齊，加法相容）

**所有** API 錯誤回應收斂到單一信封，語意對齊 RFC 9457 Problem Details，但**保留專案既有
`{error:{...}}` 外層以維持加法相容**（不強制切換 content-type 為 `application/problem+json`，
除非 §D5 對外開放階段需要）：

```jsonc
{
  "error": {
    "code": "SIMO_PAIR_INVALID",     // 穩定、機器可讀、大寫底線；前端 i18n key 的來源
    "message": "…",                   // fallback 用途的預設語言（zh-TW）人類訊息，非權威顯示來源
    "detail": {                        // 結構化參數（RFC 9457 擴充成員），前端組句用
      "row_id": "…", "simo_pair_index": 3, "field": "…"
    }
  }
}
```

- `code` 是**唯一權威識別**；前端以它查 i18n catalog。
- `message` 降級為**開發者可讀的預設語言 fallback**，不再是使用者顯示的權威來源。
- `detail` 攜帶**結構化參數**（不是格式化後的句子）；前端用它填 ICU catalog 的占位符。

### D2 在地化發生在前端（延續 ADR-032 D3.3，不做內容協商）

**不做** `Accept-Language` 內容協商、**不**讓後端 message 隨 locale 變。理由與 ADR-032 D3.3 相同：
語言中立回應可被快取、可被 e2e 穩定斷言、不需 `Vary`。前端依既有 locale（`react-i18next`）
用 `code` + `detail` 參數，從雙語 catalog 組出顯示句。

> **唯一例外（沿用 ADR-032 D3.3 的預留）**：伺服器**生成的文件**（匯出、未來 PDF）若需在地化，
> 以顯式 `?lang=` 參數取語言，不隱含讀使用者屬性。錯誤訊息不屬此類。

### D3 建立中央錯誤碼 registry（後端單一真相）

- 新增 `src/ddm_v2/errors/registry.py`（或等價位置）：以 **enum／常數集中定義** ~33 個 code，
  取代目前散落三層的字面字串。
- **移除 `error_handlers.py` 靠 `message.lower()` 反推 code 的脆弱耦合**——code 必須由 raise
  點顯式攜帶，不得從人類訊息反推。
- registry 是「code 的權威清單」；前端 catalog 的 key 必須與它逐一對應（§D6 有機械檢查）。

### D4 錯誤參數結構化（把變數從中文句子裡抽出來）

凡是 message 內嵌變數的錯誤，變數必須改放進 `detail`：

- ❌ 現況：`raise NotFoundError(f"模組不存在：{module_id}")`
- ✅ 目標：`raise NotFoundError(code=NOT_FOUND, detail={"resource": "module", "id": module_id})`

前端 catalog：
```jsonc
// en
"errors.NOT_FOUND.module": "Module not found: {id}"
// zh-TW
"errors.NOT_FOUND.module": "模組不存在：{id}"
```

**這是本 ADR 工作量最大、風險最高的一塊**（見 §5）。

**D4 實作補記（2026-09-03，階段 B 啟動）**：A4 收斂時部分 raise 點已順帶結構化
（如 `vocab.py` 已帶 `resource`/`id`、`synonyms`/`calculate` 已帶 `rule_set_code`），
但**不一致**——`rule_set.py`／`worksheet.py`／`motion_module.py` 多數仍只帶 `_compat_detail`。
階段 B 的工作是**補齊一致性**，並固定以下**結構化參數命名規範**（前端 catalog key 依此對應，§C 對齊）：

| 錯誤類型 | 必備 detail 鍵 | 範例 |
|---|---|---|
| 資源不存在（NOT_FOUND） | `resource`（資源型別字串）＋ 該資源的識別鍵 | `{"resource":"rule_set","rule_set_code":code}`、`{"resource":"module","id":str(id)}`、`{"resource":"parse_run","run_id":str(id)}` |
| 權限（FORBIDDEN） | `resource`＋`action`（＋必要時 `required_role`／`current_roles`） | `{"resource":"motion_template","action":"modify"}` |
| 資源衝突（CONFLICT） | 沿用既有結構化鍵 | `{"references":{...}}`、`{"existing":{...}}` |
| 語意/狀態機（BAD_REQUEST/VALIDATION） | 依錯誤帶對應參數（`field`／`param`／`row_index`／`seq_no`／`row_id`） | `{"row_index":i,"field":"category"}` |

**識別鍵命名固定**：資源自己的自然鍵優先（`rule_set_code`／`run_id`／`worksheet_id`／`module_id`），
無自然鍵者用泛用 `id`（值一律 `str()`）。**規範一旦定案即為契約（I3 精神）**，前端 catalog
以 `errors.<CODE>.<resource>` 為 key、用這些參數插值；後端新增同類錯誤須沿用同鍵名。

**不變的三件事（階段 B 純加法）**：不動 `_compat_detail`（KI-034-1 相容仍靠它）、不動 `code`、
不動 HTTP 狀態碼、不動信封形狀。階段 B 只在 `detail` 內**新增**結構化欄位。

### D5 分階段交付（每階段可獨立驗收，避免大爆炸式重構）

| 階段 | 內容 | 完成判準 | 依賴 |
|---|---|---|---|
| **A：信封統一 + registry** | 124 處裸 `HTTPException` 收斂進 DomainError 信封；建立中央 code registry；移除 `message.lower()` 反推；422 加自訂 `RequestValidationError` handler 統一形狀 | 所有錯誤回應皆為 `{error:{code,message,detail}}`；grep 無裸 `HTTPException(detail=...)` 於 route 層；既有 e2e 全綠（錯誤形狀變更的回歸） | 無 |
| **B：參數結構化** | 把中文 message 內嵌變數重構為 `detail` 結構化欄位（依 code 逐一處理） | 每個帶變數的 code，其 `detail` 含可重組句子所需的全部參數；`message` 僅作 fallback | A |
| **C：前端 i18n catalog** | 建 errorCode→i18n key 對照層；收斂 `humanMessage`／`apiErrorMessage`／裸 `.message` 三條路徑成單一入口；補齊 5-6 個裸露呈現點；en／zh-TW catalog 補齊 ~33 碼雙語文案（ICU 語法處理複數／語序） | 切到 en 後，錯誤訊息**無中文殘留**；查無 code 時 graceful fallback 到後端 `message`；e2e 雙語錯誤斷言全綠 | A、B |

- **A 可獨立上線**（信封一致本身就是既有技術債的修復，即使不做 i18n 也有價值）。
- **C 依賴 A、B**（沒有穩定 code 與結構化參數，前端無法 language-aware 組句）。

### D6 防漂移機械檢查（呼應 ADR-032 D8 的精神）

- **後端**：後設測試斷言 registry 的每個 code 都有對應的 handler 對映與預設 message，且無孤兒 code。
- **前端**：測試斷言 `en.ts`／`zh-TW.ts` 的 `errors.*` key 集合**與後端 registry 的 code 集合一致**
  （缺 key 或多餘 key 皆紅）。這確保新增後端錯誤碼時，雙語文案不會靜默落後。
- **CI 守衛**：擋新的裸 `HTTPException(detail=...)` 進 route 層（回歸到多信封）。

---

## 3. 架構不變式（違反即否決）

**I1 — 不碰 TMU／MOST engine／lexicon。** 錯誤契約重構只影響錯誤回應路徑，
`most_engine/`、`nlp/lexicon.py`、`template_matching.py`、TMU 計算零改動。
可機械檢查：本 ADR 三階段對 `most_engine/` 的 diff 應為空。

**I2 — 中文使用者的既有錯誤語意不得退化。** 既有 zh-TW 錯誤訊息在 catalog 化後，
顯示內容位元級等價（或更清楚）。判準：既有中文 e2e 錯誤斷言全數不變且全綠。

**I3 — `code` 是穩定契約，不得隨意更名。** 一旦 registry 定案，code 字串進入對外契約
（前端 catalog key、未來第三方 API），更名等同破壞性變更，須走加法演進（ADR-011）。

**I4 — 前端不得回退到「把中文當英文顯示」。** 查無 catalog key 時，fallback 到後端 `message`
（預設語言 zh-TW）是可接受的降級，但**不得在 en locale 下把中文 message 偽裝成英文**——
與 ADR-032 D7／`pickNarrative` 的同一條紅線。

---

## 4. 為什麼是這個方案（替代方案與否決理由）

- **否決「後端做 `Accept-Language` 內容協商」**：違反 ADR-032 D3.3；破壞快取與 e2e 穩定性；
  且需維護後端雙語 message catalog（與前端重複）。
- **否決「維持現狀、只在前端硬翻部分常見錯誤」**：等同 `describeInUse()` 的單點特例擴散，
  無 registry 對應、無防漂移，新錯誤碼會靜默落後；且無法處理參數已被格式化進中文句的錯誤。
- **採「後端穩定 code + 結構化參數，前端 catalog 組句」**：對齊 RFC 9457 與 i18n 主流共識，
  延續 ADR-032 既定的「API 語言中立、呈現層選語言」，前端外殼已備妥，邊際成本集中在後端契約重構。

---

## 5. 風險與取捨（誠實記錄）

- **blast radius 大**：階段 A 動 124 處 raise 點、階段 B 逐 code 重構參數，改變 API 錯誤契約形狀，
  對已依賴 `{detail}` 形狀的前端呼叫點與 e2e 有回歸風險。**緩解**：D5 分階段、D6 機械檢查、
  每階段跑既有 e2e 作回歸閘。
- **契約穩定性（ADR-011）**：錯誤信封形狀改變是受管制的變更；階段 A 完成前，前端須同時吃
  新舊兩種信封（`toError` 已能吃 `d?.error ?? d?.detail`，過渡期相容）。
- **工作量**：ADR-032 D9 原話「規模與風險不亞於全部三個 Phase」，實測證實。**這不是一次性小改**，
  必須按 D5 階段推進，不可當成 Phase 2 收尾硬塞。
- **不在本輪範圍**：後端 domain 例外訊息目錄化的**內容翻譯品質覆核**（哪句英文更道地）可比照
  ADR-032 的 i18n review 流程另行治理；本 ADR 只定契約與機制。

---

## 6. 落地檢查清單（核可後執行，本 ADR 不含實作）

1. 階段 A：`errors/registry.py`、收斂裸 `HTTPException`、422 handler、移除 `message.lower()` 反推、CI 守衛。
2. 階段 B：逐 code 把變數移入 `detail`；補後設測試（每個 code 的參數完整性）。
3. 階段 C：前端 `errorCatalog` 對照層、單一取訊息入口、補裸露點、雙語 ICU catalog、key 一致性測試。
4. 每階段：`PYTHONPATH=src pytest`（後端）＋ `npm run typecheck`／`build`／`typecheck:e2e`／相關 Playwright（前端）作回歸閘。
5. 於 ADR-032 D9(3) 加一行交叉引用指向本 ADR（標記該項已由 ADR-034 承接）。

---

## 7. 已知問題（Known Issues，不可忽略）

### KI-034-1：階段 A2 改變 Pydantic request 驗證 422 的回應形狀（契約變更）— ✅ 已收斂（resolved，階段 C4，2026-09-04）

**發現時間**：2026-09-03（階段 A1-A3 實作複核，審核員實跑 integration 測試佐證）。

**問題**：A2 新增的 `RequestValidationError` handler 把 FastAPI 預設的**頂層 `{detail:[...]}`
陣列**收斂為 `{error:{code,message,detail:{errors:[...]}}}`。這改變了既有 API 錯誤契約——
多處既有 integration 測試與（待查的）前端呼叫點把頂層 `detail` 當**陣列**讀。

**實證**（審核員實跑，DDM 專屬 db 於 port 15432，`DATABASE_URL=postgresql+asyncpg://howard:111111@localhost:15432/ddm_v2_most`）：
`tests/integration/test_migration_v2_0022_category_and_template_ruleset.py` 在 A2 套用後
**6 failed, 22 passed**，失敗全為 `KeyError`（斷言 `resp.json()["detail"]` 迭代，頂層 `detail` 已不存在）。
此回歸**不會被 unit 測試捕捉**（`pytest tests/unit` 仍 1570 passed）——它只在需要 DB 的
integration 層可見，正是「1570 passed 綠燈」掩蓋契約變更的典型陷阱。

**本輪處置（B 方案：過渡期雙形狀相容）**：A2 handler **同時保留頂層 `detail`＝原始 errors 陣列**
（與 FastAPI 預設等價），與新的 `error` 信封並存。既有讀頂層 `detail` 的測試與前端呼叫點不破壞；
新前端可改讀 `error`。此為過渡期妥協，不是終態。

**待辦（不可忽略）**：
1. **盤點**所有讀頂層 `detail`（陣列或 `detail.code`）的呼叫點——後端 integration 測試、前端
   `apiErrorMessage`／`humanMessage`／各呼叫處——列成遷移清單。
2. 階段 C 前端 catalog 完成、呼叫點全數遷移到 `error` 信封後，**移除頂層 `detail` 相容欄位**，
   並更新受影響的 integration 測試斷言為 `resp.json()["error"]["detail"]["errors"]`。
3. 移除相容欄位屬**破壞性契約變更**，須依 ADR-011 加法演進評估，並在移除當次跑**完整
   integration 測試**（非僅 unit）作回歸閘。
4. 環境註記：CI／開發如需驗證此類契約變更，**必須跑 integration（需 DB）**；僅跑 unit 會漏。

**風險若不處置**：頂層 `detail` 與 `error` 兩個真相長期並存 → 前端可能各自依賴不同欄位，
形成 ADR-024 事後剖析所述「同一件事兩個答案」的漂移。故 KI-034-1 必須在階段 C 收斂，不得長存。

**收斂處置（階段 C4，2026-09-04，已完成）**：C1-C3 前端已全數改讀 `error` 信封（不依賴頂層
`detail`），本階段一次移除後端所有過渡期相容欄位，錯誤契約徹底收斂為單一
`{error:{code,message,detail}}` 信封（**破壞性契約變更**）。

- **`error_handlers.py`**：(a) `_envelope` 移除 `_compat_detail` → 頂層 `detail` 的還原分支；
  (b) `RequestValidationError` handler 移除 `content["detail"]=errors` 頂層相容行（原始 errors
  陣列續存於 `error.detail.errors`，形狀不變）。
- **route 檔移除 `_compat_detail`**（15 檔、~148 處），分三形狀：(A) 純字串型直接刪鍵
  （`error.detail` 保 code/resource/id，`error.message` 已載訊息）；(B) `{**compat, "_compat_detail":
  compat}` → `{**compat}`（巢狀鍵已 spread）；(C) **compat-only 結構化 spread**（worksheet.py
  兩處 SimoPairInvalid／RowSequenceError、wi_set.py instantiate 一處）改為 `detail={**compat}`，
  確保 `error.detail` 仍含 `seq_no/row_id/message/code`——這是最高風險點（R1），未只刪鍵。
- **治理紅線守住**：I1 未碰 `most_engine`/TMU/lexicon，engine `SequenceError.e.code` 維持動態讀取；
  I2 `error.message` 中文 f-string 位元級不退化；I3 `code` 未更名。
- **測試遷移（77 斷言、15 檔）**：字串子串 → `error.message`；`detail.code` → `error.code`（更穩定）；
  巢狀 `existing`/`references`/`seq_no`/`row_id` 及 helper → `error.detail[...]`；422 陣列
  `for e in json()["detail"]` → `for e in json()["error"]["detail"]["errors"]`。附帶修正 5 處
  `"detail" in resp.json()` 存在性斷言為 `"error" in ...`。**註**：`require_role`／`current_user`
  的 401/403 走 FastAPI 原生 `HTTPException`（頂層 `{detail:str}`，非 DomainError 信封，屬 auth 層
  非本 ADR 契約），該類斷言（如 export_import「analyst」403）維持讀頂層 `detail`。
- **回歸閘證據**：`pytest tests/unit` 1577 passed；`pytest tests/integration`（全量、需 DB，port
  15432）**600 passed, 1 skipped, 0 failed**；`scripts/core_logic/run_all.py` 全通過（88+26+60，
  證 I1）；前端 `npm run typecheck` + `npm run build` 皆綠（C1-C3 已遷移，不受影響）；
  `grep -rn _compat_detail src/` 於程式碼 0 命中（僅餘 docstring 描述本次移除）。

**Follow-up（不阻擋 C4）**：`error.detail.code` 相對 `error.code` 為冗餘（dict-spread 型會兩處都有
code）；可於後續收斂 `error.detail` 只留非-code 的結構化參數，屬純加法/減法整理，另案處理。
