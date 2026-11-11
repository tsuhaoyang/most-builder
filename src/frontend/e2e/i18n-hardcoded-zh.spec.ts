/**
 * §R4 UI 外殼字串外部化守衛（ADR-032 R4）。
 *
 * R4 原文：「Phase A 完成後立即加 CI 守衛（新增 `.tsx` 不得含中文字面值），
 * 把守衛與外部化同批交付，不要留到『之後補』。」
 *
 * **範圍取「全樹」而不是「新增檔案」**：diff-based 守衛要靠 base ref 才算得出「新增」，
 * 在 `push` 到任意分支時 base 未必存在；而 Phase A 四批做完後全樹本來就該是乾淨的，
 * 全樹掃描既嚴格又不需要 git 上下文，並且**完整涵蓋** R4 想擋的那件事（新程式碼硬編中文）。
 *
 * **只擋碼內字面值，不擋註解**：註解維持中文是本 repo 的既有慣例（Phase A 四批都明文
 * 不動註解）。所以整道守衛的地基是那支剝離器——它若把該擋的當成註解剝掉，守衛會**安靜地
 * 永遠綠**。§R4-4／§R4-5 就是為了讓這件事不可能發生（「沒看過它紅過的守門不算守門」，
 * 見 `docs/architecture/v2-authoritative-model-guide.md` §6）。
 *
 * **兩種豁免，兩者都必須寫在註解裡、都要寫理由**：
 *   - 行級 `// i18n-exempt: <理由>`（同一行行尾，或緊鄰的前一行）——單點例外用這個。
 *   - 檔級 `i18n-exempt-file[<漢字預算>]: <理由>`（**限檔頭**，第一行程式碼之前）——
 *     整檔待重寫、現在外部化等於付兩次工的情況用這個。
 *
 * **兩者都只認註解裡的標記**：剝離註解後標記還看得到，就代表它躲在字串字面值中，
 * 不予採信（否則 `const s = '… // i18n-exempt: 理由'` 一行字串就能把那一行、
 * 或把整個檔案消音）。這條對行級與檔級**對稱**——H1 就是從只做了檔級的缺口漏出來的。
 *
 * **檔級豁免帶漢字預算**（`i18n-exempt-file[72]:`）：斷言該檔剝離註解後的漢字數
 * **不得超過**當初記錄的值。沒有預算的話，檔級豁免是個永久盲區——`stale-file-exemption`
 * 只在「整份乾淨了」才報，對「越長越多」全盲，零引用的檔案最適合當垃圾堆。預算只准降
 * 不准升；升要改那個數字，改動會直接出現在 diff 裡。
 *
 * 兩種豁免都會**過期偵測**：行級豁免指向的那行已經沒有中文、或檔級豁免的檔案已經整份
 * 乾淨了，都報錯，不讓標記在檔案裡積灰。兩者也**不得並存**於同一檔——檔級豁免生效期間
 * 行級標記永遠不會被觀察到過期，那正是標記積灰的溫床。
 *
 * **理由必填擋得住什麼**：只擋空白／純標點（`reasonIsSubstantive`）。`TODO`、`aaaa`
 * 這種敷衍理由**擋不住**——理由是否成立本質上是人工判斷關卡，這裡只保證「有人寫了字」，
 * 不要把它當成比實際更強的保證。
 *
 * 執行：npx playwright test e2e/i18n-hardcoded-zh.spec.ts（純 node，不需要瀏覽器或後端）
 */
import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SRC_DIR = path.resolve(HERE, '../src')

/** CJK 統一表意文字。刻意**不含**全形標點（`、`／`（）`）——那些在中英文都會出現於程式碼。 */
const HAN = /[一-鿿]/

/**
 * 掃描範圍外的兩類檔案：
 *  1. i18n 資源檔本體——它的**內容**就是中文，那是它的工作。
 *     （順帶：`en.ts` 的 `zhTW: '中文'` 因此不需要 inline 豁免標記，不要重複。）
 *  2. `shared/types/api.d.ts`——OpenAPI 產生物，`不可手改`（CLAUDE.md），
 *     中文來自後端 schema 的 description，不是前端硬編。
 */
const EXCLUDED: RegExp[] = [
  /[/\\]shared[/\\]i18n[/\\]resources[/\\][^/\\]+\.ts$/,
  /[/\\]shared[/\\]types[/\\]api\.d\.ts$/,
]

export interface Hit { file: string; line: number; rule: string; detail: string }

/**
 * 把註解換成等長空白（保留行號與欄位），字串／樣板字面值原樣留下。
 *
 * **為什麼字串要留下**：本守衛數的是「註解以外的中文」，字串內與 JSX 文字節點都算違規。
 * `<h2>匯出</h2>` 的中文根本不在引號裡——只掃字串字面值的掃描器會漏掉這一類，
 * 而它正是本 repo 最大宗的違規形態。
 *
 * **單引號／雙引號字串遇到換行即視為脫序**：JS 的 `'`／`"` 字串不能跨行，所以那代表
 * 這支狀態機被某個它看不懂的東西帶偏了。遇到就**在行尾強制回到程式碼狀態並記錄**，
 * 讓損害侷限在那一行而不是往下擴散整個檔案；記錄本身由 §R4-3 當成違規報出來
 * （fail-closed：看不懂就出聲，不要默默略過）。
 *
 * **regex literal 單獨辨識**（`REGEX_LITERAL_RE`）。少了它，`/[/*]/` 裡的區塊註解
 * 開頭記號會讓剝離器誤入 `'block'` 狀態，**一路吃到下一個區塊註解結尾記號**——跨行、
 * 而且 `'block'` 沒有任何脫序偵測，中文會安靜蒸發（實測三行 JSX 中文全滅、連 desync
 * 都不報）。
 * 判定方式刻意**不用狀態機**，而是「前一個非空白字元允許 regex 開頭」＋「同一行內能
 * 完整閉合」的前瞻比對（JS 的 regex literal 不能跨行，所以行內閉合是硬條件）：
 *   - 判成 regex 但其實是除號 → 那一段原樣留在程式碼裡＝往**多報**掉（安全方向）；
 *   - 判成除號但其實是 regex → 退回本守衛既有的行為（regex 內容當程式碼掃）。
 *   - 兩種誤判都**不會**讓狀態機卡住往下吃——因為根本沒有「regex 狀態」可卡。
 * 「吃到下一個未轉義 `/` 為止」的狀態機版本在這份程式碼會炸：JSX 的多行自閉合標籤
 * （`… } />` 換行，全樹 124 處）前一個字元是 `}`，會誤入 regex 然後撞換行，
 * 產生上百筆假 `stripper-desync`。
 *
 * **已知邊界**：`//` 只要不在字串／regex 裡就當行註解，所以 JSX **文字節點**裡的裸網址
 * （`<a>下載 https://x/y.xlsx 檔案</a>`）之後、同一行的中文會被吃掉。**字串裡**的網址
 * 不受影響（§R4-4 有測）。要補這個洞得讓剝離器認得 JSX 文字節點，成本遠高於收益——
 * 先誠實寫在這裡，不要對外宣稱「網址雙斜線都涵蓋」。
 */
export function stripComments(src: string): { code: string; desyncLines: number[] } {
  const out: string[] = []
  const desyncLines: number[] = []
  let state: null | 'line' | 'block' | "'" | '"' | '`' = null
  let line = 1
  let prevTok = ''   // 前一個非空白的**程式碼**字元（regex literal 判定用；空＝檔首）
  for (let i = 0; i < src.length; i++) {
    const c = src[i]
    const nxt = src[i + 1] ?? ''
    if (c === '\n') line++
    if (state === null) {
      if (c === '/' && nxt === '/') { state = 'line'; out.push('  '); i++; continue }
      if (c === '/' && nxt === '*') { state = 'block'; out.push('  '); i++; continue }
      if (c === '/' && REGEX_PREV_RE.test(prevTok)) {
        const eol = src.indexOf('\n', i)
        const m = (eol === -1 ? src.slice(i) : src.slice(i, eol)).match(REGEX_LITERAL_RE)
        // regex 本體原樣留下：裡面若真有中文，那也是碼內中文字面值，本來就該報
        if (m) { out.push(m[0]); i += m[0].length - 1; prevTok = 'r'; continue }
      }
      if (c === "'" || c === '"' || c === '`') { state = c; out.push(c); continue }
      out.push(c)
      if (c.trim()) prevTok = c
      continue
    }
    if (state === 'line') {
      if (c === '\n') { state = null; out.push('\n') } else out.push(' ')
      continue
    }
    if (state === 'block') {
      if (c === '*' && nxt === '/') { state = null; out.push('  '); i++; continue }
      out.push(c === '\n' ? '\n' : ' ')
      continue
    }
    // 字串／樣板內
    if (c === '\\') { out.push(c, nxt); if (nxt === '\n') line++; i++; continue }
    if (c === '\n' && (state === "'" || state === '"')) {
      desyncLines.push(line - 1)   // 換行前的那一行才是出問題的地方
      state = null; out.push('\n'); continue
    }
    if (c === state) { state = null; prevTok = c }   // 引號收尾＝值結束，後面的 `/` 是除號
    out.push(c)
  }
  return { code: out.join(''), desyncLines }
}

const EXEMPT_TOKEN = 'i18n-exempt:'
const EXEMPT_RE = /\/\/\s*i18n-exempt:(.*)$/
const FILE_EXEMPT_TOKEN = 'i18n-exempt-file'
/** `i18n-exempt-file[<漢字預算>]: <理由>`；預算缺漏時仍要比對得到，才報得出「缺預算」。 */
const FILE_EXEMPT_RE = /i18n-exempt-file(?:\[(\d+)\])?:(.*)$/

/**
 * regex literal 的起頭判定：`/` 前面那個非空白字元（空＝檔首）落在這個集合才算 regex。
 *
 * 刻意**不含 `<`**：JSX 收尾標籤 `</h2>` 的 `/` 前面正是 `<`，把它算成 regex 開頭
 * 會讓每一個收尾標籤都去掃描同一行的下一個 `/`。`(` `,` `=` `:` `[` `!` 這些才是
 * 真正會出現 regex 的位置（本樹三個 regex 全部前接 `(` 或 `!`）。
 * 判錯的代價見 `stripComments` 的說明——兩個方向都是安全的。
 */
const REGEX_PREV_RE = /^[(,=:[!&|?{};+\-*/%~^>]?$/
/** regex literal 本體：轉義、字元類別（裡面的 `/` 不用轉義）、其餘非 `/` 字元；**不跨行**。 */
const REGEX_LITERAL_RE = /^\/(?![*/])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n[])+\/[a-z]*/

/**
 * `toLocaleString('zh-TW')` 這類寫死語系的日期格式化。
 *
 * 漢字掃描器對它是全盲的（整行沒有一個中文字），但症狀同源：英文介面下日期仍是
 * 台灣格式。既有的正解在 `dictionary/VersionList.tsx`——`toLocaleString(i18n.language)`。
 * 只要第一個引數是**字面值**就算違規（寫死 `'en-US'` 是同一個病的另一面）。
 */
const HARDCODED_LOCALE_RE = /\btoLocale(?:String|DateString|TimeString)\s*\(\s*['"`]/g

/**
 * 理由必須有實質內容：去掉空白與標點後至少 4 個「字元權重」，否則等於沒寫理由。
 * **漢字一個算兩點**（門檻等效 2 字）——`待補` 這種合法的短中文理由不該被擋，
 * 而拉丁字母的 4 字元門檻對中文太嚴。
 *
 * 這道檢查只擋得住**空理由**：`TODO`／`aaaa` 照樣過關。理由成不成立是人工判斷關卡，
 * 機器擋不住敷衍——不要把它當成比實際更強的保證（見檔頭）。
 */
export function reasonIsSubstantive(reason: string): boolean {
  const s = reason.replace(/[\s\p{P}\p{S}]+/gu, '')
  return s.length + (s.match(/[一-鿿]/g) ?? []).length >= 4
}

interface FileExemption { line: number; reason: string; budget: number | null; inHeader: boolean }

/**
 * 檔級豁免標記。**必須在註解裡**：剝離註解之後標記還在，就代表它躲在字串字面值中
 * （`const s = 'i18n-exempt-file: …'` 一行就能把整個檔案消音），不予採信。
 * 註解與字串裡各有一個的病態情形一樣不採信——fail-closed 的方向是「報出來」。
 *
 * **限檔頭**（第一行程式碼之前）：埋在檔案中段的標記照樣整檔消音，讀者卻在檔頭看不到，
 * 那是文件與實作不符。位置不合格由呼叫端報 `exempt-file-misplaced` 並**不授予豁免**。
 */
function findFileExemption(rawLines: string[], codeLines: string[], code: string): FileExemption | null {
  if (code.includes(FILE_EXEMPT_TOKEN)) return null
  const firstCode = codeLines.findIndex((l) => l.trim() !== '')
  for (let i = 0; i < rawLines.length; i++) {
    const m = rawLines[i].match(FILE_EXEMPT_RE)
    if (!m) continue
    return {
      line: i + 1,
      reason: (m[2] ?? '').trim(),
      budget: m[1] == null ? null : Number(m[1]),
      inHeader: firstCode === -1 || i < firstCode,
    }
  }
  return null
}

/** 剝離註解後的漢字數（檔級豁免的預算單位）。註解裡的中文不計——那本來就允許。 */
function codeHanCount(code: string): number {
  return (code.match(/[一-鿿]/g) ?? []).length
}

/** 逐行的內容違規（尚未套用任何豁免）。 */
function contentViolations(relPath: string, rawLines: string[], codeLines: string[]): Hit[] {
  const out: Hit[] = []
  codeLines.forEach((codeLine, idx) => {
    const line = idx + 1
    const detail = rawLines[idx]?.trim().slice(0, 80) ?? ''
    if (HAN.test(codeLine)) out.push({ file: relPath, line, rule: 'hardcoded-zh', detail })
    HARDCODED_LOCALE_RE.lastIndex = 0
    if (HARDCODED_LOCALE_RE.test(codeLine)) out.push({ file: relPath, line, rule: 'hardcoded-locale', detail })
  })
  return out
}

/**
 * 單檔掃描。回傳的違規類別：
 *  - `hardcoded-zh`           註解以外出現中文，且沒有有效豁免
 *  - `hardcoded-locale`       寫死語系的日期格式化
 *  - `exempt-no-reason`       有 `i18n-exempt:` 但理由空白／只有標點
 *  - `exempt-in-literal`      行級標記躲在字串字面值裡（剝離註解後還看得到），不予採信
 *  - `stale-exemption`        行級豁免指向的那一行沒有中文（當初豁免的東西已經不在了）
 *  - `exempt-file-no-reason`  有 `i18n-exempt-file:` 但理由空白／只有標點
 *  - `exempt-file-no-budget`  檔級標記沒帶漢字預算（`i18n-exempt-file[72]:`）
 *  - `exempt-file-misplaced`  檔級標記不在檔頭（第一行程式碼之後才出現）
 *  - `exempt-file-over-budget` 檔級豁免的檔案漢字變多了（預算只准降不准升）
 *  - `stale-file-exemption`   檔級豁免的檔案已經整份乾淨，標記該刪了
 *  - `redundant-exemption`    檔級豁免生效中卻還留著行級標記（行級標記永遠不會被觀察到過期）
 *  - `stripper-desync`        剝離器在這個檔案脫序（見 stripComments 的說明）
 *
 * 兩種豁免的理由若不合格，一律**不授予豁免**（fail-closed）：那一行／那個檔的中文照樣報出來。
 */
export function scanSource(relPath: string, src: string): Hit[] {
  const { code, desyncLines } = stripComments(src)
  const rawLines = src.split('\n')
  const codeLines = code.split('\n')
  const hits: Hit[] = []

  for (const line of desyncLines) {
    hits.push({ file: relPath, line, rule: 'stripper-desync', detail: rawLines[line - 1]?.trim().slice(0, 80) ?? '' })
  }

  const content = contentViolations(relPath, rawLines, codeLines)

  // ── 檔級豁免 ────────────────────────────────────────────────────────────
  const fileExempt = findFileExemption(rawLines, codeLines, code)
  // 格式不合格 → 一律**不授予豁免**，往下走一般流程把整檔的中文報出來（fail-closed）
  const badFormat: Hit[] = []
  if (fileExempt && !reasonIsSubstantive(fileExempt.reason)) {
    badFormat.push({
      file: relPath, line: fileExempt.line, rule: 'exempt-file-no-reason',
      detail: `i18n-exempt-file: 後面必須寫理由（目前是 ${JSON.stringify(fileExempt.reason)}）`,
    })
  }
  if (fileExempt && fileExempt.budget == null) {
    badFormat.push({
      file: relPath, line: fileExempt.line, rule: 'exempt-file-no-budget',
      detail: `檔級豁免必須帶漢字預算：i18n-exempt-file[${codeHanCount(code)}]: <理由>（只准降不准升）`,
    })
  }
  if (fileExempt && !fileExempt.inHeader) {
    badFormat.push({
      file: relPath, line: fileExempt.line, rule: 'exempt-file-misplaced',
      detail: '檔級豁免必須寫在檔頭註解（第一行程式碼之前），不能埋在檔案中段',
    })
  }
  if (badFormat.length) {
    hits.push(...badFormat)
  } else if (fileExempt) {
    const han = codeHanCount(code)
    if (fileExempt.budget != null && han > fileExempt.budget) {
      hits.push({
        file: relPath, line: fileExempt.line, rule: 'exempt-file-over-budget',
        detail: `本檔漢字預算 ${fileExempt.budget}，目前 ${han}（+${han - fileExempt.budget}）——`
          + '檔級豁免只准降不准升；新增的字請走 i18n，不要往豁免檔裡堆',
      })
    }
    if (content.length === 0) {
      hits.push({
        file: relPath, line: fileExempt.line, rule: 'stale-file-exemption',
        detail: `整檔已無中文字面值，檔級豁免「${fileExempt.reason}」已過期，請刪除標記`,
      })
    }
    rawLines.forEach((raw, idx) => {
      if (!EXEMPT_RE.test(raw)) return
      hits.push({
        file: relPath, line: idx + 1, rule: 'redundant-exemption',
        detail: '本檔已有 i18n-exempt-file:，行級 i18n-exempt: 標記永遠不會被觀察到過期，請刪除',
      })
    })
    return hits
  }

  // ── 行級豁免 ────────────────────────────────────────────────────────────
  // 豁免標記要從**原始碼**找（它本身就是註解，剝掉就看不到了）
  const exemptFor = new Map<number, string>()   // 生效行號 → 理由
  rawLines.forEach((raw, idx) => {
    const m = raw.match(EXEMPT_RE)
    if (!m) return
    const reason = m[1] ?? ''
    const lineNo = idx + 1
    // 檔級同款檢查：剝離註解後這一行還看得到標記＝它躲在字串字面值裡，不予採信。
    // 否則 `const s = '中文 // i18n-exempt: 理由'` 一行字串就能把自己那行消音，
    // 而且因為豁免「有被用掉」連 stale-exemption 都不會報。
    if ((codeLines[idx] ?? '').includes(EXEMPT_TOKEN)) {
      hits.push({
        file: relPath, line: lineNo, rule: 'exempt-in-literal',
        detail: '行級豁免標記必須在註解裡；剝離註解後它還在，代表它躲在字串字面值中，不予採信',
      })
      return
    }
    const beforeMarker = raw.slice(0, m.index ?? 0)
    // 行尾形（該行還有程式碼）作用於本行；獨佔一行的形式作用於下一行。
    const target = beforeMarker.trim() ? lineNo : lineNo + 1
    if (!reasonIsSubstantive(reason)) {
      hits.push({ file: relPath, line: lineNo, rule: 'exempt-no-reason', detail: `i18n-exempt: 後面必須寫理由（目前是 ${JSON.stringify(reason.trim())}）` })
      return
    }
    exemptFor.set(target, reason.trim())
  })

  const used = new Set<number>()
  for (const h of content) {
    if (exemptFor.has(h.line)) { used.add(h.line); continue }
    hits.push(h)
  }

  // 沒被用掉的豁免＝過期
  for (const [lineNo, reason] of exemptFor) {
    if (used.has(lineNo)) continue
    hits.push({ file: relPath, line: lineNo, rule: 'stale-exemption', detail: `這一行沒有中文字面值，豁免理由「${reason}」已過期，請刪除標記` })
  }
  return hits
}

export function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) return sourceFiles(full)
    if (!/\.tsx?$/.test(e.name)) return []
    return EXCLUDED.some((re) => re.test(full)) ? [] : [full]
  })
}

function scanTree(): Hit[] {
  return sourceFiles(SRC_DIR).flatMap((f) =>
    scanSource(path.relative(SRC_DIR, f), fs.readFileSync(f, 'utf-8')),
  )
}

test.describe('§R4 UI 外殼字串外部化守衛', () => {
  test('R4-1: 掃描範圍解析得動（後設守衛：範圍算錯會讓下一條恆真通過）', () => {
    expect(fs.existsSync(SRC_DIR), `${SRC_DIR} 不存在，守衛的掃描根目錄已漂移`).toBe(true)
    const files = sourceFiles(SRC_DIR)
    expect(files.length, '掃不到前端原始碼').toBeGreaterThanOrEqual(50)
    // 排除清單真的排除了、而且**只**排除該排除的
    const rel = files.map((f) => path.relative(SRC_DIR, f))
    expect(rel).not.toContain(path.join('shared', 'i18n', 'resources', 'zh-TW.ts'))
    expect(rel).not.toContain(path.join('shared', 'types', 'api.d.ts'))
    expect(rel).toContain('App.tsx')
  })

  test('R4-2: 前端原始碼不含未豁免的中文字面值／寫死語系', () => {
    const hits = scanTree().filter((h) => h.rule === 'hardcoded-zh' || h.rule === 'hardcoded-locale')
    const report = hits.map((h) => `${h.file}:${h.line}  ${h.detail}`).join('\n')
    expect(hits, `硬編中文字面值（請改走 i18n，或加 // i18n-exempt: <理由>）：\n${report}`).toEqual([])
  })

  test('R4-3: 豁免標記本身健康（理由必填、無過期／冗餘標記、剝離器沒脫序）', () => {
    const HEALTH = [
      'exempt-no-reason', 'exempt-in-literal', 'stale-exemption',
      'exempt-file-no-reason', 'exempt-file-no-budget', 'exempt-file-misplaced',
      'exempt-file-over-budget', 'stale-file-exemption', 'redundant-exemption', 'stripper-desync',
    ]
    const hits = scanTree().filter((h) => HEALTH.includes(h.rule))
    const report = hits.map((h) => `${h.file}:${h.line}  [${h.rule}] ${h.detail}`).join('\n')
    expect(hits, `豁免標記或剝離器有問題：\n${report}`).toEqual([])
  })

  test('R4-4: 剝離器對「看起來像註解但其實是字串」不會誤剝（守衛的地基）', () => {
    // 每一條的中文都在**程式碼**裡，剝離器若把它當註解剝掉 → 守衛靜默失效
    const mustCatch: [string, string][] = [
      ['字串內的行註解記號', `const s = '// 這其實是字串'`],
      ['字串內的區塊註解記號', `const s = '/* 這其實是字串 */'`],
      ['網址中的雙斜線', `const u = 'https://example.com/中文路徑'`],
      ['樣板字面值', 'const s = `合計 ${n} 筆`'],
      ['JSX 文字節點（根本不在引號裡）', `const el = <h2>匯出</h2>`],
      ['屬性值', `const el = <input placeholder="可空" />`],
      ['同一行：程式碼在前、註解在後', `const s = '中文'   // 這一段是註解`],
    ]
    for (const [name, src] of mustCatch) {
      expect(scanSource('t.tsx', src).map((h) => h.rule), `應該抓到：${name}`).toEqual(['hardcoded-zh'])
    }

    // 反向：純註解不得誤報（喊狼的守衛下場是被放寬）
    const mustPass: [string, string][] = [
      ['整行行註解', `// 這是中文註解\nconst s = 'ok'`],
      ['行尾註解', `const s = 'ok'  // 中文說明`],
      ['區塊註解', `/* 中文\n   跨行說明 */\nconst s = 'ok'`],
      ['JSDoc', `/**\n * 中文文件\n */\nexport const s = 'ok'`],
      ['JSX 內的區塊註解', `const el = <div>{/* 中文註解 */}<b>{t('k')}</b></div>`],
    ]
    for (const [name, src] of mustPass) {
      expect(scanSource('t.tsx', src), `不該誤報：${name}`).toEqual([])
    }
  })

  test('R4-4b: regex literal 不會把剝離器帶進區塊註解狀態（跨行靜默吞中文）', () => {
    // (a) 字元類別裡的區塊註解開頭記號。沒有 regex 辨識時剝離器會從這裡誤入 'block'，
    //     一路吃到下一個結尾記號——下面兩行 JSX 中文全部蒸發，而且 'block' 沒有脫序偵測。
    const src = `const re = /[/*]/\nexport const A = () => <h2>產品清單</h2>\n`
      + `export const B = () => <h2>機種清單</h2>\n/* 收尾註解 */\n`
    expect(scanSource('t.tsx', src).map((h) => `${h.line}:${h.rule}`))
      .toEqual(['2:hardcoded-zh', '3:hardcoded-zh'])

    // (b) regex 裡的雙斜線（同一行版本：後半段會被當成行註解吃掉）
    expect(scanSource('t.ts', `const re = /\\/\\//; const s = '中文'`).map((h) => h.rule))
      .toEqual(['hardcoded-zh'])

    // (c) 本樹實際存在的三個 regex 形狀不得誤報，而且**同一行的註解照樣要剝掉**
    const real: string[] = [
      `const a = kw.split(/[,，]/).map(s => s.trim())   // 中文註解`,
      `const b = tech.split(/\\s+/).filter(t => !/^[A-Z]+0$/.test(t))   // 中文註解`,
      `const m = raw.match(/^(\\d{3})\\s+(\\{[\\s\\S]*\\}|\\[[\\s\\S]*\\])$/)   // 中文註解`,
    ]
    for (const one of real) expect(scanSource('t.ts', one), one).toEqual([])

    // (d) 除號不得被誤判成 regex 而把後面的行註解吞成程式碼（那是假警報方向）
    expect(scanSource('t.ts', `const r = a / b   // 中文註解`)).toEqual([])

    // (e) JSX 多行自閉合標籤（`} />` 換行，全樹上百處）不得脫序：
    //     「吃到下一個未轉義 / 為止」的狀態機版本會在這裡撞換行、噴出成堆假 desync
    expect(scanSource('t.tsx', `const el = (\n  <Foo\n    bar={x}\n  />\n)\n// 中文註解`)).toEqual([])
  })

  test('R4-5: 行級豁免可用、且不會退化成消音符', () => {
    const zh = `  reason: '採用單一 draft 至編輯器',`

    // (a) 前一行獨佔式豁免 → 放行
    expect(scanSource('t.ts', `  // i18n-exempt: 送後端的 audit reason，不隨 UI 語言變\n${zh}`)).toEqual([])

    // (b) 行尾式豁免 → 放行
    expect(scanSource('t.ts', `${zh}  // i18n-exempt: 送後端的 audit reason，不隨 UI 語言變`)).toEqual([])

    // (c) 沒寫理由 → 違規（否則它就只是個消音符）
    for (const bad of ['', ' ', '   ——', '  .']) {
      const hits = scanSource('t.ts', `  // i18n-exempt:${bad}\n${zh}`).map((h) => h.rule)
      expect(hits, `空理由必須被擋：${JSON.stringify(bad)}`).toContain('exempt-no-reason')
      expect(hits, '理由無效時不得順便放行那一行中文').toContain('hardcoded-zh')
    }

    // (d) 豁免只作用一行，不會外溢到下一行
    expect(
      scanSource('t.ts', `  // i18n-exempt: 送後端的 audit reason，不隨 UI 語言變\n${zh}\n${zh}`)
        .map((h) => h.rule),
    ).toEqual(['hardcoded-zh'])

    // (e) 過期豁免（指向的那行已經沒有中文了）→ 違規，不讓標記積灰
    expect(
      scanSource('t.ts', `  // i18n-exempt: 送後端的 audit reason，不隨 UI 語言變\n  reason: t('k'),`)
        .map((h) => h.rule),
    ).toEqual(['stale-exemption'])

    // (f) 合法的短中文理由不得被擋（漢字一個算兩點）。純字元數的門檻對中文太嚴——
    //     而它對拉丁字母本來就太鬆（`TODO` 擋不住），別把這道檢查當成比實際更強的保證。
    expect(scanSource('t.ts', `${zh}  // i18n-exempt: 送後端代碼`)).toEqual([])
    expect(scanSource('t.ts', `${zh}  // i18n-exempt: 碼`).map((h) => h.rule)).toContain('exempt-no-reason')

    // (g) 標記躲在字串字面值裡 → 不予採信（對稱於 §R4-5b(c)：一行字串不該能消音那一行）。
    //     舊版只對檔級做了這道檢查，行級直接掃原始碼——下面三種形態當時全部 0 hits，
    //     而且因為豁免「有被用掉」連 stale-exemption 都不報，等於一個乾淨的消音符。
    const sneaky: [string, string][] = [
      ['單引號字串', `const label = '硬編中文標籤 // i18n-exempt: 這是一個看起來很正當的理由'`],
      ['樣板字面值', 'const label = `硬編中文 ${n} 筆 // i18n-exempt: 這是一個看起來很正當的理由`'],
      ['JSX 屬性值', `const el = <input placeholder="請輸入名稱 // i18n-exempt: 這是一個很正當的理由" />`],
    ]
    for (const [name, one] of sneaky) {
      expect(scanSource('t.tsx', one).map((h) => h.rule), `不得採信：${name}`)
        .toEqual(['exempt-in-literal', 'hardcoded-zh'])
    }
  })

  test('R4-5b: 檔級豁免可用、且不會退化成消音符', () => {
    const body = `export const A = () => <h2>產品</h2>\nexport const B = () => <h2>機種</h2>\n`   // 漢字 4
    const ok = `/** i18n-exempt-file[4]: 零引用且待重寫的版面，接回 IA 時整份重寫 */\n`

    // (a) 檔頭註解的標記 → 整檔放行
    expect(scanSource('t.tsx', ok + body)).toEqual([])
    // 行註解形式一樣算
    expect(scanSource('t.tsx', `// i18n-exempt-file[4]: 零引用且待重寫的版面，接回 IA 時整份重寫\n` + body)).toEqual([])

    // (b) 沒寫理由 → 違規，而且**不授予豁免**（整檔的中文照樣報出來）
    for (const bad of ['', ' ', ' ——']) {
      const hits = scanSource('t.tsx', `/** i18n-exempt-file[4]:${bad} */\n` + body).map((h) => h.rule)
      expect(hits, `空理由必須被擋：${JSON.stringify(bad)}`).toContain('exempt-file-no-reason')
      expect(hits.filter((r) => r === 'hardcoded-zh'), '理由無效時不得順便放行整檔').toHaveLength(2)
    }

    // (c) 標記躲在字串字面值裡 → 不予採信（一行字串不該能把整個檔案消音）
    const sneaky = `const s = 'i18n-exempt-file[4]: 我把整個檔案消音'\n` + body
    expect(scanSource('t.tsx', sneaky).map((h) => h.rule)).toEqual(['hardcoded-zh', 'hardcoded-zh', 'hardcoded-zh'])

    // (d) 整檔已無中文 → 檔級豁免過期
    expect(scanSource('t.tsx', ok + `export const A = () => <h2>{t('k')}</h2>\n`).map((h) => h.rule))
      .toEqual(['stale-file-exemption'])

    // (e) 檔級與行級並存 → 行級標記永遠不會被觀察到過期，必須拆掉
    expect(scanSource('t.tsx', ok + `  // i18n-exempt: 送後端的 audit reason，不隨 UI 語言變\n` + body)
      .map((h) => h.rule)).toEqual(['redundant-exemption'])

    // (f) 漢字預算：只准降不准升。豁免生效期間**新增**的中文原本是永久盲區
    //     （`stale-file-exemption` 只在「整份乾淨了」才報，對「越長越多」全盲，
    //     零引用的檔案沒人會看，最適合當垃圾堆）。
    const grown = ok + body + `export const C = () => <h2>版本</h2>\n`
    expect(scanSource('t.tsx', grown).map((h) => h.rule)).toEqual(['exempt-file-over-budget'])
    // 變少不擋（重寫途中本來就會一路降）
    expect(scanSource('t.tsx', `/** i18n-exempt-file[9]: 零引用且待重寫的版面，接回 IA 時整份重寫 */\n` + body))
      .toEqual([])

    // (g) 沒帶預算 → 違規且不授予豁免（舊格式標記不會靜默失效，會直接說要補什麼）
    const noBudget = scanSource('t.tsx', `/** i18n-exempt-file: 零引用且待重寫的版面，接回 IA 時整份重寫 */\n` + body)
    expect(noBudget.map((h) => h.rule)).toContain('exempt-file-no-budget')
    expect(noBudget.filter((h) => h.rule === 'hardcoded-zh'), '缺預算時不得順便放行整檔').toHaveLength(2)

    // (h) 標記必須在檔頭（第一行程式碼之前）。埋在檔案中段照樣整檔消音、讀者卻在
    //     檔頭看不到——文件寫「限檔頭註解」，實作就要真的限制（否則兩邊不一致）。
    const buried = scanSource('t.tsx', body + `// i18n-exempt-file[4]: 零引用且待重寫的版面，接回 IA 時整份重寫\n`)
    expect(buried.map((h) => h.rule)).toContain('exempt-file-misplaced')
    expect(buried.filter((h) => h.rule === 'hardcoded-zh'), '位置不合格時不得順便放行整檔').toHaveLength(2)
  })

  test('R4-6: 寫死語系的日期格式化也擋（漢字掃描器對它全盲）', () => {
    expect(scanSource('t.tsx', `const f = (iso: string) => new Date(iso).toLocaleDateString('zh-TW')`)
      .map((h) => h.rule)).toEqual(['hardcoded-locale'])
    expect(scanSource('t.tsx', `const f = (iso: string) => new Date(iso).toLocaleString("en-US")`)
      .map((h) => h.rule), '寫死 en-US 是同一個病的另一面').toEqual(['hardcoded-locale'])
    // 正解不得誤判
    expect(scanSource('t.tsx', `const f = (iso: string) => new Date(iso).toLocaleString(i18n.language)`))
      .toEqual([])
    // 註解裡提到不算
    expect(scanSource('t.tsx', `// 不要寫 toLocaleString('zh-TW')\nconst f = () => 1`)).toEqual([])
  })

  test('R4-7: 合成違規檔放進真實掃描流程會紅（證明 R4-2 不是恆真的空清單）', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'r4-guard-'))
    try {
      const f = path.join(dir, 'Sneaky.tsx')
      fs.writeFileSync(f, `export const C = () => <button title="關閉">送出</button>\n`)
      const hits = sourceFiles(dir).flatMap((x) => scanSource(path.basename(x), fs.readFileSync(x, 'utf-8')))
      expect(hits.map((h) => h.rule)).toEqual(['hardcoded-zh'])   // 逐行計數：同一行兩處中文算一筆（修的時候也是修一行）

      // 排除清單不得因為「檔名剛好叫 zh-TW.ts」就整批消音——比對的是路徑而不是檔名
      const decoy = path.join(dir, 'zh-TW.ts')
      fs.writeFileSync(decoy, `export const s = '中文'\n`)
      expect(sourceFiles(dir).map((x) => path.basename(x)).sort()).toEqual(['Sneaky.tsx', 'zh-TW.ts'])
    } finally {
      fs.rmSync(dir, { recursive: true, force: true })
    }
  })
})
