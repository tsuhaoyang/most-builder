# CL-02：口語句子（MI 句）生成（可執行核心邏輯)

> 分類：核心邏輯 ｜ 來源：`calculation_v2.generate_slot_sentence` ＋ `routes/most.py _compose_full_sentence`（v3 實碼）
> 句子是 IE 的交付物：**系統句可重生、人工句另存**（雙欄並存，見 §4）。組句只在後端一處（DISC-07：前端不得自組句）。

## 1. Slot 片段生成（per-slot）

| 參數 | 片段來源 |
|---|---|
| A、B | 不產片段（僅計時；A_move 的手度例外見 §3） |
| G / M / X / I | 選項的 `sentence_text_zh` |
| P | 專用演算法（§2） |

repeat > 1 時片段加後綴 `×N`（如 `推×16`）。

## 2. P 片段演算法（display_rule 三態）

```
visible = base.sentence_text_zh
if 選了 a_insert： visible = "插入"        # show_self：取代 base 動詞
elif 選了 a_snap： visible = "卡合"
if 選了 a_align：  visible = "對準" + visible  # prefix_visible_term：前綴
a_hard / a_press： 不進句子（hidden——只計 TMU）
```

display_rule 是**字典資料**（`rule_p_addons.display_rule`），演算法讀資料執行、不寫死選項字。

## 3. 整句組裝（_compose_full_sentence 規則）

輸入：hand_type、slot 片段、context_fields `{from_location, target_object, component, to_location, where_location}`、show_hand_in_sentence。

```
hand 標籤：left=左手 / right=右手 / both=雙手（show_hand_in_sentence=false 則省略）
GM： [手] 從{from} A1 B1 [G片段] {target_object} {component} A2 B2 [P片段] 至{to} A3
CM： [手] 從{from} A1 B1 [G片段] {target_object} {component} [M片段] 至{to} [X片段] [I片段] {where} A3
空欄位直接跳過（不留占位）；片段間無空白直接串接（中文）。
```

補充規則（v3 字典 dependency）：GM 的 A2 含手度（twist）時，句中插入「翻轉+{target_object}」。

## 4. 系統句 vs 人工句（資料合約）

| 欄位 | 語意 |
|---|---|
| `system_generated_sentence_zh` | 引擎組出，**每次重算覆寫**（可重生快取） |
| `user_edited_sentence_zh` | IE 潤飾稿，系統永不覆寫 |
| `is_manual_edited` + `manual_edit_note` | 標記與原因 |
| 顯示優先序 | user_edited ?? system_generated |

## 5. 驗收條件

- Given base=放(無方向)＋a_align＋a_insert，Then P 片段=「對準插入」且 TMU=6+8+8。
- Given a_hard 勾選，Then 句子不含「較難處理」且 TMU +8。
- Given show_hand_in_sentence=false，Then 句首無手別。
- Given 使用者存過 user_edited 句，When slot 重算，Then user_edited 不變、system_generated 更新。
- Given repeat=16 的 M 推，Then 片段=「推×16」。
