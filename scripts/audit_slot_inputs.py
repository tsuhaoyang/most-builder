r"""audit_slot_inputs.py — ADR-028 §4 的部署前資料掃描（**一次性閘門，不是常駐 CI 關卡**）。

回答一個問題：**如果 most_engine 照 ADR-028 §2 的 A 類規則加嚴，現有資料裡有沒有任何一筆
會被擋下？** 有命中 → exit 1 → 先做一次性資料修補，再部署加嚴版本（ADR-028 §4 末段）。

這份報告是 ADR-028 §7 第 2 步**唯一的人工核可證據**。所以本檔對「讓報告看起來乾淨但其實
沒掃到」的路徑特別敏感：未設 `DATABASE_URL` 一律中止（不吃 settings 預設值）、報告開頭
攜帶連線身分、分頁不用 OFFSET、掃描在單一快照內、DB 內容一律跳脫後才印。

═══════════════════════════════════════════════════════════════════════════════
本檔與 most_engine 的關係（讀之前先讀這段；這是本檔最重要的註解）
═══════════════════════════════════════════════════════════════════════════════

**本檔把 ADR-028 §2 的 A 類判準實作了第二遍。這是刻意的、有期限的重複。**

為什麼可以：ADR-028 §7 把執行順序寫死——第 1 步是「掃描腳本 + 其正向對照測試（**不改引擎**）」，
引擎加嚴是第 4 步。第 1 步的當下引擎**還沒有** A 類實作，所以此刻不存在「兩份實作漂移」，
只存在「一份先行的偵測器」。

為什麼不抽成共用 predicate 模組給引擎與本檔共用（ADR 未採、本檔亦不採）：
兩者的**輸入根本不同**，共用會製造假的等價關係——

  - 本檔看的是 **DB 裡的原始 JSONB**：字串鍵、未知鍵、`revolutions: 2.6`、
    `distance_cm: "-5"` 這種「Pydantic 之前」的形狀。
    A5（非 0..6 的鍵）與 A2 的「非整數圈數」只在這一層看得見。
  - 引擎在所有生產路徑看到的是 **過完 `CycleIn` 的 dict**：`MComponent.revolutions: int`
    已經把 2.6 攔掉或轉掉，未知鍵已經被丟棄。

  另外語意也不同：引擎 fail-fast（拋第一個 `SequenceError` 就停），
  稽核必須**列舉一筆 payload 的所有違規**才有修補價值。

**本檔不手抄任何一份契約——覆蓋圖一律從真權威導出：**

  - 「哪些鍵屬於哪個格位」：讀 `schemas/v2/most.py` 的 Pydantic 欄位（`_fields()`）。
  - 「格位 i ↔ CycleIn 欄位 ↔ 格位模型」：用哨兵過一次真的 `cycle_in_to_engine()`
    反推（`_derive_slot_map()`）。原本這裡是手抄的常數，實測可以把 `"b4"` 改成
    `"b4_TYPO"`、把 A 格索引 `(0,3,6)` 改成 `(0,)`，而全套測試仍然全綠——
    那正是「稽核報乾淨但其實沒掃到」的假證據路徑。
  - 「A 格哪些分量要查帶表」：`ASlot` 欄位 × 該 rule-set 的 `a_bands` 家族 join
    （`_a_component_pairs()`）；返回格計哪些分量則**直接問引擎**（`_a_return_pairs()`）。
  - 值域判準（A1/A2/A3/A7）一律去讀該筆資料所屬 rule-set 的表（`RuleSetData`），
    不硬編任何數字。

**退場條件（不是「有空再說」，有測試盯著）：**
`tests/unit/test_audit_slot_inputs.py::test_engine_has_not_yet_implemented_a_class_strictness`
是一條 tripwire——它斷言「引擎**目前還沒有** A 類加嚴」。ADR-028 第 4 步一落地，那條測試
就會轉紅，強迫落地者回來處置本檔：把 A 類偵測改成直接呼叫 `compute_cycle` 並收
`SequenceError`（本檔即退化成「跑一遍引擎 + 產報告」的薄殼），或整支刪除。
沒有那條 tripwire，本檔就會變成第二個 `seed/v2/rule_set_seed.py`（ADR-028 §6 的前車之鑑：
兩份實作各自綠燈，實測已分叉四處）。

═══════════════════════════════════════════════════════════════════════════════

掃描範圍（ADR-028 §4）：
  - `most_cycles.slot_inputs`（rule-set 逐列釘死於 `most_cycles.rule_set_id`，不用 active 一概而論）
  - `motion_module_versions.rows[].cycle`（rule-set = 版本列的 `rule_set_id`）
  - `motion_templates.cycle_template`（不帶 rule_set_code → 套用時解析 active，故以 active 掃）
  - `excel_imports.staged_rows`、`import_rows.normalized_data`（ADR-027 §6）：
    這兩處存的是**正規化後的試算表列**，不必然含 cycle → 以深走訪找出 cycle 形狀的子物件
  - `ai_parse_runs.drafts[].cycle`（rule-set = run 的 `rule_set_id`）——**指標，不進 exit code**，
    理由見 `_DRAFT_RATIONALE`

判準分級（決定 exit code 的只有 BLOCK）：
  BLOCK  A1..A7  ADR-028 §2 A 類
         S1      斷言 #33「歷史鍵集合 ⊆ 現行 CycleIn 鍵集合」（ADR 明文授權）
  WARN   S2      payload 連現行 `CycleIn` 都驗不過
         W1..W4  已存在的問題或觀測值
                 **不影響 exit code**：閘門要量的是**差值**（加嚴之後「新增」會被擋下的列）。
                 逐項理由見 `_WARN_RATIONALE`。
  指標   AI 草稿  `ai_parse_runs.drafts[].cycle` 自成一區，既不 BLOCK 也不混進 WARN 分類。

exit code：0＝零命中（放行條件）／1＝有 BLOCK 命中／2＝掃描**沒跑完**（設定錯誤或未預期例外）。
exit 2 不是「有髒資料」，是「這份報告不存在」——不得當成任何結論。

用法（完整正式環境跑法見下方〈正式環境怎麼跑〉，也是 `--help` 的內容）：
  DATABASE_URL=postgresql+asyncpg://... PYTHONPATH=src python scripts/audit_slot_inputs.py
  ... --verbose      # 連乾淨的紀錄也逐筆列出

唯讀：本腳本不寫入任何一張表，而且這件事有**機械保證**——`begin_readonly_snapshot()`
以 `postgresql_readonly` 開交易，任何寫入當場 `25006`（ReadOnlySQLTransactionError），
**不依賴操作者有沒有先建 read-only role**（role 那層是第二道，見 runbook 第 1 步）。
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, get_args

# 讓腳本能 import ddm_v2（無需 pip install -e .）
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── exit code：中止與「有命中」必須分得開（`| tee` 存下的證據會長得一模一樣）──────
_EXIT_CLEAN = 0
_EXIT_BLOCKED = 1
_EXIT_FATAL = 2


class AuditAbort(RuntimeError):
    """掃描**沒跑完**：設定錯誤或資料完整性錯誤 → exit 2。

    刻意不用 `SystemExit`：`SystemExit(str)` 的預設 exit code 是 1，會與「有 BLOCK 命中」
    撞在一起。放行者拿到的證據檔若只寫 `exit=1`，就分不出「有髒資料」與「掃描炸掉」。
    """


# ══════════════════════════════════════════════════════════════════════════════
# 模組載入期的失敗也必須是 exit 2（**不是** exit 1）
# ══════════════════════════════════════════════════════════════════════════════
# 實測（修補前）三條全部拿到 exit **1**——而 runbook 的圖例寫著「1 = 有 BLOCK 命中 → 去修資料」：
#   /usr/bin/python3 …            → ModuleNotFoundError: pydantic          exit=1
#   契約漂移（_derive_slot_map）   → AuditAbort: [FATAL] 無法反推格位覆蓋圖   exit=1
#   ManualOverride 新增必填欄位    → pydantic ValidationError               exit=1
# 也就是說 `AuditAbort` 這個「為了 exit 2 而發明的型別」，在它自己被丟出的第一個現場拿到 1。
# 拿到 exit 1 + 空 stdout 的 DBA 會判成「有命中」→ 去做資料修補，而真相是**掃描根本沒跑**。
#
# 所以第三方／`ddm_v2` 的 import 與格位覆蓋圖的反推全部收進守衛內：失敗只記進 `_INIT_ERROR`，
# 由 `main()` 統一轉成 exit 2。刻意**不**在這裡 `sys.exit()`：本檔也被測試以 module 形式載入，
# import 期直接 exit 會把 pytest 一起帶走。
#
# 順帶的好處：`--help` 在**缺依賴時仍然印得出來**——而 runbook 第 0 步講的正是怎麼把依賴裝起來。
_INIT_ERROR: BaseException | None = None

try:
    from pydantic import BaseModel, ValidationError  # noqa: E402
    from sqlalchemy import select, text  # noqa: E402
    from sqlalchemy.engine import make_url  # noqa: E402
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

    from ddm_v2.models.v2.ai_ops import AiParseRun  # noqa: E402
    from ddm_v2.models.v2.import_staging import ExcelImport, ImportRow  # noqa: E402
    from ddm_v2.models.v2.motion_module import MotionModuleVersion  # noqa: E402
    from ddm_v2.models.v2.motion_template import MotionTemplate  # noqa: E402
    from ddm_v2.models.v2.rule_set import RuleSet  # noqa: E402
    from ddm_v2.models.v2.worksheet import MostCycle  # noqa: E402
    from ddm_v2.most_engine import SequenceError, compute_cycle  # noqa: E402
    from ddm_v2.most_engine.providers import load_rule_set_from_db  # noqa: E402
    from ddm_v2.most_engine.rule_set_data import RuleSetData  # noqa: E402
    from ddm_v2.schemas.v2.most import (  # noqa: E402
        ASlot,
        CycleIn,
        ManualOverride,
        MComponent,
        MSlot,
        XSlot,
        cycle_in_to_engine,
    )
except BaseException as exc:  # noqa: BLE001 —— 這裡不是吞錯：exc 原封不動留給 main() 印 traceback
    _INIT_ERROR = exc


# ── `--help` 的內容＝〈正式環境怎麼跑〉；本常數是**單一權威**，檔頭 docstring 由它拼出來 ──
#    （不放進 docstring 字面：`python -OO` 會把 docstring 剝掉，runbook 會靜默消失。）
_RUNBOOK_MARKER = "【正式環境怎麼跑】"
_RUNBOOK = r"""【正式環境怎麼跑】（唯讀；ADR-028 §4 的人工放行關卡）

⚠️ 這一節是**要對正式資料庫執行**的指令。全節假設 **bash**（`PIPESTATUS` 在 dash 下會是
   `Bad substitution`），並假設執行者**不是本專案的開發者**——DBA／SRE 照著就該跑得完。

0) 環境（少了這步，系統 python3 會 `ModuleNotFoundError: No module named 'pydantic'`；
   Debian/Ubuntu 預設也沒有 `python` 這個指令）

   先把 repo 弄上這台機器（跳板機通常沒有 git 憑證，也不該有）：
     # 在有 repo 的開發機上：
     git -C <repo> archive --format=tar HEAD | gzip > ddm.tgz && scp ddm.tgz <跳板機>:~/
     # 在跳板機上：
     mkdir -p ~/ddm && tar xzf ~/ddm.tgz -C ~/ddm      # <repo> 即為 ~/ddm

     cd <repo>/ddm-v2                          # 之後所有指令都在這個目錄下執行
     AUDIT_VENV=~/adr028-audit-venv            # 刻意建在 repo 外：.gitignore 只擋 .venv/，
                                               # 建在 repo 內會多出一堆未追蹤檔案
     python3.11 -m venv "$AUDIT_VENV"          # 鎖檔以 --python-version 3.11 編出，CI/Dockerfile 亦為 3.11
     "$AUDIT_VENV/bin/pip" install --require-hashes -r requirements-build.lock
     "$AUDIT_VENV/bin/pip" install --require-hashes -r requirements.lock
     # ⚠️ 這裡是 requirements.lock（runtime），**不是** requirements-dev.lock。
     #    本腳本只需要 pydantic / sqlalchemy / asyncpg / greenlet，四個都在 runtime 鎖檔裡；
     #    dev 鎖檔會額外帶進 pytest / mypy / ruff / coverage / httpx。
     #    而這台是**唯一持有正式庫憑證的機器**——裝越少越好。
     # 之後一律用 "$AUDIT_VENV/bin/python"，不要用系統 python3。
     # （本 repo 開發用的 .venv 是 3.12，也跑得動；要與 CI／Docker 一致就用 3.11。
     #   本腳本不需要 `pip install -e .`——它自己把 src/ 加進 sys.path，跑時再帶 PYTHONPATH=src。）

   離線跳板機（無對外 egress，正式環境常態）：先在開發機備妥 wheelhouse 再搬過去。
   ⚠️ 尚未在真正的冷網路上驗證過——開發機上 pip 全程 `Using cached`，等於沒證明。
     # 開發機（**同 OS／同 CPU 架構／同 Python 3.11**，wheel 是綁平台的）：
     pip download --require-hashes -r requirements-build.lock -d wheelhouse
     pip download --require-hashes -r requirements.lock -d wheelhouse
     tar czf wheelhouse.tgz wheelhouse && scp wheelhouse.tgz <跳板機>:~/
     # 跳板機：
     "$AUDIT_VENV/bin/pip" install --no-index --find-links ~/wheelhouse \
       --require-hashes -r requirements-build.lock
     "$AUDIT_VENV/bin/pip" install --no-index --find-links ~/wheelhouse \
       --require-hashes -r requirements.lock

1) 建**唯讀**帳號。本腳本自己已經在交易層開 READ ONLY（`begin_readonly_snapshot()`，
   任何寫入當場 25006），role 這層是第二道防線；兩道都要。

     -- (a) 只讀群組（NOLOGIN，長期持有授權）
     CREATE ROLE ddm_audit_ro NOLOGIN;
     GRANT CONNECT ON DATABASE <db> TO ddm_audit_ro;
     GRANT USAGE ON SCHEMA public TO ddm_audit_ro;
     -- **不要**用 GRANT SELECT ON ALL TABLES——那會一併給出 app_users（員編／姓名／角色／
     -- site 範圍）、ai_parse_runs.llm_raw_response（整段模型輸出）、excel_imports.raw_payload
     -- （整份上傳的 Excel）。
     --
     -- 六張業務表用**欄級**授權：表級 GRANT 不排除欄位，所以「只逐表授權」只解決了上面
     -- 三個理由的第一個——llm_raw_response 與 raw_payload 照樣全開。腳本本來就是逐欄
     -- select 的（`audit()`），欄級授權對它零成本；漏授的欄位會當場 permission denied
     -- （exit 2，響亮），不會產生假綠。
     GRANT SELECT (id, wi_row_id, rule_set_id, slot_inputs, total_tmu) ON most_cycles TO ddm_audit_ro;
     GRANT SELECT (id, module_id, version_no, rule_set_id, rows) ON motion_module_versions TO ddm_audit_ro;
     GRANT SELECT (id, name_zh, cycle_template) ON motion_templates TO ddm_audit_ro;
     GRANT SELECT (id, staged_rows) ON excel_imports TO ddm_audit_ro;        -- raw_payload 不給
     GRANT SELECT (id, normalized_data) ON import_rows TO ddm_audit_ro;
     GRANT SELECT (id, routing_status, rule_set_id, drafts) ON ai_parse_runs TO ddm_audit_ro;  -- llm_raw_response 不給
     -- rule-set 家族維持**表級**：`load_rule_set_from_db()` 用 `select(Model)` 取整列，
     -- 欄級授權會在日後加欄位時 permission denied。這些表是規則值，不含個資。
     GRANT SELECT ON
       rule_sets, rule_a_bands, rule_b_options, rule_g_actions,
       rule_p_bases, rule_p_addons, rule_m_ladder_bands, rule_m_foot_bands,
       rule_m_verbs, rule_m_rotation_bands, rule_m_hand_bands,
       rule_x_options, rule_i_options
     TO ddm_audit_ro;

     -- (b) 一次性登入帳號：有期限、有連線上限、連上就是唯讀
     --     （NOLOGIN 不能用在這裡——角色要能登入才跑得動腳本，所以才拆成兩層。）
     --     VALID UNTIL 是**時間點**不是天數：填「明天 00:00」＝**今晚午夜就到期**，
     --     不是「還有一天可用」。跨夜重掃的話填後天，或收工後重建帳號。
     CREATE ROLE ddm_audit_run LOGIN IN ROLE ddm_audit_ro
       VALID UNTIL '<到期時間點，例如 2026-08-16 00:00+08＝ 8/15 一整天可用>' CONNECTION LIMIT 2;
     ALTER ROLE ddm_audit_run SET default_transaction_read_only = on;
     ALTER ROLE ddm_audit_run SET statement_timeout = '30min';
     ALTER ROLE ddm_audit_run SET idle_in_transaction_session_timeout = '5min';

     -- (c) 密碼用 psql 的 \password（互動輸入，送出的是 SCRAM 雜湊）。
     --     **不要**寫成 CREATE ROLE ... PASSWORD '<明文>'：PG 官方文件明載明文密碼會進
     --     server log 與 client 的 command history。
     \password ddm_audit_run

   ⚠️ **不要**寫沒有 `FOR ROLE` 的 `ALTER DEFAULT PRIVILEGES`：
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ddm_audit_ro;
      不帶 `FOR ROLE` 時它只作用於**執行這條指令的人**未來建的物件。DBA 用 superuser 跑、
      alembic 用 app role 建表 → 完全沒接上，日後新表照樣 permission denied（實測）。
      **比不寫更糟：它製造了錯誤的安心感。** 真要涵蓋未來新表就二選一：
        ALTER DEFAULT PRIVILEGES FOR ROLE <實際建表的 role> IN SCHEMA public
          GRANT SELECT ON TABLES TO ddm_audit_ro;
      或 PG14+ 的 `GRANT pg_read_all_data TO ddm_audit_ro;`（不必知道 owner 是誰，
      但範圍等同全庫可讀——與上面「逐表授權」的收斂意圖相反，採用前先想清楚）。

2) 跑掃描並存檔。報告要附進 ADR-028 §7 第 2 步的 User 核可。

     # 密碼含 @ : / ? # 等字元一定要 percent-encode。實測：SQLAlchemy 的 URL 解析器會把
     # 'p@ssw0rd' 的第一個 @ 當成 user/host 分隔 → host 變成 'ssw0rd@dbhost'，
     # 報的是「連不到主機」而不是「密碼錯」，錯誤訊息完全誤導。
     #   "$AUDIT_VENV/bin/python" -c \
     #     "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" '<pw>'
     # ⚠️ **不要**改寫成 `...@<host>/<db>?password=<pw>` 來迴避 percent-encode。那條路連得上
     #    （asyncpg dialect 會把 query 併進連線參數），但密碼會跟著進**報告 header**——
     #    本腳本已改成只印 query 的鍵名，但別的工具（psql \conninfo、ps、log）不會。
     # 另外 export 會寫進 shell history：建議先 `set +o history`，收工後 `unset DATABASE_URL`。
     export DATABASE_URL="postgresql+asyncpg://ddm_audit_run:<percent-encoded-pw>@<host>:5432/<db>"
     # ⚠️ 要**直連 PostgreSQL**，不要走 pgbouncer 的 transaction pooling：asyncpg 會建
     #    prepared statement，跨連線撞名 → `DuplicatePreparedStatementError` → exit 2。
     #    非得經過 pooler 就加 `?prepared_statement_cache_size=0`（但那也會關掉快取）。

     # 輸出刻意寫在 repo 外：repo 內沒有 *.txt 的 ignore 規則，
     # 一份正式環境資料報告會直接出現在 git status，一個 git add -A 就進版控。
     OUT=~/adr028_audit_$(date +%Y%m%dT%H%M%S).txt
     PYTHONPATH=src "$AUDIT_VENV/bin/python" scripts/audit_slot_inputs.py \
       2>&1 | tee "$OUT"
     echo "exit=${PIPESTATUS[0]}"    # ← 接了 tee 之後 $? 是 tee 的，放行看的是 PIPESTATUS[0]

   exit code：
     0 = A 類加嚴**不會新擋下**任何現有資料（放行條件）
     1 = 有 BLOCK 命中 → 先走第 4 步（決定要不要修），再走第 5 步（怎麼修）
     2 = **掃描沒跑完**（未設 DATABASE_URL／缺依賴／設定錯誤／未預期例外）。
         這不是「有髒資料」，而是「這份報告不存在」——不得當成任何結論。
     其他（137 / 143 …）＝**被訊號砍掉**，同樣是「這份報告不存在」。137 = SIGKILL，
         最常見的成因是 OOM killer：本腳本把所有紀錄留在記憶體到最後才一次輸出報告
         （實測約 430 B/payload：102 萬列 ≈ 502 MB，千萬列 ≈ 4.4 GB）。
         被 OOM 砍掉時 tee 存下的檔案接近 0 bytes——**長得跟 FATAL 一模一樣**，
         所以務必看 `PIPESTATUS[0]` 的數字本身，不要只看「非 0／是 0」。
         `dmesg -T | grep -i oom` 可確認。量大時先在 replica 上跑，或分批確認記憶體足夠。

   `2>&1` 不可省：中止訊息走 stderr，只接 stdout 的話 tee 存下來的證據檔會是 **0 bytes**，
   而「掃描炸掉」與「有 BLOCK 命中」在放行者眼中會長得一模一樣（實測過）。

   ⚠️ 報告開頭的【連線身分】區塊是給核可者看的：`current_database` / `current_user` /
      `inet_server_addr` 對不上正式庫，這份報告就不算數。
      （沒設 DATABASE_URL 時本腳本直接 exit 2，不會偷偷連到 localhost 的 dev 庫。）

3) 營運影響（可以在營運時間跑，但有幾件事要先講清楚）
   - 本腳本開一條 **REPEATABLE READ 的長交易**（要一致快照才不會漏列）。長交易期間
     **VACUUM 無法回收 dead tuple**，掃描愈久、表膨脹愈多。
   - 長交易會**擋住 DDL**：alembic migration 要的 ACCESS EXCLUSIVE 會排在本交易後面，
     而後續一般查詢又排在那個 lock 請求後面 → 該表在等待期間實質不可用。
     所以正確的告誡是「**掃描期間不要同時部署 migration**」，不是「不能在營運時間跑」。
   - 先量規模再決定：`SELECT count(*) FROM most_cycles;`（及其餘 5 張業務表）。
     量大就跑 read replica——本腳本全程唯讀，replica 適用。
     ⚠️ 但在 replica 上跑**必須一併記錄複寫延遲**：落後 N 分鐘的 standby 上，
        這 N 分鐘內寫入的髒列**不在本次快照內**，而報告會照樣 exit 0、每個欄位都與
        primary 上跑出來的一模一樣。報告 header 已印 `pg_is_in_recovery()` 與
        `pg_last_xact_replay_timestamp()`：`now()` 減去它就是本次掃描**看不到**的寫入區間，
        核可時要一起看。延遲不可忽略、或該區間有寫入流量，就回 primary 重跑。
     ⚠️ 另外：hot standby 上 `transaction_read_only` 由 PG 強制**恆為 on**，
        所以在 replica 上該欄位不再構成「本腳本自己的唯讀設定有生效」的證據。

4) ⚠️ 先看報告結尾的【命中率】，再決定要不要動手修（順序刻意排在「怎麼修」之前）：
   **BLOCK 命中率 > 1% → 不要直接修資料了事。** ADR-028〈重評訊號〉：命中大量列代表髒資料
   是常態而非例外，A2／A6 應退回 B 類、改由匯入層正規化，「無條件加嚴」需重議。
   這種情況要回頭改 ADR，而不是把那些列改乾淨然後照原案上線。

5) 確定要修之後，才進到「怎麼修」（ADR-028 §4）：
   - **先留痕再修**：一次性修補 migration 必須先把原 `slot_inputs` 與原 `total_tmu`
     抄一份留存，之後才改值。
     ⚠️ **留痕要落在哪張表，待 ADR-028 修訂後補上（見 ADR-028〈不由本 ADR 決定〉#9）。**
     實測：ADR-028 §4 正文寫的 `workflow_audit_log` 寫不進去（`entity_type` 的 CHECK
     allow-list 只有 process_version / motion_module / rule_set / motion_template，
     沒有 `most_cycle`）；替代路徑 `ai_review_events` 因 `run_id ON DELETE CASCADE`
     也不可用（parse run 一刪，稽核軌跡跟著消失）。
     這是 ADR 層級的缺陷、已記在 ADR-028〈不由本 ADR 決定〉#9 等 User 裁決——
     **不要自行挑一張表塞進去。**
   - 修補完**重掃到 exit 0**，才可部署加嚴版本。順序不可顛倒（ADR-028 §7）。

6) 收工：把一次性帳號收掉（一支自稱「一次性閘門」的腳本不該在正式庫留下永久帳號）。

     unset DATABASE_URL
     -- psql:
     DROP ROLE ddm_audit_run;      -- VALID UNTIL 只是保險，還是要主動刪
     -- ddm_audit_ro 是 NOLOGIN 群組，重掃還會用到；確定不再掃了再收：
     -- REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ddm_audit_ro;
     -- REVOKE USAGE ON SCHEMA public FROM ddm_audit_ro;
     -- REVOKE CONNECT ON DATABASE <db> FROM ddm_audit_ro;   -- ← 少這行，下一行會失敗：
     --   ERROR: role "ddm_audit_ro" cannot be dropped because some objects depend on it
     --   DETAIL: privileges for database <db>
     -- DROP ROLE ddm_audit_ro;

7) 本機／CI 綠燈不構成證據（ADR-028 斷言 #34）：放行條件是「對**正式環境全量資料** exit 0」。
"""

# 單一權威：runbook 只有 `_RUNBOOK` 一份，檔頭 docstring 由它拼上去。
# （`python -OO` 會把上面的 docstring 字面剝成 None，這行讓 runbook 依然在。）
__doc__ = (__doc__ or "") + "\n" + _RUNBOOK

# ── 判準說明（報告會原樣印出，讓看報告的人不必回讀 ADR）──────────────────────
_RULE_TEXT = {
    "A1": "M 分量 distance_cm/angle_deg/diameter_cm < 0 → M_NEGATIVE",
    "A2": "旋轉圈數非整數，或不在該 rule-set m_rotation 的圈數集合內 → M_ROTATION_RANGE",
    "A3": "A 分量超出帶表且該分量無 overflow 帶 → A_BAND_RANGE",
    "A4": "格位出現不屬於該格位模型的鍵（擴及 slot 0/1/2/6）→ SLOT_CROSS_MODEL",
    "A5": "slots 出現非 0..6 的整數鍵（含字串鍵）→ SLOT_KEY_INVALID",
    "A6": "m_components 內出現無 verb_code 的分量（空 list 仍合法）→ M_VERB_REQUIRED",
    "A7": "X 選項 mode='fixed' 但 fixed_seconds 為 NULL → X_FIXED_SECONDS_MISSING",
    "S1": "斷言 #33：歷史鍵集合 ⊄ 現行 CycleIn 鍵集合（extra='forbid' 的前提檢查）",
    "S2": "payload 驗不過現行 CycleIn（**今天就已經會 422**，與加嚴無關；修補批次請一起修）",
    "W1": "現行引擎已經拒絕這筆，或對它行為未定義（未預期例外）——加嚴前就壞了",
    "W2": "快取 total_tmu 與現行引擎重算值不一致",
    "W3": "payload 的 rule_set_code 與該列 FK 指向的 rule-set 不一致",
    "W4": "seq 用不到的變體格位帶了非 null 值（引擎會靜默丟棄）",
}

# 決定 exit code 的規則集合。**顯式列舉**，不是「開頭不是 W 就算 BLOCK」——
# 後者讓「S2 從 BLOCK 降成 WARN」這種分級調整必須改命名，而命名不該承載閘門語意。
_BLOCKING_RULES = frozenset({"A1", "A2", "A3", "A4", "A5", "A6", "A7", "S1"})

_WARN_RATIONALE = (
    "S2 與 W1–W4 不列入 exit code。**閘門要量的是差值**——「加嚴之後**新增**會被擋下的列」：\n"
    "  S2（payload 驗不過現行 `CycleIn`）：這種列**今天就已經會 422**，它不是加嚴造成的。\n"
    "    若把它算進 exit code，正式環境掃描會非 0，讀報告的人會以為「加嚴不安全」，\n"
    "    但真相是「你本來就有壞列」——那是**誤導性訊號**，會讓一個正確的部署決策被錯誤的\n"
    "    資料擋下。不過它的爆炸半徑與加嚴同型（下次存檔一樣 422），\n"
    "    **既然要做修補批次就一起修**，所以顯眼地排在本區塊最前面。\n"
    "  W1 是加嚴前就已存在的拒絕（爆炸半徑相同但成因不同，修它不屬本 ADR）；\n"
    "  W2 是快取漂移，而 ADR-028〈不由本 ADR 決定〉#7 明訂加嚴後**不重算** computed 快取；\n"
    "  W3/W4 是資料一致性觀測值。把它們納入閘門＝自行加嚴 ADR 沒授權的條件。\n"
    "  （S1 維持 BLOCK：斷言 #33 是 ADR 明文授權的放行條件。）"
)

_DRAFT_RATIONALE = (
    "為什麼 AI 草稿另立一區、且**不影響 exit code**：\n"
    "  `ai_parse_runs.drafts[].cycle` 是**還沒被採用**的建議草稿，不會被原樣重存回 most_cycles。\n"
    "  草稿被採用時會重新過 `CycleIn` + `compute_cycle`（`most_compiler/engine_gate.py`），\n"
    "  屆時被加嚴版本擋下**正是預期行為**——ADR-026 的 engine_gate 本來就是為此存在。\n"
    "  所以這裡的數字不是「加嚴會弄壞既有資料」，而是「加嚴後有多少 AI 草稿會開始被拒」：\n"
    "  那是決定要不要加嚴時會想知道的**觀測值**，不是阻擋部署的理由。\n"
    "  （因為不改變閘門語意，此區塊不需要重新核可 ADR-028；ADR〈不由本 ADR 決定〉已記錄。）"
)


@dataclass(frozen=True)
class Finding:
    rule: str    # A1..A7 / S1 / S2 / W1..W4
    code: str    # 加嚴後引擎會拋的錯誤碼（W* 為觀測標籤）
    where: str   # payload 內的 JSON 路徑
    detail: str

    @property
    def blocking(self) -> bool:
        return self.rule in _BLOCKING_RULES

    def __str__(self) -> str:
        return f"{self.rule} {self.code} @ {self.where}: {self.detail}"


@dataclass
class ScanRecord:
    source: str                       # 來源表
    entity_id: str                    # 實體 id
    path: str                         # payload 在該實體內的位置
    rule_set_code: str
    orig_tmu: float | None            # 原 total_tmu（沒有就 None）
    engine_tmu: float | None = None   # 現行引擎重算值
    engine_error: str | None = None   # 現行引擎的錯誤碼
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if not f.blocking]


# ── 格位覆蓋圖：**從真契約反推**，不手抄 `cycle_in_to_engine()` ───────────────
_SLOT_COUNT = 7
_PROBE_TMU_BASE = 10_000.0


def _fields(model: type) -> set[str]:
    return set(model.model_fields)


def _slot_model_of(field_name: str) -> type[BaseModel] | None:
    """`CycleIn` 某欄位背後的格位模型（`ASlot | None` 這種也要拆得出來）；不是格位就回 None。"""
    annotation = CycleIn.model_fields[field_name].annotation
    for candidate in (annotation, *get_args(annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _derive_slot_map(seq: str) -> tuple[tuple[str, ...], tuple[type[BaseModel], ...]]:
    """反推「格位 i ↔ CycleIn 欄位名 ↔ 格位模型」——過一次真的 `cycle_in_to_engine()`。

    作法：每個候選欄位塞一個哨兵（`manual_override.tmu` 給一個唯一數字，這是七個格位模型
    都有的欄位），送進 `cycle_in_to_engine()`，看哨兵落在哪一格。
    `seq` 用不到的變體格位（GM 的 m3/x4/i5）不會出現在輸出裡，自然被排除。

    為什麼不寫成常數：手抄的常數是無人看守的第二份契約。實測把 `"b4"` 打成 `"b4_TYPO"`、
    或把 A 格索引 `(0,3,6)` 改成 `(0,)`，全套 unit+integration 測試仍然全綠，
    而 `{"seq":"GM","a3":{"twist_deg":9999}}` 從報 `['A3']` 變成報 `[]`（假陰性）。
    """
    names: list[str | None] = [None] * _SLOT_COUNT
    models: list[type[BaseModel] | None] = [None] * _SLOT_COUNT
    for n, field_name in enumerate(CycleIn.model_fields):
        model = _slot_model_of(field_name)
        if model is None or "manual_override" not in model.model_fields:
            continue
        probe = _PROBE_TMU_BASE + n
        cycle = cycle_in_to_engine(CycleIn.model_validate({
            "seq": seq,
            field_name: {"manual_override": {"tmu": probe, "reason": "audit-slot-probe"}},
        }))
        for idx, slot in cycle["slots"].items():
            override = slot.get("manual_override")
            if isinstance(override, dict) and override.get("tmu") == probe:
                names[idx], models[idx] = field_name, model
                break
    if None in names or None in models:
        raise AuditAbort(
            f"[FATAL] 無法從 cycle_in_to_engine() 反推 {seq} 的格位覆蓋圖（得到 {names}）。"
            " 契約形狀變了（例如某個格位模型不再有 manual_override），"
            " 本檔的 A3/A4/S1 覆蓋範圍會靜默縮小——先修這裡，不要繞過。"
        )
    return tuple(n for n in names if n is not None), tuple(m for m in models if m is not None)


# 反推同樣在 `_INIT_ERROR` 守衛內：契約漂移丟的 `AuditAbort`、格位模型加了必填欄位丟的
# `ValidationError`，都是「掃描沒跑完」（exit 2），不是「有 BLOCK 命中」（exit 1）。
# 刻意**不**預設成空 tuple：預設值會讓覆蓋圖靜默縮成 0 格（假陰性）；沒定義就是 NameError，吵。
if _INIT_ERROR is None:
    try:
        _CYCLE_FIELDS_GM, _SLOT_MODELS_GM = _derive_slot_map("GM")
        _CYCLE_FIELDS_CM, _SLOT_MODELS_CM = _derive_slot_map("CM")
        # 格位索引一律由格位模型導出，不另抄 (0,3,6)/(0,6)/3/4/6。
        # 這幾個常數是覆蓋圖的一部分：手抄的那份沒人看守（實測把 A 格索引改成 `(0,)` 全套測試仍綠）。
        _A_SLOT_INDEXES_GM = tuple(i for i, m in enumerate(_SLOT_MODELS_GM) if m is ASlot)
        _A_SLOT_INDEXES_CM = tuple(i for i, m in enumerate(_SLOT_MODELS_CM) if m is ASlot)
        _M_SLOT_INDEX_CM = _SLOT_MODELS_CM.index(MSlot)
        _X_SLOT_INDEX_CM = _SLOT_MODELS_CM.index(XSlot)
        # 返回格＝最後一格（GM/CM 共通），且必須是 A 格——兩邊交叉驗證，不寫死 6。
        _RETURN_SLOT = _SLOT_COUNT - 1
        if (_A_SLOT_INDEXES_GM[-1], _A_SLOT_INDEXES_CM[-1]) != (_RETURN_SLOT, _RETURN_SLOT):
            raise AuditAbort(
                f"[FATAL] 最後一格（slot {_RETURN_SLOT}）不再是 A 格："
                f"GM A 格索引={_A_SLOT_INDEXES_GM}、CM={_A_SLOT_INDEXES_CM}。"
                " 序列形狀變了，A3 的返回格判準會失準——先修這裡，不要繞過。"
            )
    except BaseException as exc:  # noqa: BLE001 —— 同上：留給 main() 印 traceback 後 exit 2
        _INIT_ERROR = exc


def _a_component_pairs(rs: RuleSetData) -> tuple[tuple[str, str], ...]:
    """(ASlot 欄位, rule-set 帶表家族) 對照——由兩份真權威 join，不手抄引擎那三行。

    join 鍵是欄位名去掉單位後綴（`reach_cm` → `reach`）：`schemas/v2/most.py::ASlot` 的欄位
    與 `rule_a_bands.component` 兩邊都用這個構詞，加新分量時兩邊都得改，本表自動跟上。
    與引擎的一致性由 `tests/unit/test_audit_slot_inputs.py::test_a_component_pairs_match_the_engine`
    用行為探針對 `compute_cycle` 複驗。
    """
    return tuple(
        (name, name.rsplit("_", 1)[0])
        for name in ASlot.model_fields
        if name.rsplit("_", 1)[0] in rs.a_bands
    )


def _a_return_pairs(rs: RuleSetData, pairs: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """返回格（slot 6）由 A3 管的分量——**問引擎**，不抄 `_a_return_tmu` 的清單。

    引擎對返回格的非零 twist/foot 一律 `A_RETURN_COMPONENT`（E1），那些分量已經有人守，
    A3 再報一次就是雙重誤報。用一個只填該分量的最小 cycle 去問：引擎收就留，拒就排除。
    """
    kept: list[tuple[str, str]] = []
    for name, comp in pairs:
        try:
            compute_cycle({"seq": "GM", "slots": {_RETURN_SLOT: {name: 1}}}, rs)
        except SequenceError:
            continue
        kept.append((name, comp))
    return tuple(kept)


# per-RuleSetData 記憶：`_a_return_pairs` 要跑引擎，不能每列重算。
# key 用 id() 但同時持有物件的強參考——沒有強參考時物件被回收後 id 會被重用，快取就會答錯人。
_A_PAIRS_CACHE: dict[int, tuple[RuleSetData, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]] = {}


def _a_pairs(rs: RuleSetData) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    cached = _A_PAIRS_CACHE.get(id(rs))
    if cached is not None and cached[0] is rs:
        return cached[1], cached[2]
    pairs = _a_component_pairs(rs)
    entry = (rs, pairs, _a_return_pairs(rs, pairs))
    _A_PAIRS_CACHE[id(rs)] = entry
    return entry[1], entry[2]


def _num(value: Any) -> float | None:
    """取數值；**字串型數值也算**（bool 不算——Python 的 bool 是 int 子類，放行會讓 True 被當 1）。

    為什麼要吃字串：`Pydantic 之前`的 JSONB 可能存著 `"distance_cm": "-5"`。
    Pydantic 會把它 coerce 成 `-5.0`，加嚴後引擎照樣擋——所以稽核如果跳過字串，
    就會把一筆**加嚴後會被擋下**的列判成乾淨（假陰性）。dev DB 目前沒有這種資料，
    但正式環境的 AI parser 與匯入正是最會產生字串型數值的來源。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except OverflowError:
            # JSONB 可以存任意精度整數，float() 會溢位。回 ±inf 讓 A1/A3 仍然往正確方向命中，
            # 而不是讓整趟掃描因為一筆荒謬的值而中止。
            return math.inf if value > 0 else -math.inf
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _int_or_none(value: Any) -> int | None:
    """整數值（含 2.0 / "2" 這種）→ int；非整數或非數值 → None。"""
    number = _num(value)
    if number is None or not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


# ── A 類偵測（純函式，免 DB；單元測試的受測對象）─────────────────────────────
def _check_key_subset(obj: Any, allowed: set[str], where: str, rule: str, code: str) -> list[Finding]:
    if not isinstance(obj, dict):
        return []
    foreign = sorted(set(obj.keys()) - allowed)
    if not foreign:
        return []
    # foreign 來自 DB 的 JSONB 鍵：用 list 的 repr（元素逐一 repr）印出，換行／ANSI 逃脫序列
    # 不會原樣進報告。報告是人工放行證據，能被 DB 內容改寫版面就等於可偽造。
    return [Finding(rule, code, where, f"未知鍵 {foreign}（允許：{sorted(allowed)}）")]


def _check_a_slot(slot: Any, rs: RuleSetData, where: str, *, return_slot: bool) -> list[Finding]:
    """A3：分量超出帶表且該分量無 overflow 帶 → A_BAND_RANGE（資料驅動，不是一律報錯）。"""
    out: list[Finding] = []
    if not isinstance(slot, dict):
        return out
    all_pairs, return_pairs = _a_pairs(rs)
    for key, comp in (return_pairs if return_slot else all_pairs):
        value = _num(slot.get(key))
        if value is None or value <= 0:
            continue
        bands = rs.a_bands.get(comp, ())
        if not bands:
            continue  # 空帶表＝rule-set 缺陷（ADR-028 C 類），不是 A3
        if any(mx is None for mx, _idx in bands):
            continue  # 有 overflow 帶 → 超出仍合法（斷言 #13：reach 9999cm → 24）
        finite_max = max(mx for mx, _idx in bands if mx is not None)
        if value > finite_max:
            out.append(Finding(
                "A3", "A_BAND_RANGE", f"{where}.{key}",
                f"{value:g} 超出 {comp} 帶表上界 {finite_max:g} 且該分量無 overflow 帶",
            ))
    return out


def _check_m_slot(slot: Any, rs: RuleSetData, where: str) -> list[Finding]:
    """A1（負值）／A2（旋轉圈數）／A6（缺 verb_code）＋ S1（分量鍵集合）。"""
    out: list[Finding] = []
    if not isinstance(slot, dict):
        return out
    comps = slot.get("m_components")
    if comps is None:
        return out
    if not isinstance(comps, list):
        return out  # 形狀問題由 S2 管
    rev_set = {rv for _mx, rv, _tmu in rs.m_rotation}
    for i, comp in enumerate(comps):
        at = f"{where}.m_components[{i}]"
        if not isinstance(comp, dict):
            continue
        out += _check_key_subset(comp, _fields(MComponent), at, "S1", "CYCLE_KEY_UNKNOWN")

        # A1：三個尺寸欄位一律不得為負（ADR-028 §2 A1 未按動詞區分；Pydantic 預設值皆為 0，
        # 所以「動詞用不到的欄位」在合法資料裡不會出現負值，檢查全部不會誤殺）
        for key in ("distance_cm", "angle_deg", "diameter_cm"):
            value = _num(comp.get(key))
            if value is not None and value < 0:
                out.append(Finding("A1", "M_NEGATIVE", f"{at}.{key}", f"{value:g} < 0"))

        # A6：空 list 合法；list 裡的分量沒有 verb_code 不合法
        code = comp.get("verb_code")
        if not code:
            out.append(Finding("A6", "M_VERB_REQUIRED", at, f"分量缺 verb_code（收到 {code!r}）"))
            continue

        # A2：只在動詞真的是 rotate 時才有意義（ADR-028〈考慮過的選項〉C-2：
        # 一律 ge=1,le=3 會誤殺 ladder／hand 分量帶的無害預設值）
        kind = rs.m_verbs.get(code, (None, None))[0]
        if kind != "rotate":
            continue
        raw_rev = comp.get("revolutions", 1)
        if raw_rev is None:
            raw_rev = 1  # 與 MComponent 預設值/引擎 `or 1` 對齊
        rev = _int_or_none(raw_rev)
        if rev is None:
            # 訊息要與實際成因相符：非數值（"abc"）與含小數（2.6）是兩回事。
            reason = "不是數值，無法解讀為圈數" if _num(raw_rev) is None else "非整數圈數"
            out.append(Finding("A2", "M_ROTATION_RANGE", f"{at}.revolutions",
                               f"{raw_rev!r} {reason}"))
        elif rev not in rev_set:
            out.append(Finding("A2", "M_ROTATION_RANGE", f"{at}.revolutions",
                               f"{rev} 不在 rule-set {rs.code!r} 的圈數集合 {sorted(rev_set)} 內"))
    return out


def _check_x_slot(slot: Any, rs: RuleSetData, where: str) -> list[Finding]:
    """A7：payload 指到 mode='fixed' 但 fixed_seconds 為 NULL 的 X 選項（今天是裸 ValueError → 500）。"""
    if not isinstance(slot, dict):
        return []
    code = slot.get("x_code")
    if not code or not isinstance(code, str) or code not in rs.x_options:
        return []
    mode, fixed_seconds = rs.x_options[code]
    if mode == "fixed" and fixed_seconds is None:
        return [Finding("A7", "X_FIXED_SECONDS_MISSING", f"{where}.x_code",
                        f"X 選項 {code!r} 在 rule-set {rs.code!r} 為 mode='fixed' 但 fixed_seconds 為 NULL")]
    return []


def _slots_from_engine_shape(raw: dict[str, Any]) -> tuple[dict[int, Any], list[Finding]]:
    """引擎形狀 {'seq':..,'slots':{0:{...}}}：A5 檢查鍵必須是 0..6 的**整數**鍵。

    JSON 沒有整數鍵——所以任何從 JSONB 讀回來的引擎形狀 payload 必然全數命中 A5，
    這正是 ADR-028 斷言 #9 的病灶（`compute_cycle(json.loads(json.dumps(cycle)))` → 0.0）。

    `slots` 不是 dict（`null`／字串／陣列）→ 回一條 S2 並由呼叫端**提早結束**。
    原本這裡靜默回空 dict，然後 `_run_current_engine` 把 raw 原封不動交給引擎，
    `calculate.py:238` 的 `s.get(i)` 對非 dict 拋 `AttributeError`——不在被捕捉的三種例外內
    → 整趟 exit 2，而 traceback 裡沒有 entity_id／path，正式庫上得靠二分法找那一筆。
    """
    findings: list[Finding] = []
    slots: dict[int, Any] = {}
    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, dict):
        return slots, [Finding("S2", "CYCLE_SHAPE_INVALID", "$.slots",
                               f"slots 須為物件，收到 {type(raw_slots).__name__}")]
    for key, value in raw_slots.items():
        idx = key if isinstance(key, int) and not isinstance(key, bool) else None
        if idx is None or not (0 <= idx < _SLOT_COUNT):
            findings.append(Finding("A5", "SLOT_KEY_INVALID", f"slots[{key!r}]",
                                    f"格位鍵須為 0..6 的整數，收到 {type(key).__name__} {key!r}"))
            continue
        slots[idx] = value
    return slots, findings


def scan_cycle_payload(raw: Any, rs: RuleSetData) -> list[Finding]:
    """對**單一 cycle payload 的原始 JSON** 跑完 ADR-028 A 類 + S1/S2 + W1。

    刻意不先過 Pydantic：A5（字串鍵）、S1（未知鍵）、A2（非整數圈數）都只在 Pydantic 之前看得見。
    回傳**所有**命中（不 fail-fast），因為修補需要完整清單。
    """
    findings: list[Finding] = []
    if not isinstance(raw, dict):
        return [Finding("S2", "CYCLE_SHAPE_INVALID", "$", f"cycle payload 不是物件：{type(raw).__name__}")]

    seq = raw.get("seq")
    if seq not in ("GM", "CM"):
        return [Finding("S2", "CYCLE_SHAPE_INVALID", "$.seq", f"seq 必須是 GM/CM，收到 {seq!r}")]

    engine_shape = "slots" in raw
    if engine_shape:
        slots, key_findings = _slots_from_engine_shape(raw)
        findings += key_findings
        if any(f.where == "$.slots" for f in key_findings):
            # `slots` 根本不是物件：底下每一條判準都無從施力，而把 raw 丟給引擎會炸掉整趟掃描。
            return findings
        where_of = {i: f"slots[{i}]" for i in range(_SLOT_COUNT)}
    else:
        # 斷言 #33：歷史 slot_inputs 的鍵集合 ⊆ 現行 CycleIn 鍵集合
        findings += _check_key_subset(raw, _fields(CycleIn), "$", "S1", "CYCLE_KEY_UNKNOWN")
        names = _CYCLE_FIELDS_GM if seq == "GM" else _CYCLE_FIELDS_CM
        slots = {i: raw.get(name) for i, name in enumerate(names)}
        where_of = {i: f"$.{name}" for i, name in enumerate(names)}

    models = _SLOT_MODELS_GM if seq == "GM" else _SLOT_MODELS_CM
    for i in range(_SLOT_COUNT):
        slot = slots.get(i)
        if slot is None:
            continue  # B6：缺格位／null 視為空 dict，仍合法
        where = where_of[i]
        if not isinstance(slot, dict):
            findings.append(Finding("S2", "CYCLE_SHAPE_INVALID", where,
                                    f"格位須為物件，收到 {type(slot).__name__}"))
            continue
        # A4：格位鍵必須屬於該格位模型（允許集合＝真契約的 Pydantic 欄位，非本檔自抄）
        findings += _check_key_subset(slot, _fields(models[i]), where, "A4", "SLOT_CROSS_MODEL")
        # manual_override 的鍵集合（S1；extra='forbid' 會一起收緊）
        if isinstance(slot.get("manual_override"), dict):
            findings += _check_key_subset(slot["manual_override"], _fields(ManualOverride),
                                          f"{where}.manual_override", "S1", "CYCLE_KEY_UNKNOWN")

    a_indexes = _A_SLOT_INDEXES_GM if seq == "GM" else _A_SLOT_INDEXES_CM
    for i in a_indexes:
        findings += _check_a_slot(slots.get(i), rs, where_of[i], return_slot=(i == _RETURN_SLOT))
    if seq == "CM":
        findings += _check_m_slot(slots.get(_M_SLOT_INDEX_CM), rs, where_of[_M_SLOT_INDEX_CM])
        findings += _check_x_slot(slots.get(_X_SLOT_INDEX_CM), rs, where_of[_X_SLOT_INDEX_CM])

    findings += _run_current_engine(raw, rs, engine_shape)
    return findings


def _engine_cycle(raw: dict[str, Any], engine_shape: bool) -> dict[str, Any]:
    """把 payload 轉成現行引擎吃的形狀（走真正的生產路徑 `cycle_in_to_engine`）。"""
    if engine_shape:
        return raw
    return cycle_in_to_engine(CycleIn.model_validate(raw))


def _brief_validation_error(exc: ValidationError) -> str:
    """只取 type/loc/msg。

    pydantic 的 `errors()[0]` 還帶 `input`——那是**該格位的完整 dict**（可能含使用者填的
    自由文字），沒必要進一份會被傳閱、附進 ADR 核可的報告。
    """
    first = exc.errors()[0]
    return repr({key: first.get(key) for key in ("type", "loc", "msg")})


def _unexpected(exc: BaseException) -> str:
    """未預期例外的摘要——**訊息一律 repr**（引擎訊息會內插 DB 原值，見 `render()` 的說明）。"""
    return f"{type(exc).__name__}: {str(exc)!r}"


def _run_current_engine(raw: dict[str, Any], rs: RuleSetData, engine_shape: bool) -> list[Finding]:
    """S2（驗不過現行契約）與 W1（現行引擎已拒絕）——加嚴前就存在的狀態。"""
    try:
        cycle = _engine_cycle(raw, engine_shape)
    except ValidationError as exc:
        return [Finding("S2", "CYCLE_SHAPE_INVALID", "$",
                        f"CycleIn 驗證失敗：{exc.error_count()} 個錯誤；首個＝{_brief_validation_error(exc)}")]
    try:
        compute_cycle(cycle, rs)
    except SequenceError as exc:
        # 引擎訊息會內插原始輸入值（`calculate.py` 多處），一律 repr 後才進報告。
        return [Finding("W1", exc.code, "$", repr(str(exc)))]
    except ValueError as exc:  # calculate.py:200 的裸 ValueError（ADR-028 §5）
        return [Finding("W1", "UNCODED_VALUE_ERROR", "$", repr(str(exc)))]
    except AuditAbort:
        raise  # 掃描層的中止不是「這筆資料的問題」，不得降級成 finding
    except Exception as exc:  # noqa: BLE001 —— 見下方註解
        # **這不是吞錯**：是把「現行引擎對這一筆資料的行為未定義」記進報告而不是炸掉閘門。
        # 對照組是原本的行為：一筆畸形 payload（例如 `slots` 不是物件）讓 `s.get(i)` 拋
        # `AttributeError` → 整趟 exit 2，且 traceback 裡**沒有 entity_id／path**，
        # 正式庫上只能靠二分法找出是哪一筆。現在它變成一條帶著實體位置的 W1，掃描繼續走完。
        # 仍是 WARN 而非 BLOCK：它描述的是**現行**引擎的狀態，與 A 類加嚴的差值無關。
        return [Finding("W1", "UNEXPECTED_ENGINE_ERROR", "$", _unexpected(exc))]
    return []


def recompute(raw: Any, rs: RuleSetData) -> tuple[float | None, str | None]:
    """現行引擎重算值（報告的「新結果或錯誤碼」欄）。不拋例外。"""
    if not isinstance(raw, dict):
        return None, "CYCLE_SHAPE_INVALID"
    try:
        result = compute_cycle(_engine_cycle(raw, "slots" in raw), rs)
    except ValidationError:
        return None, "CYCLE_SHAPE_INVALID"
    except SequenceError as exc:
        return None, exc.code
    except ValueError:
        return None, "UNCODED_VALUE_ERROR"
    except AuditAbort:
        raise
    except Exception:  # noqa: BLE001 —— 同 `_run_current_engine`：不得讓一筆畸形資料中止整趟掃描
        return None, "UNEXPECTED_ENGINE_ERROR"
    return result.total_tmu, None


def unused_variant_slots(raw: dict[str, Any]) -> list[str]:
    """W4：seq 用不到的變體格位帶了非 null 值 → 引擎會靜默丟棄。"""
    if not isinstance(raw, dict) or raw.get("seq") not in ("GM", "CM"):
        return []
    unused = _CYCLE_FIELDS_CM if raw["seq"] == "GM" else _CYCLE_FIELDS_GM
    shared = set(_CYCLE_FIELDS_GM) & set(_CYCLE_FIELDS_CM)
    return [n for n in unused if n not in shared and raw.get(n) is not None]


def iter_cycle_payloads(obj: Any, path: str = "$") -> Iterator[tuple[str, dict[str, Any]]]:
    """深走訪任意 JSON，找出「長得像 cycle」的子物件（供 staged_rows / import_rows 用）。

    判準刻意保守：`seq ∈ {GM,CM}` **或**含 `slots` 鍵。找到就不再往下鑽（cycle 內部不會再有 cycle）。

    `"slots" in obj` 這半邊不是贅字：它負責撈出**引擎形狀但 seq 壞掉／缺席**的 payload
    （`{"slots": {"0": {...}}}`）。這種 payload 今天由 `scan_cycle_payload` 判 S2（WARN），
    拿掉這半邊的話它們會直接從報告上消失——不是變成 WARN，是**完全掃不到**，
    而報告的【掃描範圍】仍然印著同樣的列數。那是「報告謊報掃描量」的同型問題。
    """
    if isinstance(obj, dict):
        if obj.get("seq") in ("GM", "CM") or "slots" in obj:
            yield path, obj
            return
        for key, value in obj.items():
            yield from iter_cycle_payloads(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from iter_cycle_payloads(value, f"{path}[{i}]")


# ── DB 掃描層 ────────────────────────────────────────────────────────────────
_PAGE = 500


def _identity_sql() -> Any:
    """報告 header 的連線身分查詢。

    `pg_is_in_recovery()` / `pg_last_xact_replay_timestamp()` 不是裝飾：runbook 第 3 步
    建議「量大就跑 read replica」，而落後 N 分鐘的 replica 上，最近寫入的髒列**不在快照裡**
    → exit 0，且報告每個欄位都與 primary 上跑出來的一模一樣。核可者必須看得到這件事。
    連帶：`transaction_read_only` 在 hot standby 上**恆為 on**（PG 強制），
    所以在 replica 上該欄位不再證明本腳本自己的唯讀設定有生效——一併寫進報告。

    （寫成函式而不是 module 常數：`text()` 來自 sqlalchemy，module 層求值會落在
    `_INIT_ERROR` 守衛之外。）
    """
    return text(
        "SELECT current_database(), current_user, inet_server_addr(), "
        "current_setting('transaction_read_only'), current_setting('transaction_isolation'), now(), "
        "pg_is_in_recovery(), pg_last_xact_replay_timestamp()"
    )


def require_database_url() -> str:
    """`DATABASE_URL` 未設（或缺 host／username）→ 立即中止（exit 2）。**不吃 settings 的預設值。**

    `src/ddm_v2/settings.py` 的 fallback 是
    `postgresql+asyncpg://ddm_user:ddm_pass@localhost:5432/ddm_v2`。
    export 掉在別的 shell、改用 `sudo`（`env_reset` 會清掉環境變數）、或包成 cron，
    都會靜默連到跳板機上的本機 dev PG，然後產出一份格式完全正確、結論寫「零命中」的報告。
    這份報告是 ADR-028 §7 第 2 步唯一的人工核可證據——寧可不跑，不要跑錯庫。
    （同 repo 先例：`scripts/cleanup_test_data.py`）

    為什麼還要檢查 host／username：`postgresql+asyncpg:///ddm` 是合法 URL，但兩者都空
    → 落到 libpq 預設（`PGHOST` / `~/.pgpass` / unix socket ＋ OS 使用者）。在 DB 主機上跑
    就是以 peer auth 連上——很可能是 superuser，而 runbook 第 1 步那個唯讀角色等於沒發生。
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise AuditAbort(
            "[FATAL] 未設定 DATABASE_URL。本腳本刻意**不**沿用 settings 的預設連線"
            "（那會靜默連到 localhost 的 dev 庫，產出一份看起來正確的「零命中」假報告）。\n"
            '  export DATABASE_URL="postgresql+asyncpg://<ro-user>:<pw>@<host>:5432/<db>"'
        )
    parsed = make_url(url)
    missing = [name for name, value in (("host", parsed.host), ("username", parsed.username))
               if not value]
    if missing:
        raise AuditAbort(
            f"[FATAL] DATABASE_URL 缺少 {missing}：{redact_url(url)!r}。\n"
            "  沒有 host／username 時連線會落到 libpq 預設（PGHOST／~/.pgpass／unix socket"
            " ＋ OS 使用者）。在 DB 主機上那通常是 superuser 的 peer auth，"
            "runbook 第 1 步的唯讀角色等於沒發生，而報告仍會長得完全正確。\n"
            '  export DATABASE_URL="postgresql+asyncpg://<ro-user>:<pw>@<host>:5432/<db>"'
        )
    return url


def redact_url(url: str) -> str:
    """報告 header 用的連線字串——**自己組，不用 `render_as_string(hide_password=True)`。**

    SQLAlchemy 的 `hide_password` 只遮 `URL.password`，`URL.query` 是**逐字 render** 的
    （`sqlalchemy/engine/url.py`）。而 asyncpg dialect 會 `opts.update(url.query)`，
    所以 `?password=...` 是**合法且會生效**的寫法——被 runbook 的 percent-encode 警告勸退的
    操作者，最自然的迴避動作就是把密碼搬進 query string：

        postgresql+asyncpg://ddm_audit_run@dbhost:5432/ddm?password=P%40ss%2Fw0rd

    連得上、掃描正常跑完，然後密碼明文落進一份要附進 ADR 核可、被傳閱的報告。
    （`sslpassword` 同理。）所以 query 一律**只印鍵名不印值**。
    """
    parsed = make_url(url)
    userinfo = f"{parsed.username}@" if parsed.username else ""
    port = f":{parsed.port}" if parsed.port else ""
    database = f"/{parsed.database}" if parsed.database else ""
    query = f"?{'&'.join(f'{k}=***' for k in sorted(parsed.query))}" if parsed.query else ""
    return f"{parsed.drivername}://{userinfo}{parsed.host or ''}{port}{database}{query}"


async def begin_readonly_snapshot(session: Any) -> None:
    """在**單一快照**內、以交易層唯讀開始掃描。這是「唯讀」的機械保證。

    - `postgresql_readonly`：之後任何寫入當場 `25006`（ReadOnlySQLTransactionError）。
      docstring 說「唯讀」而保證只寫在 runbook 的 role 步驟裡，等於把保證外包給一段人工步驟；
      runbook 第 2 步又叫人 export 一整條 URL，最省事的做法就是貼手邊的 app 帳號 URL，
      那時第 1 步等於沒發生。這行讓保證回到腳本內。
    - `REPEATABLE READ`：整趟掃描看同一份快照。keyset 分頁（`_page`）解掉「新列插進既有順序」
      造成的漏列，快照則解掉「同一列在掃描中途被改」造成的前後不一致。

    刻意**不**加 `postgresql_deferrable`：DEFERRABLE 只在 `SERIALIZABLE READ ONLY` 下有作用，
    在 REPEATABLE READ 下是 no-op。留著一個 no-op 旗標會招來「那把 isolation 改成 SERIALIZABLE
    讓它生效吧」的誤修，而那會讓這條長交易可能被 serialization failure 中斷
    （且 DEFERRABLE 會等到「能安全開始」為止——忙碌的 primary 上可能是很長的沉默等待）。
    """
    await session.connection(execution_options={
        "postgresql_readonly": True,
        "isolation_level": "REPEATABLE READ",
    })


async def connection_identity(session: Any, url: str) -> dict[str, str]:
    """報告 header 的連線身分：讓核可者能從報告本身判斷這是不是對正式庫跑的。"""
    row = (await session.execute(_identity_sql())).one()
    in_recovery = bool(row[6])
    replay = row[7]
    return {
        "DATABASE_URL（已遮罩密碼與 query 值）": redact_url(url),
        "current_database()": str(row[0]),
        "current_user": str(row[1]),
        "inet_server_addr()": "（NULL：unix socket 或本機連線）" if row[2] is None else str(row[2]),
        "transaction_read_only": str(row[3]),
        "transaction_isolation": str(row[4]),
        "now()": row[5].isoformat(),
        "pg_is_in_recovery()": (
            "True（**這是 read replica**：延遲期間的寫入不在本次快照內；"
            "且 standby 上 transaction_read_only 恆為 on，不再證明本腳本的唯讀設定生效）"
            if in_recovery else "False（primary）"
        ),
        "pg_last_xact_replay_timestamp()": (
            "（NULL：primary 或尚未重放任何交易）" if replay is None
            else f"{replay.isoformat()}（相對 now() 的落後量就是本報告看不到的寫入區間）"
        ),
    }


async def _page(session: Any, stmt: Any, order_col: Any) -> AsyncIterator[Any]:
    """**keyset** 分頁取全表（正式環境資料量未知，不一次撈進記憶體）。

    為什麼不是 OFFSET：排序鍵是 uuid4 主鍵，新列會**隨機插進既有順序的任何位置**。
    掃描期間每插入一筆排在目前 offset 之前的列，後面每頁就整體位移一列
    → 恰好有一列永遠不會被讀到。漏掉的若正好是髒列，報告就是**假綠**。
    keyset（`WHERE id > :last`）對插入免疫；順帶解掉 OFFSET 的 O(N²)。
    （O(N²) 的機制實測是「走 PK 索引掃過並**丟棄** OFFSET 之前的每一列」——
    `EXPLAIN` 計畫裡**沒有 Sort 節點**，不是 external merge sort。代價一樣是真的：
    102 萬列時末頁量到 2.7 秒。）
    """
    key = order_col.key
    last: Any = None
    while True:
        query = stmt if last is None else stmt.where(order_col > last)
        rows = list((await session.execute(query.order_by(order_col).limit(_PAGE))).all())
        for row in rows:
            yield row
        if len(rows) < _PAGE:
            return
        # 游標必須是**本頁最後一列**。取 `rows[0]` 的話每頁只前進一列，
        # 下一頁會重吐 `_PAGE-1` 筆已讀過的列——而【命中率】的分母就是 `len(records)`，
        # ADR-028 的 1% 門檻會被灌水稀釋到失效。守它的測試見
        # `test_keyset_pagination_walks_every_row_across_pages`（integration，_PAGE=2 種 3 列）
        # 與 `test_pagination_is_keyset_not_offset`（unit，假 session 真的套用 keyset 條件）。
        last = getattr(rows[-1], key)


class _RuleSetCache:
    """rule-set 依 code 載入一次；載不到＝錯誤狀態，不猜、不 fallback。"""

    def __init__(self, session: Any) -> None:
        self._session = session
        self._by_code: dict[str, RuleSetData] = {}
        self.code_by_id: dict[str, str] = {}
        self.active_code: str | None = None

    async def prime(self) -> None:
        rows = list((await self._session.execute(
            select(RuleSet.id, RuleSet.code, RuleSet.is_active))).all())
        self.code_by_id = {str(r.id): r.code for r in rows}
        active = [r.code for r in rows if r.is_active]
        # 不只一個 active＝設定錯誤，不能挑第一個當答案（挑錯版本會誤報或漏報 A2/A3）。
        self.active_code = active[0] if len(active) == 1 else None

    async def get(self, code: str) -> RuleSetData:
        if code not in self._by_code:
            self._by_code[code] = await load_rule_set_from_db(self._session, code)
        return self._by_code[code]


async def _scan_payload(
    cache: _RuleSetCache, *, source: str, entity_id: str, path: str,
    raw: Any, rule_set_code: str, orig_tmu: float | None,
    declared_code: str | None,
) -> ScanRecord:
    rs = await cache.get(rule_set_code)
    rec = ScanRecord(source=source, entity_id=entity_id, path=path,
                     rule_set_code=rule_set_code, orig_tmu=orig_tmu)
    rec.findings = scan_cycle_payload(raw, rs)
    rec.engine_tmu, rec.engine_error = recompute(raw, rs)

    if declared_code is not None and declared_code != rule_set_code:
        rec.findings.append(Finding("W3", "RULE_SET_CODE_MISMATCH", "$.rule_set_code",
                                    f"payload 宣告 {declared_code!r}，實際綁定 {rule_set_code!r}"))
    if orig_tmu is not None and rec.engine_tmu is not None and abs(orig_tmu - rec.engine_tmu) > 1e-6:
        rec.findings.append(Finding("W2", "TMU_CACHE_DRIFT", "$",
                                    f"快取 {orig_tmu:g} ≠ 重算 {rec.engine_tmu:g}"))
    for name in unused_variant_slots(raw) if isinstance(raw, dict) else []:
        rec.findings.append(Finding("W4", "UNUSED_VARIANT_SLOT", f"$.{name}",
                                    f"seq={raw.get('seq')!r} 用不到 {name}，引擎會靜默丟棄"))
    return rec


def _require_active(cache: _RuleSetCache, source: str) -> str:
    if cache.active_code is None:
        raise AuditAbort(
            f"[FATAL] {source} 的 cycle 不帶 rule_set_code，需以 active rule-set 掃描，"
            "但全庫沒有（或不只一個）is_active 版本。這是設定錯誤，不得猜版本。"
        )
    return cache.active_code


async def audit(session: Any) -> tuple[list[ScanRecord], dict[str, int], list[str], list[ScanRecord]]:
    """回傳 (放行條件相關的紀錄, 各來源掃描筆數, INFO 訊息, AI 草稿指標紀錄)。

    **AI 草稿走獨立回傳值，不是靠 render 過濾**：把它們放進 `records` 再篩掉，
    只要哪天有人在別處重用 `records` 就會把指標算成閘門。分開回傳是結構性保證。

    每個查詢只 select 用得到的欄位：`excel_imports.raw_payload` 是整份上傳的 Excel，
    `ai_parse_runs.llm_raw_response` 是整段模型輸出——本掃描一個都不需要，不取就不會進記憶體
    也不會進報告。

    ⚠️ **逐欄 select 不會減少授權需求**——那是 runbook 的事，不是這裡的事。SQL 的 `GRANT
    SELECT ON <table>` 涵蓋該表**所有欄位**，跟本函式挑了哪幾欄無關。要讓唯讀帳號真的看不到
    `llm_raw_response` / `raw_payload`，runbook 第 1 步必須下**欄級**授權
    （`GRANT SELECT (col, ...) ON <table>`）；本 docstring 原本寫「不取就不會進唯讀帳號的
    授權需求」，與 SQL 事實不符，已改正。
    """
    cache = _RuleSetCache(session)
    await cache.prime()
    known_codes = set(cache.code_by_id.values())
    records: list[ScanRecord] = []
    draft_records: list[ScanRecord] = []
    counts: dict[str, int] = {}
    infos: list[str] = []

    # 1. most_cycles.slot_inputs —— rule-set 逐列釘死（不同列可能不同版本）
    n = 0
    async for cyc in _page(session, select(
        MostCycle.id, MostCycle.wi_row_id, MostCycle.rule_set_id,
        MostCycle.slot_inputs, MostCycle.total_tmu,
    ), MostCycle.id):
        n += 1
        code = cache.code_by_id.get(str(cyc.rule_set_id))
        if code is None:
            raise AuditAbort(f"[FATAL] most_cycles {cyc.id} 的 rule_set_id={cyc.rule_set_id} 不存在。")
        raw = cyc.slot_inputs or {}
        records.append(await _scan_payload(
            cache, source="most_cycles", entity_id=f"{cyc.id} (wi_row={cyc.wi_row_id})",
            path="slot_inputs", raw=raw, rule_set_code=code,
            orig_tmu=float(cyc.total_tmu) if cyc.total_tmu is not None else None,
            declared_code=raw.get("rule_set_code") if isinstance(raw, dict) else None,
        ))
    counts["most_cycles.slot_inputs"] = n

    # 2. motion_module_versions.rows[].cycle
    n = 0
    async for ver in _page(session, select(
        MotionModuleVersion.id, MotionModuleVersion.module_id, MotionModuleVersion.version_no,
        MotionModuleVersion.rule_set_id, MotionModuleVersion.rows,
    ), MotionModuleVersion.id):
        code = cache.code_by_id.get(str(ver.rule_set_id))
        if code is None:
            raise AuditAbort(f"[FATAL] motion_module_versions {ver.id} 的 rule_set_id 不存在。")
        for i, row in enumerate(list(ver.rows or [])):
            raw = (row or {}).get("cycle") if isinstance(row, dict) else None
            if raw is None:
                continue
            n += 1
            records.append(await _scan_payload(
                cache, source="motion_module_versions",
                entity_id=f"{ver.id} (module={ver.module_id} v{ver.version_no})",
                path=f"rows[{i}].cycle", raw=raw, rule_set_code=code,
                orig_tmu=None,
                declared_code=raw.get("rule_set_code") if isinstance(raw, dict) else None,
            ))
    counts["motion_module_versions.rows[].cycle"] = n

    # 3. motion_templates.cycle_template —— 不帶 rule_set_code（ADR-025 D9），套用＝以 active 現算
    n = 0
    async for tpl in _page(session, select(
        MotionTemplate.id, MotionTemplate.name_zh, MotionTemplate.cycle_template,
    ), MotionTemplate.id):
        raw = tpl.cycle_template
        if raw is None:
            continue
        n += 1
        records.append(await _scan_payload(
            # name_zh 是使用者自填的裸 str（`schemas/v2/motion_template.py`，建立端點只要 analyst）。
            # 不 repr 就能用含換行的名字在報告裡插入偽造行（例如整段「【BLOCK…】（無）」），
            # 含 ANSI escape 的名字還能改寫 `cat` 時的顯示內容。
            cache, source="motion_templates", entity_id=f"{tpl.id} ({tpl.name_zh!r})",
            path="cycle_template", raw=raw,
            rule_set_code=_require_active(cache, "motion_templates"),
            orig_tmu=None,
            declared_code=raw.get("rule_set_code") if isinstance(raw, dict) else None,
        ))
    counts["motion_templates.cycle_template"] = n

    # 4/5. excel_imports.staged_rows 與 import_rows.normalized_data（ADR-027 §6）
    #      這兩處存的是正規化後的試算表列，不必然含 cycle → 深走訪找 cycle 形狀子物件
    for source, attr, id_col, payload_col in (
        ("excel_imports", "staged_rows", ExcelImport.id, ExcelImport.staged_rows),
        ("import_rows", "normalized_data", ImportRow.id, ImportRow.normalized_data),
    ):
        n = 0
        scanned = 0
        fallbacks: list[tuple[str, str, Any]] = []
        async for rec_row in _page(session, select(id_col, payload_col), id_col):
            n += 1
            payload = getattr(rec_row, attr)
            for path, raw in iter_cycle_payloads(payload, attr):
                scanned += 1
                declared = raw.get("rule_set_code")
                if isinstance(declared, str) and declared in known_codes:
                    code = declared
                else:
                    # 沒宣告 → 套用時本來就是解析 active，這是正解。
                    # 宣告了但那個 code 在庫裡不存在 → 仍以 active 掃（否則整趟中止），
                    # 但**必須在報告上說出來**：靜默改用別的版本會讓 A2/A3 誤報或漏報。
                    code = _require_active(cache, source)
                    if declared is not None:
                        fallbacks.append((str(rec_row.id), path, declared))
                records.append(await _scan_payload(
                    cache, source=source, entity_id=str(rec_row.id), path=path,
                    raw=raw, rule_set_code=code, orig_tmu=None, declared_code=None,
                ))
        counts[f"{source}.{attr}"] = n
        infos.append(f"{source}.{attr}：{n} 列，其中找到 {scanned} 個 cycle 形狀 payload")
        if fallbacks:
            infos.append(
                f"  ⚠️ {source}.{attr}：{len(fallbacks)} 個 payload 宣告了資料庫裡不存在的 "
                f"rule_set_code，已改用 active {cache.active_code!r} 掃描"
                f"（前 5 筆：{fallbacks[:5]!r}）。這些列的 A2/A3 判定僅在 active 版本下成立。"
            )

    # 6. ai_parse_runs.drafts[].cycle —— **指標，不進 exit code**（理由見 `_DRAFT_RATIONALE`）
    n = 0
    async for run in _page(session, select(
        AiParseRun.id, AiParseRun.routing_status, AiParseRun.rule_set_id, AiParseRun.drafts,
    ), AiParseRun.id):
        code = cache.code_by_id.get(str(run.rule_set_id))
        if code is None:
            raise AuditAbort(f"[FATAL] ai_parse_runs {run.id} 的 rule_set_id={run.rule_set_id} 不存在。")
        for i, draft in enumerate(list(run.drafts or [])):
            raw = (draft or {}).get("cycle") if isinstance(draft, dict) else None
            if raw is None:
                continue  # partial draft（`complete=False`）的 cycle 就是 null，這是常態
            n += 1
            draft_records.append(await _scan_payload(
                cache, source="ai_parse_runs",
                entity_id=f"{run.id} (routing={run.routing_status!r})",
                path=f"drafts[{i}].cycle", raw=raw, rule_set_code=code, orig_tmu=None,
                declared_code=raw.get("rule_set_code") if isinstance(raw, dict) else None,
            ))
    counts["ai_parse_runs.drafts[].cycle（指標）"] = n

    # INFO：rule-set 層的 X mode='fixed' 但 fixed_seconds NULL（ADR-028 斷言 #27 的前提）
    for code in sorted(known_codes):
        rs = await cache.get(code)
        broken = sorted(c for c, (mode, sec) in rs.x_options.items() if mode == "fixed" and sec is None)
        infos.append(f"rule-set {code!r}：X mode='fixed' 且 fixed_seconds NULL 的選項 = {broken or '無'}")
    return records, counts, infos, draft_records


# ── 報告 ─────────────────────────────────────────────────────────────────────
_RATE_THRESHOLD_PCT = 1.0   # ADR-028〈重評訊號〉：命中 >1% 的 cycle → 「無條件加嚴」需重議


def _rate_pct(hit: int, total: int) -> float | None:
    return None if total == 0 else hit * 100.0 / total


def _fmt_rate(hit: int, total: int) -> str:
    pct = _rate_pct(hit, total)
    return f"{hit}/{total} = n/a（掃描 0 筆）" if pct is None else f"{hit}/{total} = {pct:.2f}%"


def render(records: list[ScanRecord], counts: dict[str, int], infos: list[str],
           *, verbose: bool, draft_records: list[ScanRecord] | None = None,
           identity: dict[str, str] | None = None) -> tuple[str, int]:
    """產出報告與 exit code。

    `draft_records`（`ai_parse_runs.drafts[].cycle`）只進【指標】區塊，**不參與 exit code**。
    所有來自 DB 的字串（entity_id / path / rule_set_code / finding detail）一律 `!r` 輸出——
    這份報告是人工放行證據，能被 DB 內容改寫版面就等於可偽造。
    """
    drafts = list(draft_records or [])
    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add("ADR-028 §4 資料掃描：A 類加嚴會不會擋下現有資料？")
    add("=" * 78)
    add("")
    add("【連線身分】核可前先確認這是不是正式庫；對不上，這份報告不算數")
    if identity is None:
        add("  ⚠️ （未取得——本報告不是由 CLI 對真實連線產生的，不得作為放行證據）")
    else:
        for key, value in identity.items():
            add(f"  {key:<28} {value!r}")
    add("")
    add("【掃描範圍】")
    for name, n in counts.items():
        add(f"  {name:<44} {n:>6} 筆")
    add(f"  {'（放行條件內的 cycle payload 數）':<40} {len(records):>6} 個")
    add(f"  {'（AI 草稿 payload 數，不列入放行條件）':<38} {len(drafts):>6} 個")
    add("")
    add("【判準】只有 BLOCK 決定 exit code；WARN 與 AI 草稿指標都不決定")
    for rule, text_ in _RULE_TEXT.items():
        add(f"  {'BLOCK' if rule in _BLOCKING_RULES else 'WARN '} {rule}  {text_}")
    add("")

    blocking = [r for r in records if r.blocking]
    # S2 排最前面：它是「今天就已經壞了」的列，修補批次要一起帶走（見 _WARN_RATIONALE）
    warned = sorted((r for r in records if r.warnings),
                    key=lambda r: 0 if any(f.rule == "S2" for f in r.warnings) else 1)

    def dump(rec: ScanRecord, tag: str) -> None:
        new = rec.engine_error or (f"{rec.engine_tmu:g}" if rec.engine_tmu is not None else "—")
        orig = f"{rec.orig_tmu:g}" if rec.orig_tmu is not None else "—"
        add(f"  [{tag}] {rec.source} {rec.path!r}")
        add(f"        id={rec.entity_id!r}")
        add(f"        rule_set={rec.rule_set_code!r}  原 total_tmu={orig}  現行引擎={new}")
        for f in rec.findings:
            add(f"        · {f}")

    add("【BLOCK：加嚴後會被擋下的紀錄】")
    if not blocking:
        add("  （無）")
    for rec in blocking:
        dump(rec, "BLOCK")
    add("")

    add("【WARN：不影響 exit code】")
    if not warned:
        add("  （無）")
    blocked_ids = {id(rec) for rec in blocking}  # 用 identity，ScanRecord 的欄位可能巧合相同
    for rec in warned:
        if id(rec) in blocked_ids:
            continue  # 上面 BLOCK 區塊已完整列出這筆的所有命中
        dump(rec, "WARN")
    add(f"  {_WARN_RATIONALE}" if warned else "")
    add("")

    draft_blocking = [r for r in drafts if r.blocking]
    add("【指標：AI 草稿（不影響 exit code）】")
    add(f"  ai_parse_runs.drafts[].cycle：掃描 {len(drafts)} 個，"
        f"加嚴後會被拒 {len(draft_blocking)} 個（{_fmt_rate(len(draft_blocking), len(drafts))}）")
    for rec in draft_blocking:
        dump(rec, "指標")
    add(f"  {_DRAFT_RATIONALE}")
    add("")

    if verbose:
        add("【逐筆（--verbose）】")
        for rec in records:
            if not rec.findings:
                dump(rec, "OK")
        add("")

    n_block_findings = sum(len(r.blocking) for r in records)
    by_rule: dict[str, int] = {}
    for rec in records:
        for f in rec.findings:
            by_rule[f.rule] = by_rule.get(f.rule, 0) + 1

    add("【INFO】")
    for info in infos:
        add(f"  {info}")
    add("")
    add("【合計】")
    add(f"  掃描 cycle payload：{len(records)} 個（另有 AI 草稿 {len(drafts)} 個，僅計為指標）")
    add(f"  BLOCK 紀錄：{len(blocking)} 筆 / BLOCK 命中：{n_block_findings} 條")
    add(f"  各規則命中數：{by_rule or '無'}")
    add("")
    add("【命中率】（分母＝放行條件內的 cycle payload 數；AI 草稿不在內）")
    add(f"  BLOCK 命中率：{_fmt_rate(len(blocking), len(records))}"
        f"　← 對照 ADR-028〈重評訊號〉門檻 {_RATE_THRESHOLD_PCT:.2f}%")
    add(f"  WARN  命中率：{_fmt_rate(len([r for r in records if r.warnings]), len(records))}"
        "　（僅供參考，不在門檻內）")
    rate = _rate_pct(len(blocking), len(records))
    if rate is not None and rate > _RATE_THRESHOLD_PCT:
        add(f"  ⚠️ **BLOCK 命中率 {rate:.2f}% 已超過 {_RATE_THRESHOLD_PCT:.2f}% 門檻。**")
        add("     ADR-028〈重評訊號〉：髒資料是常態而非例外 → A2／A6 應退回 B 類、改由匯入層")
        add("     正規化，「無條件加嚴」需重議。**不要直接修資料了事**，先回頭改 ADR。")
    add("")
    if blocking:
        add("結論：**有命中** → 先看上方【命中率】決定要不要修（--help 第 4 步），確定要修才依")
        add("      ADR-028 §4 做一次性資料修補 migration（原 slot_inputs 與原 total_tmu 先留痕再")
        add("      改值；留痕落在哪張表待 ADR-028 修訂，見 --help 第 5 步與 ADR-028〈不由本 ADR")
        add("      決定〉#9），修補後重掃綠燈才可部署加嚴版本。")
        code = _EXIT_BLOCKED
    else:
        add("結論：本次掃描的資料集**零命中**。")
        add("      ⚠️ ADR-028 斷言 #34：放行條件是「對**正式環境全量資料** exit 0」。")
        add("      在筆數少的環境（dev/CI）綠燈不構成任何證據——差集守門的待驗集合可能根本是空的。")
        code = _EXIT_CLEAN
    add("=" * 78)
    return "\n".join(lines), code


async def _main_async(verbose: bool) -> int:
    url = require_database_url()
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await begin_readonly_snapshot(session)
            identity = await connection_identity(session, url)
            records, counts, infos, draft_records = await audit(session)
    finally:
        await engine.dispose()
    report, code = render(records, counts, infos, verbose=verbose,
                          draft_records=draft_records, identity=identity)
    print(report)
    return code


def build_parser() -> argparse.ArgumentParser:
    """獨立出來讓測試可以斷言 `--help` 真的帶著 runbook（而不是只斷言常數存在）。"""
    parser = argparse.ArgumentParser(
        description="ADR-028 §4：掃描既有資料，找出 A 類加嚴後會被擋下的 cycle payload（唯讀）。",
        epilog=_RUNBOOK,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", action="store_true", help="連乾淨的紀錄也逐筆列出。")
    return parser


def main() -> None:
    # 先 parse_args：`--help` 不需要任何第三方依賴，而 runbook 第 0 步講的正是怎麼把依賴裝起來。
    args = build_parser().parse_args()
    if _INIT_ERROR is not None:
        # 模組載入期就失敗（缺依賴／契約漂移／格位模型加了必填欄位）。
        # 這是 exit **2**：掃描沒跑完。若讓它照 Python 預設走 exit 1，
        # 拿到「exit=1 + 空 stdout」的 DBA 會照 runbook 圖例判成「有 BLOCK 命中」去修資料。
        traceback.print_exception(_INIT_ERROR)
        print("[FATAL] 模組載入期失敗（見上方 traceback）：掃描**沒跑**，這份報告不存在。"
              "常見成因：沒用 runbook 第 0 步建的 venv（缺 pydantic／sqlalchemy），"
              "或 schemas/v2/most.py 的契約變了。**不得**當成任何結論。", file=sys.stderr)
        sys.exit(_EXIT_FATAL)
    try:
        code = asyncio.run(_main_async(verbose=args.verbose))
    except AuditAbort as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(_EXIT_FATAL)
    except Exception:  # 掃描沒跑完 ≠ 有髒資料：exit 2，不得與 BLOCK 命中的 exit 1 混淆
        traceback.print_exc()
        print("[FATAL] 掃描未完成（未預期的例外，見上方 traceback）。"
              "這份報告不存在，**不得**當成放行證據。", file=sys.stderr)
        sys.exit(_EXIT_FATAL)
    sys.exit(code)


if __name__ == "__main__":
    main()
