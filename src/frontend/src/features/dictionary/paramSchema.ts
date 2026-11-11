/**
 * 七參數分頁 / 次級區塊 / 欄位描述（ADR-023 §2）。
 *
 * 分頁標籤沿用 v3 `PARAM_TABS`（使用者已驗證的字串），但次級區塊是 v2 專有：
 * v3 是單一泛型 `parameter_options` 表，v2 是 12 張不同構子表，故 A/P/M 需分頁內次級 tab。
 *
 * **欄位名＝後端 schema 的 model_fields**（`schemas/v2/rule_set_options.py`）。
 * 這裡不得憑空新增後端沒有的欄位——表格取不到值時顯示「—」。
 *
 * ADR-032 Phase A：本檔只存 **i18n key**（`labelKey`／`hintKey`／`addLabelKey`），
 * 字面值在 `shared/i18n/resources/*.ts` 的 `dictionary.*`。這是模組層級常數、
 * 不在元件內，拿不到 `useTranslation()`；存 key 讓語言切換時整棵表跟著重繪，
 * 而不是把某一次渲染時的字串釘死在模組載入的當下。
 */

export type FieldType = 'text' | 'int' | 'float' | 'bool' | 'select'

export interface FieldSpec {
  key: string
  /** i18n key（`dictionary.field.*`）。 */
  labelKey: string
  type: FieldType
  /** select 的選項；`null` 值代表「未設定」。`labelKey` 屬 `dictionary.choice.*`。 */
  choices?: { value: string | null; labelKey: string }[]
  /** 可為 null（送出時給 null 而非空字串）。 */
  nullable?: boolean
  /** i18n key（`dictionary.hint.*`）。 */
  hintKey?: string
  /** 建立後不可改（code 是 URL 定址鍵，改 code＝刪+建）。 */
  immutableOnEdit?: boolean
}

export interface SectionSpec {
  key: string
  /** i18n key（`dictionary.section.*`）。 */
  labelKey: string
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
  /** 新增按鈕文案的 i18n key（`dictionary.addLabel.*`；v3 addLabel 慣例）。 */
  addLabelKey?: string
}

export interface ParamSpec {
  key: string
  /** i18n key（`dictionary.param.*`）。 */
  labelKey: string
  sections: SectionSpec[]
}

// ── 共用欄位 ────────────────────────────────────────────────────────
const CODE: FieldSpec = { key: 'code', labelKey: 'code', type: 'text', immutableOnEdit: true, hintKey: 'code' }
const LABEL_ZH: FieldSpec = { key: 'label_zh', labelKey: 'label_zh', type: 'text' }
const LABEL_EN: FieldSpec = { key: 'label_en', labelKey: 'label_en', type: 'text', nullable: true }
const SENTENCE: FieldSpec = { key: 'sentence_text_zh', labelKey: 'sentence_text_zh', type: 'text', nullable: true }
const SORT: FieldSpec = { key: 'sort_order', labelKey: 'sort_order', type: 'int' }
const ACTIVE: FieldSpec = { key: 'is_active', labelKey: 'is_active', type: 'bool' }

const optionFields = (...extra: FieldSpec[]): FieldSpec[] => [
  CODE, LABEL_ZH, LABEL_EN, SENTENCE, ...extra, SORT, ACTIVE,
]

// 帶型共用尾欄
const bandTail: FieldSpec[] = [SORT, ACTIVE]

const A_BAND = (component: string, openEnded: boolean): SectionSpec => ({
  key: component,
  labelKey: component,
  kind: 'bands',
  tmuField: null,
  boundField: 'max_value',
  valueField: 'index_value',
  requireOpenEnded: openEnded,
  fields: [
    { key: 'max_value', labelKey: 'max_value', type: 'float', nullable: true, hintKey: 'maxValue' },
    { key: 'index_value', labelKey: 'index_value', type: 'int' },
    ...bandTail,
  ],
})

const M_DIST_BAND = (key: string): SectionSpec => ({
  key,
  labelKey: key,
  kind: 'bands',
  tmuField: null,
  boundField: 'max_cm',
  valueField: 'tmu',
  fields: [
    { key: 'max_cm', labelKey: 'max_cm', type: 'float', nullable: true, hintKey: 'openBand' },
    { key: 'tmu', labelKey: 'tmu', type: 'int' },
    ...bandTail,
  ],
})

export const PARAMS: ParamSpec[] = [
  {
    key: 'A',
    labelKey: 'A',
    sections: [
      // reach/foot 物理無上界 → 末帶須開放（rule_set_data.py:63 會靜默夾取）
      A_BAND('reach', true),
      A_BAND('twist', false),
      A_BAND('foot', true),
    ],
  },
  {
    key: 'B',
    labelKey: 'B',
    sections: [{
      key: 'default', labelKey: 'default', kind: 'options', tmuField: 'index_value', addLabelKey: 'body',
      fields: optionFields(
        { key: 'index_value', labelKey: 'index_value', type: 'int' },
        { key: 'is_default', labelKey: 'is_default', type: 'bool' },
      ),
    }],
  },
  {
    key: 'G',
    labelKey: 'G',
    sections: [{
      key: 'default', labelKey: 'default', kind: 'options', tmuField: 'base_tmu', addLabelKey: 'get',
      fields: optionFields(
        { key: 'base_tmu', labelKey: 'base_tmu', type: 'int' },
        { key: 'modifier_key', labelKey: 'modifier_key', type: 'text', nullable: true },
        { key: 'requires_modifier', labelKey: 'requires_modifier', type: 'bool' },
      ),
    }],
  },
  {
    key: 'P',
    labelKey: 'P',
    sections: [
      {
        key: 'base', labelKey: 'base', kind: 'options', tmuField: 'base_tmu', addLabelKey: 'placeBase',
        fields: optionFields(
          { key: 'base_tmu', labelKey: 'base_tmu', type: 'int' },
          { key: 'category', labelKey: 'category', type: 'text', nullable: true },
          { key: 'direction_mode', labelKey: 'direction_mode', type: 'text', nullable: true },
        ),
      },
      {
        key: 'addon', labelKey: 'addon', kind: 'options', tmuField: 'delta_tmu', addLabelKey: 'placeAddon',
        fields: optionFields(
          { key: 'delta_tmu', labelKey: 'delta_tmu', type: 'int' },
          { key: 'needs_precision', labelKey: 'needs_precision', type: 'bool' },
          // 引擎取 min(max_select) 當 p_addon_max → 全表須一致，後端會跨列檢查
          { key: 'max_select', labelKey: 'max_select', type: 'int', hintKey: 'maxSelect' },
          {
            key: 'display_rule', labelKey: 'display_rule', type: 'select',
            choices: [
              { value: 'show_self', labelKey: 'display_rule.show_self' },
              { value: 'hidden', labelKey: 'display_rule.hidden' },
              { value: 'prefix_visible_term', labelKey: 'display_rule.prefix_visible_term' },
            ],
          },
        ),
      },
    ],
  },
  {
    key: 'M',
    labelKey: 'M',
    sections: [
      {
        key: 'verb', labelKey: 'verb', kind: 'options', tmuField: 'fixed_tmu', addLabelKey: 'moveVerb',
        fields: optionFields(
          {
            key: 'pricing_kind', labelKey: 'pricing_kind', type: 'select',
            choices: [
              { value: 'fixed', labelKey: 'pricing_kind.fixed' },
              { value: 'ladder', labelKey: 'pricing_kind.ladder' },
              { value: 'foot', labelKey: 'pricing_kind.foot' },
              { value: 'hand', labelKey: 'pricing_kind.hand' },
              { value: 'rotate', labelKey: 'pricing_kind.rotate' },
            ],
          },
          { key: 'fixed_tmu', labelKey: 'fixed_tmu', type: 'int', nullable: true, hintKey: 'fixedTmu' },
        ),
      },
      M_DIST_BAND('ladder'),
      M_DIST_BAND('foot'),
      {
        key: 'rotation', labelKey: 'rotation', kind: 'bands', tmuField: null,
        boundField: 'max_diameter_cm', valueField: 'tmu', groupField: 'revolutions',
        fields: [
          { key: 'max_diameter_cm', labelKey: 'max_diameter_cm', type: 'float', nullable: true, hintKey: 'openBand' },
          { key: 'revolutions', labelKey: 'revolutions', type: 'int', hintKey: 'revolutions' },
          { key: 'tmu', labelKey: 'tmu', type: 'int' },
          ...bandTail,
        ],
      },
      {
        key: 'hand', labelKey: 'hand', kind: 'bands', tmuField: null,
        boundField: 'max_deg', valueField: 'tmu',
        fields: [
          { key: 'max_deg', labelKey: 'max_deg', type: 'float', nullable: true, hintKey: 'openBand' },
          { key: 'tmu', labelKey: 'tmu', type: 'int' },
          ...bandTail,
        ],
      },
    ],
  },
  {
    key: 'X',
    labelKey: 'X',
    sections: [{
      // X 是秒數制，無 TMU 欄 → 表格 TMU 欄顯示「—」
      key: 'default', labelKey: 'default', kind: 'options', tmuField: null, addLabelKey: 'process',
      fields: optionFields(
        {
          key: 'mode', labelKey: 'mode', type: 'select',
          choices: [
            { value: 'zero', labelKey: 'mode.zero' },
            { value: 'seconds', labelKey: 'mode.seconds' },
            { value: 'fixed', labelKey: 'mode.fixed' },
          ],
        },
        { key: 'fixed_seconds', labelKey: 'fixed_seconds', type: 'float', nullable: true, hintKey: 'fixedSeconds' },
      ),
    }],
  },
  {
    key: 'I',
    labelKey: 'I',
    sections: [{
      key: 'default', labelKey: 'default', kind: 'options', tmuField: 'index_value', addLabelKey: 'align',
      fields: optionFields(
        { key: 'index_value', labelKey: 'index_value', type: 'int' },
        {
          key: 'vision_scope', labelKey: 'vision_scope', type: 'select', nullable: true,
          choices: [
            { value: null, labelKey: 'vision_scope.unset' },
            { value: 'normal', labelKey: 'vision_scope.normal' },
            { value: 'outside', labelKey: 'vision_scope.outside' },
          ],
        },
      ),
    }],
  },
]

export const getParam = (key: string): ParamSpec => PARAMS.find(p => p.key === key)!
