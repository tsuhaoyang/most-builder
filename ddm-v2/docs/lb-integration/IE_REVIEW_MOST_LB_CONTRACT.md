# IE 審查報告：MOST ↔ LB 整合契約（領域正確性）

> 審查者角色：資深 IE／方法工程／MOST(MiniMOST)／Line Balance 領域（獨立審查子代理產出）。
> 範圍：`MOST_LB_CONTRACT.md`（D1–D14）＋ `TASK_CSV_INPUT_CONTRACT.md`。方法：實讀 v2 code 佐證。唯讀審查。
> 主流程已抽查核實關鍵漏洞（H1 SIMO、H2 machine/manpower）屬實——見 `export_service.py:45/86`（simo 欄）、`:118/130`（machine_count/manpower 已在 to_lb_csv 送出）。
> 標記：【判定】＝IE 專業判斷；【待 User 確認】＝需現場 IE / LB 端定案。

## (1) 總評

契約方法工程邏輯**可信、扎實**（可信度中高 ~75%）。D7(拆乘數防重複乘)、D8(自由度=有界平行非無邊)、D9(不承諾工件級)、D13(結構單向/屬性雙向) 抓到正確且不平凡的重點，多以 code 佐證屬實。

**系統性盲點**：契約逐一對映「LB 契約有的欄位」，卻略過 **v2 引擎真實存在、與工時語義強相關、但 LB 契約無對應欄位**的三個維度——SIMO(雙手同動作)、machine_count/manpower(機台並行/人力複製分攤)、X/I 的機器等待/檢驗時間。前二者是 v2 code 已實作、export 已在送的欄位。這是最需要 User 補的缺口。

## (2) 逐條 D1–D14 IE 觀點（摘要）

- **D1**（1:1）：粒度合理【判定正確】，**但 SIMO 漏洞**：SIMO 從屬列 calculate.py:318-322 貢獻 0 TMU，照 D1 會輸出 duration=0 task，被 LB 當零工時可分站工序 → 低估負載、拆散雙手作業。【待確認 SIMO→LB 對映】
- **D2/D3**（tool）：vocab `_KIND_CK` 含 'tool' 屬實，狀態機+LLM 粗判分工正確【判定】；雙手持工具情境與 SIMO 重疊需確認 lifecycle 不誤判。
- **D4**（cub→group / worker_cub→atomic_group）：讀 code 確認 cub 只隱含同站、不隱含同人連續，正交拆分正確【判定】；提醒：worker_cub 成員 frequency>1 違反 LB atomic quantity≤1，UX 要即時擋。
- **D5**（投影層單一權威）：架構正確【判定】。
- **D6**（組內傳染）：正確必要【判定】；需納入 SIMO 一致性。
- **D7**（frequency=quantity 拆乘數）：**全契約最漂亮的一條**，calculate.py:315 佐證，拆乘數鐵則正確【判定】；待確認「一列內 setup+cyclic 混合」（走動 setup + 多顆 cyclic）是否靠拆列解決。
- **D8**（level→DAG 有界平行）：觀念正確【判定】；**但與現況 build_output 有落差**——現有 `precedence_edges` 只是 level_min 保守相鄰鏈、只連 has_main 列，未實作 D8 的上下界完整框法，sub/cub 內部鏈也沒生成。契約應標註「不可直接沿用 build_output 的 edges，PrecedenceProjector 須依 D8 重新生成」。sub 的對外自由度勿變硬鏈。
- **D9**（segment 不保證工件級）：正確誠實【判定】，對工時標準無影響；IE 使用上需文件明寫「非物件追溯」防誤用。
- **D10/D11/D12/D13/D14**：正確，對齊 LB code 與 v2 語義【判定】，無異議（D13 用 wi_row.id 對應鍵佐證扎實：worksheet.py wi_row.id 版本內穩定）。

## (3) 漏洞與危險假設

- **H1【高】SIMO/雙手同動作完全未對映 LB**：v2 一等公民（`simo_group_id`、ADR-020、從屬列 0 TMU），D1–D14 零著墨。從屬列會以 duration=0 進 LB 被當可分站零工時工序。**最嚴重缺口。** 需定義：從屬列不輸出？主+從標 atomic_group 同站同人？
- **H2【中高】machine_count/manpower 被靜默丟棄**：`level_entry` 有此二欄、level-system-spec §6.2/C1 明定「分攤(時間/N)屬 LB 職責」、現況 `to_lb_csv` 已送（export_service.py:118/130）；但新版 CSV 契約移除且列入「移除欄位」。現況有、新契約丟＝回歸 + 工時語義缺口。需與 LB 端確認機台並行/人力複製分攤走哪個機制。
- **H3【中】X 機器處理/等待時間未區分「人工 vs 機器時間」**：LB 做人力平衡時把機器時間當人的負載會高估人力。自動化站(壓合/熱熔)會出問題。
- **H4【中】走動(A)時間 vs 佈局的循環依賴**：MOST 在 LB 決站別前就用假設佈局算走動 TMU，餵給會改佈局的 LB。固有難題，至少標為已知限制。
- **H5【低-中】檢驗(I)/General 判定重疊**：檢驗常跨零件(對應 General 前抽後插)，但 General 判定本輪未納入 MOST 自動判定。
- **H6【低】一列內 setup+cyclic 混合**（見 D7）。

## (4) 給 User 的建議

**必補（阻擋級）**：
1. 補 **SIMO→LB 對映**條款（新增 D 條）。最大缺口。【需 User + LB 端】
2. 解決 **machine_count/manpower 缺口**（現況送、新契約移除、spec 說 LB 職責，三者矛盾）。【需 User + LB 端】

**應補（重要級）**：
3. 標註 **D8 與現況 build_output 落差**（PrecedenceProjector 須重新生成，勿沿用現有 edges）。
4. 確認 **X 機器時間**是否計入 worker load。
5. **worker_cub 成員 frequency>1 即時擋**寫進 D4/D6 UX 硬規則。

**應確認（釐清級）**：
6. D7 一列內 setup+cyclic 混合是否靠拆列（若是，D1 的 1:1 要補例外）。
7. D9 segment「非物件追溯」的 IE 教育（防誤用）。
8. H4 走動/佈局循環依賴列為已知限制。
9. 檢驗(I)/General(H5) 後續納入範圍。

**強項（無須改）**：D5、D6、D7 拆乘數、D8 有界平行觀念、D9 誠實邊界、D10–D14。
