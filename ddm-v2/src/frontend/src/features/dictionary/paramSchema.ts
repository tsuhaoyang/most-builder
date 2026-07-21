/**
 * 七參數分頁 / 次級區塊 / 欄位描述（ADR-023 §2）。
 *
 * 分頁標籤沿用 v3 `PARAM_TABS`（使用者已驗證的字串），但次級區塊是 v2 專有：
 * v3 是單一泛型 `parameter_options` 表，v2 是 12 張不同構子表，故 A/P/M 需分頁內次級 tab。
 *
 * **欄位名＝後端 schema 的 model_fields**（`schemas/v2/rule_set_options.py`）。
 * 這裡不得憑空新增後端沒有的欄位——表格取不到值時顯示「—」。
 */

export type FieldType = 'text' | 'int' | 'float' | 'bool' | 'select'

export interface FieldSpec {
  key: string
  label: string
  type: FieldType
  /** select 的選項；`null` 值代表「未設定」。 */
  choices?: { value: string | null; label: string }[]
  /** 可為 null（送出時給 null 而非空字串）。 */
  nullable?: boolean
  hint?: string
  /** 建立後不可改（code 是 URL 定址鍵，改 code＝刪+建）。 */
  immutableOnEdit?: boolean
}

export interface SectionSpec {
  key: string
  label: string
  kind: 'options' | 'bands'
  fields: FieldSpec[]
  /** 選項型：表格「TMU」欄取哪個欄位（各子表命名不同）。null＝該表無 TMU 概念。 */
  tmuField: string | null
  /** 帶型：上界欄位（顯示於「上界」欄）。 */
  boundField?: string
  /** 帶型：值欄位（指數/TMU）。 */
  valueField?: string
  /** 帶型：分組欄位（rotation 依 revolutions 各自成序）。 */
  groupField?: string
  /** 帶型：末帶必須 open-ended（物理無上界；否則引擎會靜默夾取）。 */
  requireOpenEnded?: boolean
  /** 新增按鈕文案（v3 addLabel 慣例）。 */
  addLabel?: string
}

export interface ParamSpec {
  key: string
  label: string
  sections: SectionSpec[]
}

// ── 共用欄位 ────────────────────────────────────────────────────────
const CODE: FieldSpec = { key: 'code', label: '代碼', type: 'text', immutableOnEdit: true, hint: '僅限英數與 _ . -' }
const LABEL_ZH: FieldSpec = { key: 'label_zh', label: '顯示文字', type: 'text' }
const LABEL_EN: FieldSpec = { key: 'label_en', label: '英文標籤', type: 'text', nullable: true }
const SENTENCE: FieldSpec = { key: 'sentence_text_zh', label: 'WI 句子', type: 'text', nullable: true }
const SORT: FieldSpec = { key: 'sort_order', label: '排序', type: 'int' }
const ACTIVE: FieldSpec = { key: 'is_active', label: '啟用', type: 'bool' }

const optionFields = (...extra: FieldSpec[]): FieldSpec[] => [
  CODE, LABEL_ZH, LABEL_EN, SENTENCE, ...extra, SORT, ACTIVE,
]

// 帶型共用尾欄
const bandTail: FieldSpec[] = [SORT, ACTIVE]

const A_BAND = (component: string, openEnded: boolean): SectionSpec => ({
  key: component,
  label: { reach: '伸手', twist: '手度', foot: '腳步' }[component]!,
  kind: 'bands',
  tmuField: null,
  boundField: 'max_value',
  valueField: 'index_value',
  requireOpenEnded: openEnded,
  fields: [
    { key: 'max_value', label: '上界', type: 'float', nullable: true, hint: '留空＝開放帶（無上界）' },
    { key: 'index_value', label: '指數', type: 'int' },
    ...bandTail,
  ],
})

const M_DIST_BAND = (key: string, label: string): SectionSpec => ({
  key,
  label,
  kind: 'bands',
  tmuField: null,
  boundField: 'max_cm',
  valueField: 'tmu',
  fields: [
    { key: 'max_cm', label: '上界(cm)', type: 'float', nullable: true, hint: '留空＝開放帶' },
    { key: 'tmu', label: 'TMU', type: 'int' },
    ...bandTail,
  ],
})

export const PARAMS: ParamSpec[] = [
  {
    key: 'A',
    label: 'A 距離',
    sections: [
      // reach/foot 物理無上界 → 末帶須開放（rule_set_data.py:63 會靜默夾取）
      A_BAND('reach', true),
      A_BAND('twist', false),
      A_BAND('foot', true),
    ],
  },
  {
    key: 'B',
    label: 'B 身體動作',
    sections: [{
      key: 'default', label: '選項', kind: 'options', tmuField: 'index_value', addLabel: '新增身體動作',
      fields: optionFields(
        { key: 'index_value', label: '指數', type: 'int' },
        { key: 'is_default', label: '預設值', type: 'bool' },
      ),
    }],
  },
  {
    key: 'G',
    label: 'G 取得控制',
    sections: [{
      key: 'default', label: '選項', kind: 'options', tmuField: 'base_tmu', addLabel: '新增取得控制',
      fields: optionFields(
        { key: 'base_tmu', label: 'TMU', type: 'int' },
        { key: 'modifier_key', label: '修飾子', type: 'text', nullable: true },
        { key: 'requires_modifier', label: '需修飾子', type: 'bool' },
      ),
    }],
  },
  {
    key: 'P',
    label: 'P 放置',
    sections: [
      {
        key: 'base', label: '基礎', kind: 'options', tmuField: 'base_tmu', addLabel: '新增放置選項',
        fields: optionFields(
          { key: 'base_tmu', label: 'TMU', type: 'int' },
          { key: 'category', label: '類別', type: 'text', nullable: true },
          { key: 'direction_mode', label: '方向模式', type: 'text', nullable: true },
        ),
      },
      {
        key: 'addon', label: '附加', kind: 'options', tmuField: 'delta_tmu', addLabel: '新增附加選項',
        fields: optionFields(
          { key: 'delta_tmu', label: '增量 TMU', type: 'int' },
          { key: 'needs_precision', label: '需精度', type: 'bool' },
          // 引擎取 min(max_select) 當 p_addon_max → 全表須一致，後端會跨列檢查
          { key: 'max_select', label: '最多可選', type: 'int', hint: '全表必須一致（引擎取最小值當上限）' },
          {
            key: 'display_rule', label: '顯示規則', type: 'select',
            choices: [
              { value: 'show_self', label: '顯示自身' },
              { value: 'hidden', label: '隱藏' },
              { value: 'prefix_visible_term', label: '前置可見詞' },
            ],
          },
        ),
      },
    ],
  },
  {
    key: 'M',
    label: 'M 控制移動',
    sections: [
      {
        key: 'verb', label: '動詞', kind: 'options', tmuField: 'fixed_tmu', addLabel: '新增控制移動',
        fields: optionFields(
          {
            key: 'pricing_kind', label: '計價方式', type: 'select',
            choices: [
              { value: 'fixed', label: '固定值' },
              { value: 'ladder', label: '距離階梯' },
              { value: 'foot', label: '腳步' },
              { value: 'hand', label: '手部角度' },
              { value: 'rotate', label: '旋轉' },
            ],
          },
          { key: 'fixed_tmu', label: '固定 TMU', type: 'int', nullable: true, hint: '計價方式為「固定值」時必填' },
        ),
      },
      M_DIST_BAND('ladder', '距離階梯'),
      M_DIST_BAND('foot', '腳步'),
      {
        key: 'rotation', label: '旋轉', kind: 'bands', tmuField: null,
        boundField: 'max_diameter_cm', valueField: 'tmu', groupField: 'revolutions',
        fields: [
          { key: 'max_diameter_cm', label: '直徑上界(cm)', type: 'float', nullable: true, hint: '留空＝開放帶' },
          { key: 'revolutions', label: '圈數', type: 'int', hint: '1–3；各圈數自成一組帶序' },
          { key: 'tmu', label: 'TMU', type: 'int' },
          ...bandTail,
        ],
      },
      {
        key: 'hand', label: '手部角度', kind: 'bands', tmuField: null,
        boundField: 'max_deg', valueField: 'tmu',
        fields: [
          { key: 'max_deg', label: '角度上界(°)', type: 'float', nullable: true, hint: '留空＝開放帶' },
          { key: 'tmu', label: 'TMU', type: 'int' },
          ...bandTail,
        ],
      },
    ],
  },
  {
    key: 'X',
    label: 'X 製程時間',
    sections: [{
      // X 是秒數制，無 TMU 欄 → 表格 TMU 欄顯示「—」
      key: 'default', label: '選項', kind: 'options', tmuField: null, addLabel: '新增製程選項',
      fields: optionFields(
        {
          key: 'mode', label: '模式', type: 'select',
          choices: [
            { value: 'zero', label: '零' },
            { value: 'seconds', label: '使用者輸入秒數' },
            { value: 'fixed', label: '固定秒數' },
          ],
        },
        { key: 'fixed_seconds', label: '固定秒數', type: 'float', nullable: true, hint: '模式為「固定秒數」時必填' },
      ),
    }],
  },
  {
    key: 'I',
    label: 'I 對位/檢查',
    sections: [{
      key: 'default', label: '選項', kind: 'options', tmuField: 'index_value', addLabel: '新增對位/檢查',
      fields: optionFields(
        { key: 'index_value', label: '指數', type: 'int' },
        {
          key: 'vision_scope', label: '視覺範圍', type: 'select', nullable: true,
          choices: [
            { value: null, label: '（未設定）' },
            { value: 'normal', label: '正常' },
            { value: 'outside', label: '範圍外' },
          ],
        },
      ),
    }],
  },
]

export const getParam = (key: string): ParamSpec => PARAMS.find(p => p.key === key)!
