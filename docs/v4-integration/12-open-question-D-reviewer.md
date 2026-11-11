# 開放問題 D 技術評估：v4 reviewer 角色如何對映到 v2 RBAC

> **裁決結果（User 2026-09-04）：整合 Case 審批流，並採 (a) — v2 新增 reviewer 階層
> （viewer<analyst<reviewer<approver<admin），保留四眼分權。**
> 以下為裁決依據原文。
>
> 目的：為 Case 審批流（若採用 v4 的 submit→review→approve 分權模型）在 v2 落地時，
> 決定 v4 的 `reviewer` 角色要如何對映——(a) v2 新增 `reviewer` 階層，或 (b) 併入既有 `approver`。
> 方法：實讀 v4 與 v2 相關程式碼，附 `檔案:行號`。唯讀分析，不改任何 v4/v2 程式碼。
> 日期：2026-09-04

## 結論（建議）

**採 (a) 的「語義」但用 (b) 的「機制」——具體落地：在 v2 新增一個 `reviewer` 階層，
但把它插在 `analyst` 與 `approver` 之間（`viewer<analyst<reviewer<approver<admin`）。**

一句話：v4 的 review 是「approve 之前的獨立品管把關」，把它併入 approver 會**讓同一人
同時 review 又 approve**，弱化四眼原則（four-eyes）。但 v2 是**階層式**RBAC，不是 v4 的
**扁平集合**RBAC——直接照搬 v4「reviewer 與 approver 互不隸屬」的扁平語義會與 v2 現有治理衝突。
折衷是：新增 `reviewer` 階層（低於 approver），讓 review 成為獨立可授予的關卡，同時保留
v2「上位角色涵蓋下位能力」的一致模型。

**但這個決策應與開放問題「Case 審批流是否整合」綁定**：若 User 最終決定不整合 v4 的
Case/Analysis 審批流（v2 目前的審批對象是 worksheet／template／rule-set，不是 v4 的 analysis case），
則 reviewer 角色**根本不需要引入**——沒有 review 動作要守的關。詳見下方§4。

---

## 1. v4 的 reviewer 實際把關什麼（實讀證據）

### 1.1 v4 是扁平角色集合，不是階層

`app/api/dependencies.py:34-50`：

```python
def require_roles(*role_names: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        user_roles = set(current_user.role_names)
        if not user_roles.intersection(role_names):   # 純集合交集，無大小關係
            raise HTTPException(status_code=403, detail="權限不足")
        return current_user
    return dependency

require_admin              = require_roles("admin")
require_analyst_or_admin   = require_roles("admin", "analyst")
require_reviewer_or_admin  = require_roles("admin", "reviewer")
require_approver_or_admin  = require_roles("admin", "approver")
```

關鍵：v4 用 `set.intersection`——`reviewer` 與 `approver` **彼此不隸屬**，也不互相涵蓋。
一個只有 `approver` 角色的人**無法** review（`require_reviewer_or_admin` 不含 approver），
一個只有 `reviewer` 角色的人**無法** approve。唯一的「超級角色」是 `admin`（每個 gate 都含 admin）。
`models/user.py:56-58` 的 `role_names` 也只是回傳角色名清單，無序無階層。

### 1.2 review 是 approve 前的獨立狀態關卡

v4 Case 狀態機 `app/api/routes/analysis.py:80-88`：

```python
VALID_TRANSITIONS = {
    "draft":              {"submitted"},
    "submitted":          {"reviewed", "changes_requested"},
    "reviewed":           {"approved"},
    "changes_requested":  {"draft"},
    "approved":           {"archived"},
}
```

各動作的角色守門（`analysis.py`）：

| 動作 | 端點 | 狀態轉換 | 要求角色 | 行號 |
|---|---|---|---|---|
| submit | `POST /cases/{id}/submit` | draft→submitted | `require_analyst_or_admin` | :356-364 |
| review | `POST /cases/{id}/review` | submitted→reviewed | `require_reviewer_or_admin` | :366-374 |
| request-changes | `POST /cases/{id}/request-changes` | submitted→changes_requested | `require_reviewer_or_admin` | :376-384 |
| approve | `POST /cases/{id}/approve` | reviewed→approved | `require_approver_or_admin` | :386-394 |
| archive | `POST /cases/{id}/archive` | approved→archived | `require_admin` | :396-404 |

**reviewer 把的關**：一個 case 從 `submitted` 只能先進到 `reviewed`（或被 `request-changes` 退回），
**approve 動作硬性要求前一狀態是 `reviewed`**（`VALID_TRANSITIONS["reviewed"]={"approved"}`，
且 `submitted` 不能直接到 `approved`）。也就是說：

- reviewer 是**品管初審**：確認 case 內容（步驟、TMU、敘述）品質，通過才放行到 approve。
- reviewer 也持有**退件權**（request-changes），把 case 打回 draft 讓 analyst 重編。
- approver 是**最終核准**：只能對「已通過 review」的 case 蓋章。

這是典型的**兩段式分權（reviewer 初審 + approver 終審）**，強制 case 至少經兩個角色的手，
且 `analyst`（提交者）既不能 review 也不能 approve（`require_analyst_or_admin` 不含這兩關）——
四眼原則在 v4 是靠「三個互不隸屬的角色 + 狀態機順序」共同保證的。

> 注意：v4 的稽核 `WorkflowAuditLog`（`models/audit.py`）只記 `actor_user_id`/`from_status`/`to_status`，
> **沒有**「review 與 approve 必須不同人」的程式強制。v4 的分權完全靠「reviewer≠approver 是兩個角色」
> 這件事在角色指派時人為維持——扁平角色讓這件事自然（一個人若只被授 reviewer 就 approve 不了）。

### 1.3 v4 角色種子

`app/db/init_db.py:15-21`：`admin / analyst / reviewer / approver / viewer` 五個角色，扁平並存。
使用者可被授予任意組合（`routes/users.py:72-73`）。

---

## 2. v2 現況：階層式 RBAC（實讀證據）

`src/ddm_v2/auth/deps.py:17`：

```python
ROLE_ORDER = {"viewer": 0, "analyst": 1, "approver": 2, "admin": 3}
```

`deps.py:34-46` `CurrentUser.level` 取**最大**角色序，`has()` 與 `require_role` 都用 `>=` 比較：

```python
@property
def level(self) -> int:
    return max((ROLE_ORDER.get(r, 0) for r in self.roles), default=0)

def require_role(min_role: str):
    async def dep(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.level < ROLE_ORDER[min_role]:   # 階層：上位涵蓋下位
            raise HTTPException(status_code=403, detail=...)
        return user
    return dep
```

**與 v4 的根本差異**：v2 是**單調階層**——`approver`（level 2）自動涵蓋 `analyst`（level 1）
與 `viewer`（level 0）的所有能力。這是 v2 治理的核心假設。

v2 目前 `approver` 這關實際守的東西（審批性質，非 case）：

- `worksheet.py:104`：發布 worksheet（draft→published）需 `require_role("approver")`。
- `motion_template.py:84`：把 template 從 draft 升為 standard（promote）需 `require_role("approver")`。
- `audit_log.py:51`：讀稽核記錄需 `require_role("approver")`。
- `services/v2/motion_module_service.py:50`：`_MANAGER_LEVEL = ROLE_ORDER["approver"]`（治理門檻）。

可指派角色白名單 `admin_users.py:22`：

```python
_VALID_ROLES = {"admin", "approver", "analyst"}
```

（v2 目前**不開放**指派 `viewer`——viewer 是 JIT 預設的無角色狀態，見 `deps.py` `current_user` 的 JIT 建 user `roles=[]`。）

---

## 3. 兩個選項對 v2 治理的影響

### 選項 (a)：v2 新增 `reviewer` 階層

**做法**：`ROLE_ORDER = {"viewer":0, "analyst":1, "reviewer":2, "approver":3, "admin":4}`
（reviewer 插在 analyst 與 approver 之間），`admin_users.py:22` 白名單加 `"reviewer"`。

- **保留分權**：review 成為獨立可授予的關卡。一個只被授 `reviewer`（level 2）的人可以 review，
  但 `< approver`（level 3）→ 不能 approve。四眼原則的「review≠approve」得以保留。
- **與 v2 階層模型相容**：因為 approver（level 3）> reviewer（level 2），`approver` 自動涵蓋
  review 能力——這**符合** v2「上位涵蓋下位」的一致假設，也符合直覺（能終審的人當然能初審）。
  這一點正是 v2 與 v4 的差異：v4 的 approver **不能** review（扁平），v2 的 approver **能** review（階層）。
  對 case 分權而言，v2 階層版仍成立，因為關鍵是「**提交者 analyst 不能 review/approve**」，
  這在 (a) 下依然成立（analyst level 1 < reviewer level 2）。
- **代價**：
  - `ROLE_ORDER` 改動會**位移** approver 的數值（2→3）與 admin（3→4）。凡是**硬編數字**的地方要查。
    實讀確認 v2 目前**沒有**硬編 `ROLE_ORDER` 數字的地方——都走 `require_role("approver")` 具名查表
    或 `ROLE_ORDER["approver"]`（`motion_module_service.py:50` 也是具名索引），所以位移**安全**。
  - `admin_users.py:22` 白名單需加 `"reviewer"`（1 行）。
  - 前端角色選單、i18n 標籤要加 reviewer（ADR-032 `_zh`/`_en`）。
  - 現有審批（worksheet publish、template promote）**不受影響**：它們要 approver（level 3），
    reviewer（level 2）自然擋在門外，行為與現在一致。

### 選項 (b)：把 v4 reviewer 併入 v2 approver

**做法**：不新增角色，把 v4 的 review 與 approve 兩個動作都對映到 v2 `require_role("approver")`。

- **弱化分權**：review 與 approve 由**同一階層（approver）**把關 → 同一個 approver 使用者
  可以先 review 再 approve **同一個 case**，四眼原則失效（除非另加「不同人」程式強制，
  但 v4 稽核模型也沒有這個強制，見 §1.2 註）。這**降低**了 v4 原本的治理強度。
- **狀態機退化**：若 review 與 approve 同權，`submitted→reviewed→approved` 的中間 `reviewed`
  關卡失去把關意義，等於退回「submit→approve」兩段式（少一道獨立品管）。
- **好處**：零 schema／零角色新增，最小改動；若 case 審批流的品管需求本來就低，這是務實選擇。
- **風險**：一旦日後要恢復分權，得補建 reviewer 角色 + 資料回填，成本比一開始就做 (a) 高。

---

## 4. 關鍵前提：這題與「Case 審批流是否整合」綁定

**v2 目前的審批對象與 v4 不同**：

- v2 審批的是 **worksheet 發布**、**motion template 升級**、**rule-set 治理**（§2 證據）。
- v4 的 review/approve 是針對 **Analysis Case**（`analysis_cases`，`models/analysis.py:14`）——
  v2 目前**沒有** analysis case 這個實體，也沒有對應的 submit→review→approve 狀態機。

因此：

- 若 **不整合** v4 的 Case/Analysis 審批流 → **不需要** reviewer 角色（沒有 review 動作要守關）。
  v2 既有 `analyst<approver<admin` 足以支撐現有審批（worksheet/template/rule-set）。
- 若 **整合** v4 Case 審批流（在 v2 重寫 case 狀態機）→ 才需要決定 reviewer 對映，此時**建議採 (a)**。

**這是 review 前必須先問 User 的上游決策**，不能只在 RBAC 層獨立裁決。

---

## 5. 建議裁決

1. **先確認 Case 審批流是否整合**（上游決策）。若不整合 → reviewer 免談，本題關閉。
2. **若整合 → 採 (a)：新增 `reviewer` 階層，插在 `analyst` 與 `approver` 之間**
   （`viewer<analyst<reviewer<approver<admin`）。理由：
   - 保留 v4 的核心治理價值——**提交者不能自審自核**、**review 是 approve 前的獨立關卡**。
   - 相容 v2 階層模型（上位涵蓋下位），不引入 v4 的扁平語義污染 v2 一致性。
   - 對現有審批零影響（實讀確認無硬編 `ROLE_ORDER` 數字）。
   - 與 TMU 單一權威無關（純授權層，不進計算路徑，golden GM=28/CM=29 不受影響）。
3. **不建議 (b)**：併入 approver 會讓 review/approve 同權，弱化四眼原則且使狀態機中間關卡失義；
   除非 User 明確認為 case 審批只需單關品管（那時 (b) 才是務實選擇）。

## 6. 若採 (a) 的最小落地清單（供實作階段參考，本題不改碼）

- `auth/deps.py:17` `ROLE_ORDER` 插入 `"reviewer": 2`，approver→3、admin→4。
- `admin_users.py:22` `_VALID_ROLES` 加 `"reviewer"`。
- case 審批端點：review／request-changes → `require_role("reviewer")`；approve → `require_role("approver")`；
  submit → `require_role("analyst")`（比照 v4 §1.2 對映，但用 v2 階層語義）。
- 前端角色標籤 + i18n（ADR-032 `_zh`/`_en`）。
- 稽核：沿用 v2 既有稽核機制記錄 actor + 狀態轉換（v4 `WorkflowAuditLog` 的等價）。
- 驗證：RBAC 相關測試 + golden 全綠（授權層不動 TMU，golden 應天然不受影響）。

## 一句話

v4 的 reviewer 是「approve 前的獨立品管把關關卡」，扁平角色讓 review≠approve 自然成立；
**若整合 Case 審批流，v2 應新增 `reviewer` 階層（analyst 與 approver 之間）以保留這道分權**，
併入 approver 會弱化四眼原則。**若不整合 Case 審批流，則不需要引入 reviewer**。
