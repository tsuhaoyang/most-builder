# MOST Rule-set 參數對照表：`MINIMOST_FACTORY_V2`

TMU 口徑：cycle 合計 = Σ(各 slot index)；1 TMU = 0.036 秒。
A 的 `max_value` = 檔位上界（`<=` 落該帶，超過落下一帶）。
M 動詞依 `pricing_kind` 查 fixed/ladder(距離)/rotate/hand/foot 對應表。
X 以秒數經 half-up 3 位轉 TMU。

## A

### A/foot

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | foot <= 20 cm |  | 6 | <= 20 cm | 距離帶 |
|  | foot <= 30 cm |  | 10 | <= 30 cm | 距離帶 |
|  | foot <= 45 cm |  | 16 | <= 45 cm | 距離帶 |
|  | foot <= 65 cm |  | 24 | <= 65 cm | 距離帶 |
|  | foot > 上一檔 (cm) |  | 32 | > 上一檔 (cm) | 距離帶 |

### A/reach

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | reach <= 2.5 cm |  | 0 | <= 2.5 cm | 距離帶 |
|  | reach <= 5 cm |  | 1 | <= 5 cm | 距離帶 |
|  | reach <= 10 cm |  | 3 | <= 10 cm | 距離帶 |
|  | reach <= 20 cm |  | 6 | <= 20 cm | 距離帶 |
|  | reach <= 35 cm |  | 10 | <= 35 cm | 距離帶 |
|  | reach <= 60 cm |  | 16 | <= 60 cm | 距離帶 |
|  | reach > 上一檔 (cm) |  | 24 | > 上一檔 (cm) | 距離帶 |

### A/twist

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | twist <= 30 deg |  | 0 | <= 30 deg | 距離帶 |
|  | twist <= 60 deg |  | 1 | <= 60 deg | 距離帶 |
|  | twist <= 120 deg |  | 3 | <= 120 deg | 距離帶 |
|  | twist <= 180 deg |  | 6 | <= 180 deg | 距離帶 |

## B

### B

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| b_none | 無身體動作 | No body motion | 0 |  |  |
| b_eye | 眼部動作 | Eye action | 10 |  |  |
| b_bend | 起身或彎腰/坐 | Stand up or bend/sit | 32 |  |  |
| b_stand | 站 | Stand | 42 |  |  |

## G

### G

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| g_tap | 輕按 | Tap | 3 |  |  |
| g_touch | 接觸 | Touch | 3 |  |  |
| g_pat | 輕拍 | Pat | 3 |  |  |
| g_grasp | 抓握 | Grasp | 6 |  |  |
| g_grab | 抓取 | Grab | 6 |  |  |
| g_regrasp | 重新抓握 | Regrasp | 6 |  |  |
| g_handchange | 換手(轉移) | Hand change (transfer) | 10 |  |  |
| g_pick_sel | 拿取(選取) | Pick up (select) | 10 |  |  |
| g_pick_small | 拿取(選取-小) | Pick up (select, small) | 16 |  |  |
| g_pullout | 拔出(分離) | Pull out (separate) | 16 |  |  |
| g_pick_collect | 拿取(收集) | Pick up (collect) | 24 |  |  |

## P

### P/base

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| p_toss | 丟 | Toss | 3 |  | toss |
| p_hold | 保持住 | Hold in place | 3 |  | hold |
| p_place_none | 放(無方向) | Place (no direction) | 6 |  | place / none |
| p_place_multi | 放(多種方向) | Place (multi-direction) | 10 |  | place / multi |
| p_place_single | 放(一種方向) | Place (single direction) | 16 |  | place / single |
| p_asm_multi | 組(多種方向) | Assemble (multi-direction) | 10 |  | assemble / multi |
| p_asm_single | 組(一種方向) | Assemble (single direction) | 16 |  | assemble / single |

### P/addon

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| a_align | 對準(精度<4mm) | Align (precision <4mm) | +8 | 附加項 | max_select=2 |
| a_insert | 插入 | Insert | +8 | 附加項 | max_select=2 |
| a_hard | 較難處理 | Difficult to handle | +8 | 附加項 | max_select=2 |
| a_snap | 卡合 | Snap fit | +16 | 附加項 | max_select=2 |
| a_press | 施加壓力 | Apply pressure | +16 | 附加項 | max_select=2 |

## M

### M/verb

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| m_btn | 按動按鈕 | Press button | 3 |  | pricing=fixed |
| m_screw | 滑出螺絲 | Screw release | 3 |  | pricing=fixed |
| m_li | 理 | Dress | (查ladder表) |  | pricing=ladder |
| m_through | 穿 | Thread | (查ladder表) |  | pricing=ladder |
| m_push | 推 | Push | (查ladder表) |  | pricing=ladder |
| m_pull | 拉 | Pull | (查ladder表) |  | pricing=ladder |
| m_attach | 貼附 | Attach | (查ladder表) |  | pricing=ladder |
| m_remove | 去除 | Remove | (查ladder表) |  | pricing=ladder |
| m_teartape | 撕除 | Peel off (tape) | (查ladder表) |  | pricing=ladder |
| m_fold | 折 | Fold | (查ladder表) |  | pricing=ladder |
| m_wipe | 擦拭 | Wipe | (查ladder表) |  | pricing=ladder |
| m_tearopen | 撕開 | Tear open | (查ladder表) |  | pricing=ladder |
| m_rotate | 旋轉 | Rotate | (查rotate表) |  | pricing=rotate |
| m_press | 按壓 | Press | 3 |  | pricing=fixed |
| m_hand | 手度 | Hand turn | (查hand表) |  | pricing=hand |
| m_foot | 腳步 | Foot step | (查foot表) |  | pricing=foot |

### M/hand

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | <= 90 deg |  | 6 | <= 90 deg |  |
|  | <= 180 deg |  | 10 | <= 180 deg |  |

### M/foot

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | <= 25 cm |  | 10 | <= 25 cm |  |
|  | <= 40 cm |  | 16 | <= 40 cm |  |
|  | <= 55 cm |  | 24 | <= 55 cm |  |
|  | <= 75 cm |  | 32 | <= 75 cm |  |
|  | > 上一檔 (cm) |  | 42 | > 上一檔 (cm) |  |

### M/ladder(距離)

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | <= 2.5 cm |  | 3 | <= 2.5 cm |  |
|  | <= 10 cm |  | 6 | <= 10 cm |  |
|  | <= 25 cm |  | 10 | <= 25 cm |  |
|  | <= 45 cm |  | 16 | <= 45 cm |  |
|  | <= 75 cm |  | 24 | <= 75 cm |  |

### M/rotate

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
|  | <= 12.5 cm × 1圈 |  | 16 | <= 12.5 cm rev=1 |  |
|  | <= 12.5 cm × 2圈 |  | 32 | <= 12.5 cm rev=2 |  |
|  | <= 12.5 cm × 3圈 |  | 42 | <= 12.5 cm rev=3 |  |
|  | <= 50 cm × 1圈 |  | 24 | <= 50 cm rev=1 |  |
|  | <= 50 cm × 2圈 |  | 42 | <= 50 cm rev=2 |  |

## X

### X

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| x_none | 無機台等待 | No machine wait | (zero) | mode=zero | X 口徑：秒→TMU，half-up 3 位 |
| x_press | 並壓合機台 | Press-fit machine | (seconds) | mode=seconds | X 口徑：秒→TMU，half-up 3 位 |
| x_snap_press | 並卡合&壓合機台 | Snap & press machine | (seconds) | mode=seconds | X 口徑：秒→TMU，half-up 3 位 |
| x_heat | 並熱熔機台 | Heat-melt machine | (seconds) | mode=seconds | X 口徑：秒→TMU，half-up 3 位 |
| x_glue | 並點膠 | Dispense glue | (seconds) | mode=seconds | X 口徑：秒→TMU，half-up 3 位 |
| x_screw_fix | 並鎖附固定(鎖附順序如圖所示) | Screw fastening (per diagram sequence) | 0.216s→TMU | mode=fixed | X 口徑：秒→TMU，half-up 3 位 |
| x_laser | 並鐳雕 | Laser marking | (seconds) | mode=seconds | X 口徑：秒→TMU，half-up 3 位 |
| x_scan_ppid | 刷PPID | Scan PPID | 0.216s→TMU | mode=fixed | X 口徑：秒→TMU，half-up 3 位 |
| x_scan_wo | 刷工單二維碼 | Scan work-order QR code | 0.216s→TMU | mode=fixed | X 口徑：秒→TMU，half-up 3 位 |
| x_scan_bar | 刷條形碼 | Scan barcode | 0.216s→TMU | mode=fixed | X 口徑：秒→TMU，half-up 3 位 |
| x_blow_clean | 並吹風清潔 | Air-blow clean | (seconds) | mode=seconds | X 口徑：秒→TMU，half-up 3 位 |

## I

### I

| code | label_zh | label_en | index/TMU | 條件 | 備註 |
|---|---|---|---|---|---|
| i_none | 不額外對齊 | No additional alignment | 0 |  |  |
| i_check | 並檢查(正常視線範圍) | Check (normal vision) | 6 |  | vision_scope=normal |
| i_confirm | 並確認(正常視線範圍) | Confirm (normal vision) | 6 |  | vision_scope=normal |
| i_align1 | 並對準(正常視線範圍到點) | Align to point (normal vision) | 10 |  | vision_scope=normal |
| i_align2 | 並對齊(正常視線範圍到兩點) | Align to two points (normal vision) | 16 |  | vision_scope=normal |
| i_check_out | 並檢查(正常視線範圍外) | Check (outside normal vision) | 16 |  | vision_scope=outside |
| i_confirm_out | 並確認(正常視線範圍外) | Confirm (outside normal vision) | 16 |  | vision_scope=outside |
| i_align1_out | 並對準(正常視線範圍外到點) | Align to point (outside normal vision) | 24 |  | vision_scope=outside |
| i_align2_out | 並對齊(正常視線範圍外到兩點) | Align to two points (outside normal vision) | 32 |  | vision_scope=outside |
