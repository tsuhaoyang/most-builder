# 核心邏輯驗證 — 測試情境與黃金集說明（Test Catalog）

**文件類型：** 測試情境說明 / 黃金集目錄
**版本：** 1.0
**建立日期：** 2026-06-17
**對應程式：** [scripts/core_logic/minimost_sequence_validator.py](../../scripts/core_logic/minimost_sequence_validator.py)、[scripts/core_logic/level_system_validator.py](../../scripts/core_logic/level_system_validator.py)
**對應規格：** [minimost-sequence-model-core-logic-spec.md](./minimost-sequence-model-core-logic-spec.md)、[level-system-core-logic-spec.md](./level-system-core-logic-spec.md)

> 本文件「**先說清楚每個測試在驗什麼、封了哪個 edge case、抓的是哪種真實錯誤**」，再由 validator 實作。
> 寫測試的目的不是湊綠燈，而是把「IE 會填錯的地方」「來源資料會矛盾的地方」逐一釘死。

---

## 0. 兩個層次的黃金集

| 驗證器 | 黃金集（必須恆真） | 反例集（必須被擋下） |
|--------|-------------------|----------------------|
| Sequence | GM＝28 TMU、CM＝29 TMU；1205 真實工步距離/時間 token → 索引 | 非法選項、結構混用、超量、負值… |
| Level | 教學檔案 7 個範例；跳號/變動層級 | image5 三反例、R1–R9 各違規 |

「黃金集」＝**正向**斷言（這樣填一定算出 X）；「反例集」＝**負向**斷言（這樣填一定報出錯誤碼 Y）。兩者缺一不可：只有正向會放過該擋的錯，只有負向會放過算錯的值。

---

## 1. Sequence Validator 測試情境（逐組詳解）

### A. 黃金教學範例（spec §7）
| 測試 | 輸入 | 期望 | 為何重要 / 封什麼 |
|------|------|------|-------------------|
| GM＝28 | 伸手20→A6, 抓握 G6, 移25→A10, 放無方向 P6 | **28 TMU / 1.008s** | 釘死「合計＝Σindex×1、不乘 10」的口徑（spec Q1）。若有人誤把教科書 ×10 套上，這條立刻紅 |
| CM＝29 | 伸手25→A10, 接觸 G3, 推≤18cm→M16, X0, I0 | **29 TMU** | 同上；並驗證 CM 控制段 M/X/I。**注意 M16＝推 ≤18cm**——理解文件把它標成「30cm」是來源筆誤（30cm→24，見 §3.3） |

### B. A 距離（伸手/手度/腳步，取 max）
| 測試 | 為何重要 / 封什麼 |
|------|-------------------|
| max(伸手6,手度3,腳步0)=6 | A 是三分量**取最大**，不是相加——最常見的實作錯誤是誤加總 |
| max(伸手3,手度6,腳步10)=10 | 確認腳步分量也參與 max |
| 全 0 → 0 | 空動作不貢獻 |
| 20cm→6、20.01cm→10 | **帶邊界**：`≤` 邊界落在低階，超過 0.01 就跳階。off-by-one 的經典點 |
| 999cm→24（伸手封頂）、腳步 999→32 | 超出最大帶要落在最後一階，不可丟例外或回 None |
| 負距離 → 擋下 `A_NEGATIVE` | 負輸入是資料髒，必須報錯而非默默當 0 |

### C. B 身體動作（採 1205 值 0/10/32/42）
| 測試 | 為何重要 |
|------|----------|
| 0/10/32/42 各自正確 | 確認採用 1205 值且**有計入**（修掉 JS 寫死 0 的 gap） |
| B=3 → 擋下 `B_INVALID` | **舊 SEED 值 3/6/18 已廢**；若 DB 殘留舊值流入必須報錯，否則會算出與規格不符的時間 |

### D. G 取得 + 修飾門檻
| 測試 | 為何重要 / 封什麼 |
|------|-------------------|
| 抓握(無需修飾)=6 | 無修飾類直接計 base |
| 接觸已勾 contact=3 | 需修飾類勾了才計 |
| **接觸未勾 contact=0** | **核心陷阱**：需勾修飾卻沒勾 → 視為「動作未完成」計 0，不可給 base。IE 漏勾時系統要反映「這格還沒填完」 |
| 未知選項 → `G_UNKNOWN` | 防止前端傳入不存在的 id |

### E. P 放置（base + ≤2 附加 + 精度門檻）
| 測試 | 為何重要 / 封什麼 |
|------|-------------------|
| 放無方向=6 | base 正確 |
| 組一種+插入+卡合 = 16+8+16=40 | 多附加累加 |
| **對準未勾精度 → 不加（只 base）** | 「對準」要勾「精度<4mm」才 +8；漏判會多算 8 TMU |
| 對準勾精度 → +8 | 反向確認 |
| 超過 2 附加 → `P_TOO_MANY_ADDONS` | 規格上限 2，多選非法 |
| 重複附加 → `P_DUP_ADDON` | 同一附加選兩次是 UI bug |
| 未知附加 → `P_ADDON_UNKNOWN` | 防髒 id |

### F. M 控制移動（取 max / 階梯 / 旋轉 / 手度）
| 測試 | 為何重要 |
|------|----------|
| 推 30cm=24、30.1cm=42 | M 距離階梯邊界（≤30→24、>30→42）。**這裡證明 30cm≠16**，直接打臉來源筆誤 |
| 多分量取 max(理6,手度10)=10 | M 也是分量取 max |
| 按鈕固定=3、旋轉直徑10/2圈=32 | 固定類與旋轉表 |
| 無分量/空 verb=0 | 沒填不貢獻 |
| 未知動詞 → `M_UNKNOWN` | 防髒 id |

### G. X 處理時間（連續 ceil + 固定 0.216）
| 測試 | 為何重要 / 封什麼 |
|------|-------------------|
| 無機台=0 | 預設 |
| 5 秒 → ceil(5/0.036)=139 | 連續換算（spec Q3）。**用 ceil 不用 round**——機台時間寧可高估不可低估 |
| 固定 0.216 → 6 | 掃碼類固定值 |
| 0 秒 → 0；負秒 → `X_NEGATIVE` | 邊界與髒資料 |
| 未知模式 → `X_MODE` | 防錯 |

### H. I 對齊
| 測試 | 為何重要 |
|------|----------|
| 0/6/10/16 正確 | 採 JS 子集 |
| I=3 → `I_INVALID` | 非法索引（教科書 1/3 不在本專案集）必須擋 |

### I. 序列結構（GM↔CM 不可混用）— 最關鍵的結構防線
| 測試 | 為何重要 / 封什麼 |
|------|-------------------|
| GM 的 P slot 帶 m_components → `SLOT_CROSS_MODEL` | **GM 只有 P、沒有 M/X/I；CM 只有 M/X/I、沒有 P**。前端切換 GM/CM 沒清乾淨殘留欄位 = 最危險的靜默錯誤，必須結構性擋下 |
| CM 的 slot5 帶 p_base → `SLOT_CROSS_MODEL` | 反向 |
| 未知 seq → `SEQ_KIND` | 只允許 GM/CM |

### J. 整表 SIMO / frequency
| 測試 | 為何重要 |
|------|----------|
| 56 + max(29,29)=85 | SIMO 群組**只取群組內最大**，非 SIMO 列全計。算錯會高估雙手同時動作的工時 |
| frequency≤0 → `FREQ_INVALID` | 次數須 ≥1 |

---

## 2. Level Validator 測試情境（逐組詳解）

### A. 七個教學範例（spec §7，皆應**合法**＝0 issue）
| 範例 | 驗的邏輯 | 為何重要 |
|------|----------|----------|
| Ex1 純序列 main 1..10 | 最基本 precedence | 確認「每動作各一層」可填 |
| Ex2 ABC 同層並行 | 同 Level 數字 = 可並行 | **同層並行**是 LB 自由度來源；不可被誤判為衝突 |
| Ex3 sub1 群組 | 軟綁定 + 群組內 order | sub 給子集獨立順序 |
| Ex4 cub1 群組 | 硬綁定（同站） | sub↔cub 只差語意，填法相同 |
| Ex5 變動層級 1~2 + cub + sub | 跳躍 + 巢狀並存 | 同時驗 `~` 解析與多群組 |
| Ex6 nb1 count1 逼分站 | 分割限制 | nb 單獨用（不與 cub 衝突）要合法 |
| 列舉 1/3、跳號 1,2,5 | 變動語法與跳號 | spec Q2/Q3 確認項 |

### B. image5 三個反例（IE 易犯，必須**擋下**）
| 反例 | 錯誤碼 | 真實錯誤 |
|------|--------|----------|
| 歸屬不明(C) | `R3_ORPHAN` | 成員列忘了填 Countersignature，系統無法判斷它屬於哪組 |
| sub 重複定義歸屬(G) | `R2_REDEFINE` | 成員列(order≥2)又自填了 main+Level，與「繼承頭列」矛盾 |
| cub 內加 nb 分割(H/I) | `R6_NB_VS_CUB` | cub 要同站、nb count1 又逼分站 → 邏輯不可能同時成立 |

> 這三條正是 User 強調的：**Level System 的價值就是把 IE 的填寫錯誤擋在源頭**。

### C. R1–R9 其他 edge cases
| 測試 | 錯誤碼 | 封什麼 |
|------|--------|--------|
| 頭列無 main | `R1_HEAD_NO_MAIN` | 群組頭列(order1)必須錨定一個 main+Level |
| Ascription 非 main | `R4_ASCRIPTION` | Ascription 只能是 main 或空 |
| main 當 Countersignature | `R4_COUNTERSIG` | main 永不可當子群組名 |
| level=0 / abc / 2~1 | `R7_LEVEL_FORMAT` | 非正整數、亂碼、反向範圍 |
| 主序倒退 | `R7_NON_DECREASING` | 後列 main 比前列小（以 min-level 為鍵）|
| order 跳號 / 重複 | `R8_ORDER_GAP` / `R8_MULTI_HEAD` | 群組內 order 須 1..k 連續、單一頭列 |
| Number 無 Count / 反之 | `NB_COUNT_MISSING` / `NB_NAME_MISSING` | nb 標籤與數量必須成對 |
| nb count 不一致 | `NB_COUNT_INCONSISTENT` | 同一 nb 標籤在不同列填了不同上限 |
| 系數 0 | `COEF_INVALID` | 寬放係數須 >0（否則動作時長歸零）|
| 群組列缺 order | `ORDER_MISSING` | 有 Countersignature 必須有 order |

---

## 3. 1205 第 96–117 列 — 擴充黃金集（真實工廠工步）

來源：`MOST系統邏輯1205.xlsx › 工作表「MOST 系统逻辑」` 第 96–117 列的 METHOD 長敘事（K 欄）。這是真實產線 WI 句子，是把計算邏輯對到**真實輸入**的最佳素材。

### 3.1 真實 token → 索引（**客觀、無歧義**，直接斷言）

從 22 列敘事抽出所有距離/時間 token，依 spec §4 表對應：

| token 類型 | 真實出現值 | spec 表 | 期望索引/TMU |
|-----------|-----------|---------|--------------|
| 伸手 reach | 40cm | A 伸手帶（≤60→16）| **16** |
| 伸手 reach | 60cm | A 伸手帶（≤60→16）| **16** |
| 移動 reach(放段) | 10cm | A 伸手帶（≤10→3）| **3** |
| 移動 reach(放段) | 20cm | A 伸手帶（≤20→6）| **6** |
| 移動 reach(放段) | 40cm | A 伸手帶（≤60→16）| **16** |
| 移動 reach(放段) | 60cm | A 伸手帶（≤60→16）| **16** |
| M 階梯距離 | 理 20cm | M 距離階梯（≤30→24）| **24** |
| X 處理時間 | 10S | X 連續 ceil(10/0.036)| **278** |

> **重點對照**：同樣 20cm，當「伸手/移動(A)」是 **6**，當「理/推(M 階梯)」是 **24**——**context 決定用哪張表**。驗證器把這兩條都釘住，防止實作把 A 與 M 的距離表搞混。

### 3.2 重複記號 `(*n)`
敘事中的 `[…](*2)`、`(*3)`、`(*4)` ＝該段落 **frequency＝n**（整段 TMU ×n）。驗證器以 frequency 機制覆蓋（§1.J）。

### 3.3 兩則完整工步解構（**詮釋性，標註假設，待 IE 複核**）

> 下列把真實敘事解構成 slot，TMU 由驗證器函式算出。**距離→索引客觀，但「動詞→G/P/M 選項」與「方向/精度」屬詮釋**，標 ⚠️ 之處待 IE 確認（列入規格 §14）。

**範例 R112（GM）：** 「(伸手60cm)右手從泡棉抓握 bezel 的右上角，對準組到 Cover 並卡合 (*2)」
| slot | 解讀 | 值 |
|------|------|----|
| A0 | 伸手 60cm | 16 |
| B1 | 無 | 0 |
| G2 | 抓握 | 6 |
| A3 | ⚠️ 未明示移動距離，暫記 0 | 0 |
| B4 | 無 | 0 |
| P5 | ⚠️「對準組+卡合」＝組(一種方向 16)+對準(需精度?+8)+卡合(+16)；暫設精度未勾 | 16+16=32 |
| A6 | 返回，暫 0 | 0 |
| 合計 ×freq2 | (16+0+6+0+0+32+0)=54 ×2 | **108** |

**範例 R116（CM）：** 「(伸手60cm)雙手按壓 LCD&Bezel 壓合治具的啟動按鈕，壓合(10S)LCD」
| slot | 解讀 | 值 |
|------|------|----|
| A0 | 伸手 60cm | 16 |
| B1 | 無 | 0 |
| G2 | ⚠️ 按壓啟動鈕，視為接觸(需勾)＝3 | 3 |
| M3 | 按動按鈕（固定）| 3 |
| X4 | 壓合 10S → ceil(10/0.036) | 278 |
| I5 | ⚠️ 無明示對齊，暫 0 | 0 |
| A6 | 返回，暫 0 | 0 |
| 合計 | 16+0+3+3+278+0+0 | **300** |

> ⚠️ 這兩則的 ⚠️ 假設（P 方向/精度、A 返回距離、G 動作判定）需 IE 複核；在那之前，測試斷言的是「**依此解構，驗證器算出 108 / 300**」——用途是 (1) 鎖定計算一致性、(2) 給 IE 一份具體可校正的解構樣本。

---

## 4. 錯誤碼總表

**Sequence：** `A_NEGATIVE` `B_INVALID` `G_UNKNOWN` `P_UNKNOWN` `P_TOO_MANY_ADDONS` `P_DUP_ADDON` `P_ADDON_UNKNOWN` `M_UNKNOWN` `M_NEGATIVE` `M_KIND` `X_MODE` `X_NEGATIVE` `I_INVALID` `SEQ_KIND` `SLOT_CROSS_MODEL` `FREQ_INVALID`

**Level：** `COEF_INVALID` `R1_HEAD_NO_MAIN` `R2_REDEFINE` `R3_ORPHAN` `R4_ASCRIPTION` `R4_COUNTERSIG` `R6_NB_VS_CUB` `R7_LEVEL_FORMAT` `R7_NON_DECREASING` `R8_DUP_ORDER` `R8_ORDER_GAP` `R8_MULTI_HEAD` `NB_FORMAT` `NB_COUNT_MISSING` `NB_NAME_MISSING` `NB_COUNT_INCONSISTENT` `ORDER_INVALID` `ORDER_MISSING`

---

## 5. 怎麼跑

```bash
cd ddm-v2
python3 scripts/core_logic/minimost_sequence_validator.py   # exit 0 = 全綠
python3 scripts/core_logic/level_system_validator.py
```

或用 harness skill（見 [scripts/core_logic/README.md](../../scripts/core_logic/README.md)）一鍵跑全部並彙總。

---

*本目錄與兩個 validator 同步維護；新增測試前，先在此說明「驗什麼、封什麼」，再實作。*
