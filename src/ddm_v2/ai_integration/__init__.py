"""外部 ai_service 整合（ADR-037；實作計畫 S2）。

本套件只做「呼叫 ai_service、把回應轉成 MOST 可驗證的建議」。它**不**算 TMU、不寫 DB、
不決定採用——那些在 MOST 既有的 link／compile／engine_gate 與審核流程（S3／S4）。

分層：

- `config`  ：部署層設定與 base URL 安全檢查（SSRF）、服務金鑰遮蔽。
- `client`  ：HTTP 呼叫 `POST /v1/llm/structured-completion`；逾時、重試、熔斷、錯誤分類。
- `mapper`  ：ai_service 回應 → `MotionSuggestion`（allow-list、上限、不採信欄位降為提示）。
- `schema`  ：ai_service 輸出 schema 的 MOST 端複本（sha256 釘值）。
- `ports`   ：`WiParserPort` 與輸入輸出型別（S3 起由 `wi_ai_service` 依賴這一層）。
- `adapter` ：`AiServiceWiParser`＝`WiParserPort` 的第一個實作（逐句呼叫）。
- `fake`    ：`FakeWiParser`，供下游單元測試使用，不走 HTTP。

S2 完成時沒有任何現有路由依賴本套件；開關 `DDM_AI_SERVICE_ENABLED` 預設關閉。
"""
