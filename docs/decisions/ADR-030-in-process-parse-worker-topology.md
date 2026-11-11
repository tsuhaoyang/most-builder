# ADR-030: ai_parse_jobs 背景 worker 的部署拓撲——in-process、預設開啟（過渡）

**狀態：** proposed（待 User 核可；核可前本文件只描述現況與條件，不追認為終局架構）
**日期：** 2026-08-15
**關聯：** [ADR-027](ADR-027-domain-evolution-versioning-and-ai-readiness.md) §6（「Dedicated worker 承載
durable work」——本 ADR 記錄的正是對 §6 的**暫時偏離**）、§7（達條件再物理拆分的同一原則）、
[ADR-026](ADR-026-wi-ai-parser-pipeline-boundary.md)（WI AI Parser bounded context）、
`docs/llm/wi-ai-parser-implementation-spec.md` §12–13（jobs schema 與 L4 批次邊界）、
worklog D3-008（本決策原本唯一的紀錄位置——一列表格，這不是部署拓撲決策該有的能見度）

## 脈絡

L4 交付 `ai_parse_jobs` 時只有 tick 邏輯與 4 個端點：job 建了**不會自己跑**，要靠
API 手動 tick。2026-08-15 補上 `services/v2/parse_job_worker.py`——lifespan 起一個
asyncio Task 週期呼叫 `parse_job_service.tick_job`，並且**預設開啟**
（`DDM_PARSE_WORKER_ENABLED` 未設＝跑；理由：預設關閉的守門等於沒做）。

這與 ADR-027 §6 寫的「Dedicated worker 承載 durable work；FastAPI `BackgroundTasks`
不作數百列 job queue」**不一致**：in-process asyncio task 不是 BackgroundTasks，但也
不是 dedicated worker——它跟 API 共享 event loop、共享行程生命週期、共享資源上限。
這個偏離當時只記在 worklog Decision Log（D3-008）一列，等於把一個部署拓撲決策藏在
交付追蹤表裡。本 ADR 把它抬到正確的能見度，並寫清楚：**為什麼現在可以這樣、什麼
時候必須不再這樣**。

## 決策（提案）

**維持 in-process、預設開啟，作為明確標記的過渡方案**，附帶以下不可省略的前提：

1. **狀態機與計算全在 `parse_job_service`**：worker 只負責排程。抽離成 dedicated
   worker 時搬的是「驅動迴圈」，不是業務語意——這是抽離成本低的關鍵，也是現在敢
   選過渡方案的理由。
2. **多實例安全靠 DB，不靠拓撲**：item 認領走 `FOR UPDATE SKIP LOCKED`＋lease＋
   attempt 上限（CLAIM_SQL）。N 個行程同時輪詢是浪費（見下），但不是正確性問題。
3. **毒 job 不得傷及 API**（2026-08-15 硬化輪）：輸入長度上限（`MAX_PARSE_TEXT_CHARS`）
   → 同步 CPU 段丟 executor ＋ `asyncio.wait_for`（`PARSE_CPU_TIMEOUT_S`）→
   attempt 耗盡收屍。in-process 的最大風險本來就是「job 卡死的是**整個 app** 的
   event loop」；這三層是 in-process 得以成立的安全前提，抽離後仍然全部適用。
4. **死亡可觀測**：worker task 掛 done-callback，異常終止記 ERROR（uvicorn 預設
   root logger 只出 WARNING+，INFO 在 docker logs 看不見——啟動訊息同理用 WARNING）。
   shutdown 對「worker 先死」免疫（`engine.dispose()` 必達）。

## per-process 迴圈語意（部署者必讀）

worker 迴圈是 **per-process** 的：每個 uvicorn worker 行程各起一個迴圈。

- **現況（compose 用 `--reload`）**：devops 實測 `--reload` 下 `--workers` 是
  **no-op**——實際只有一個 app 行程，也就只有一個迴圈。今天「單迴圈」是 reload
  旗標的副作用，不是設計保證。
- **拿掉 reload 之後（正式部署必然）**：`--workers N` 會真的生出 N 個行程 → N 個
  迴圈。後果不是壞資料（SKIP LOCKED 保正確性），而是：
  - 輪詢放大：DB 每 interval 吃 N 次 runnable 掃描（partial index
    `ix_ai_parse_jobs_active_created` 壓低了單次成本，但次數照放大）；
  - **LLM 併發放大**：N 個行程各自按 batch 上限打 LLM，總併發 ≈ N × batch，
    沒有任何全域節流。單機 Ollama（預設 `llm_base_url=127.0.0.1:11434`）會直接
    變成排隊深度，逾時 → item retry → 更多請求的正回饋。
  - 緩解（不解決）：per-user 在途 job 配額、batch 上限 4、lease 60s。

## 抽離成 dedicated worker 的觸發條件（任一成立即開工）

1. 正式部署要開 `--workers > 1`（LLM 併發失去上限，見上）；
2. 啟用真 LLM 於批次路徑成為常態（現在預設 `wi_ai_enabled=false`，批次是毫秒級
   rule-based；LLM 一開，tick 交易抱著 job 列鎖跨網路呼叫的窗就從毫秒變 8s×batch
   ——Cancel／多實例計數都會被擋，正解「LLM 移出交易」只值得做在 dedicated worker）；
3. ADR-027 §7 的物理拆分條件成立（GPU/大型依賴、獨立 SLO、release cadence 分離）；
4. job 吞吐需要水平擴（worker 數要能獨立於 API 副本數調整）。

抽離形狀已由前提 1 決定：新增一個跑 `run_worker_loop` 的入口行程（compose 服務），
app 端 `DDM_PARSE_WORKER_ENABLED=0`，狀態機零搬動。

## 考慮過的選項

- **A. 立即做 dedicated worker（ADR-027 §6 原文）**：多一個常駐服務、compose/監控
  /部署面全要動，而批次路徑今天是 rule-based 毫秒級、量是「一個 import 幾百列」。
  成本先付、收益後到，違反 §7 自己的「達條件再拆」原則。
- **B. 維持 API 手動 tick**：批次 job 建了不動，功能等於沒交付；已被 D3-008 否決。
- **C. in-process、預設關閉**：部署不設環境變數就不跑——預設關閉的 worker 與 B
  無異（守門存在≠守門有在跑）。
- **D. in-process、預設開啟（本提案）**：功能即刻可用；以上述四個前提控風險；
  觸發條件明確、抽離成本被刻意壓低。

## 後果

**好處**：零新增部署面；job 自動推進；抽離路徑清楚且便宜。
**代價**：API 行程背著 CPU/記憶體外掛（executor 殘餘執行緒有 attempt 上限封頂）；
`--workers` 放大輪詢與 LLM 併發（觸發條件 1 擋在前面）；tick 交易的 job 列鎖窗
（已縮到交易尾端，殘餘＝首次 tick 的 queued→running 旗標）在 LLM 開啟時變顯著
（觸發條件 2 擋在前面）。

## 不由本 ADR 決定

LLM 全域節流的機制（token bucket vs queue depth）、dedicated worker 的副本策略、
`ai_*` 表獨立 schema（worklog 待決 #6）。
