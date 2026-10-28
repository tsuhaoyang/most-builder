// BL-ENG-12：隔離瀏覽器掛載真實 WritebackPanel，驗證「不屬於工序表的 LB 結果」呈現。
// 不啟動 Vite／後端、不載入 playwright.config.ts 或 e2e/global-setup.ts、不寫 DB；網路全攔截。
// 用法（於 ddm-v2/src/frontend 執行）：
//   node isolated-tests/writeback-external.mjs --capture <baseline.json>   取回歸基線（對現況元件）
//   node isolated-tests/writeback-external.mjs --regress <baseline.json>   比對回歸（DOM 與基線逐字相等）
//   node isolated-tests/writeback-external.mjs --new                       斷言新行為（未實作時必失敗＝對照組）
import { build } from 'esbuild'
import { chromium } from 'playwright-core'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const [mode, file] = process.argv.slice(2)
if (!['--capture', '--regress', '--new'].includes(mode) || (mode !== '--new' && !file)) {
  console.error('usage: writeback-external.mjs --capture|--regress <baseline.json> | --new')
  process.exit(2)
}

const stubs = {
  '@tanstack/react-query': 'export const useQueryClient=()=>({invalidateQueries:async()=>{}})',
  '../../shared/api/client': 'export class ApiError extends Error {}',
  '../wi-workbench/store': 'export const useWiStore=(select)=>select({rows:window.fixture.rows})',
  '../wi-workbench/useRowNarr': 'export const useRowNarr=()=>r=>r.name',
  './api': 'export const useLbWriteback=()=>({data:window.fixture.data,isLoading:false,isError:false}); export const useFetchWriteback=()=>({isPending:false,mutateAsync:async()=>{throw Error("fetch forbidden")}}); export const useApplyOffline=()=>({isPending:false,mutateAsync:async(req)=>{window.applyCalls.push(req);return {applied:req.wi_row_ids,propagated:[]}}});',
}

const bundle = await build({
  stdin: { contents: `
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {flushSync} from 'react-dom';
    import i18next from 'i18next';
    import {initReactI18next} from 'react-i18next';
    import zh from '${root}/src/shared/i18n/resources/zh-TW.ts';
    import en from '${root}/src/shared/i18n/resources/en.ts';
    import {WritebackPanel} from '${root}/src/features/level-system/WritebackPanel.tsx';
    await i18next.use(initReactI18next).init({lng:'zh-TW',fallbackLng:false,resources:{'zh-TW':{translation:zh},en:{translation:en}},interpolation:{escapeValue:false}});
    const rootEl=createRoot(document.getElementById('root'));
    let n=0;
    window.renderFixture=async(locale)=>{await i18next.changeLanguage(locale);flushSync(()=>rootEl.render(<WritebackPanel key={++n} worksheetId="isolated" editable={window.fixture.editable}/>));};
  `, resolveDir: root, loader: 'tsx' },
  bundle: true, write: false, format: 'esm', jsx: 'automatic',
  nodePaths: [root + '/node_modules'],
  plugins: [{ name: 'bounded-component-stubs', setup(b) {
    b.onResolve({ filter: /.*/ }, args => {
      if (args.importer.endsWith('/WritebackPanel.tsx') && Object.hasOwn(stubs, args.path)) return { path: args.path, namespace: 'stub' }
    })
    b.onLoad({ filter: /.*/, namespace: 'stub' }, args => ({ contents: stubs[args.path], loader: 'js' }))
  } }],
})

const EXT = n => `00000000-0000-4000-8000-00000000000${n}`
const motion = (extra = {}) => ({ task_ids: [1], stations: [0], workers: ['w'], units_total: null, units_source: null, offline: false, cross_station: false, offline_conflict: false, ...extra })
const base = (diff, extra = {}) => ({
  snapshot_id: 'snapshot-isolated', fetched_at: '2026-10-28T00:00:00Z', applied_at: null,
  summary: { project_id: 'p', version_id: 'v', result_id: 'r', units_baseline: { status: 'ok', reasons: [] } },
  diff: { matched: [], unmatched: [], motions: {}, missing: [], offline_diffs: [], ...diff }, ...extra,
})

// 既有行為的回歸情境（皆無 unmatched）
const regressRows = [{ id: 'A', name: 'step A' }, { id: 'B', name: 'step B' }, { id: 'C', name: 'step C' }]
const regressData = base({
  matched: ['A', 'B'],
  motions: {
    A: motion({ units_total: 5, units_source: 'cyclic', cross_station: true, stations: [0, 1], units_degraded: [
      { task_id: 11, units_sum: 4, quantity: 5, reason: 'conservation' }, { task_id: 12, units_sum: 2, quantity: 1, reason: 'setup_not_one' },
      { task_id: 13, units_sum: null, quantity: null, reason: 'unknown' }] }),
    B: motion({ units_total: 3, units_source: 'inferred_max', offline_conflict: true, stations: [2] }),
  },
  missing: [{ wi_row_id: 'C', reason: 'no_result', lb_dropped_possible: true }],
  offline_diffs: [{ wi_row_id: 'A', most_offline: false, lb_offline: true }],
  export_warnings: { present: true, units_degraded: [], truncated: true, limit: 2, unattached_units_degraded: 3,
    dropped_rows: [{ task_id: 21, reason: 'source_wi_row_id_not_uuid' }, { task_id: 22, reason: 'unknown' }] },
}, { applied_at: '2026-10-28T01:00:00Z', applied_report_status: 'unavailable' })
regressData.summary.units_baseline = { status: 'unavailable', reasons: ['E1'] }

const scenarios = {
  regressFull: { editable: true, rows: regressRows, data: regressData },
  onlyNormal: { editable: false, rows: regressRows, data: base({ matched: ['A'], motions: { A: motion() } }) },
  noResults: { editable: false, rows: regressRows, data: base({}) },
  mixed: { editable: false, rows: regressRows, data: base({ matched: ['A'], unmatched: [EXT(1), EXT(2)], motions: { A: motion(), [EXT(1)]: motion(), [EXT(2)]: motion() } }) },
  allExternal: { editable: false, rows: regressRows, data: base({ unmatched: [EXT(1), EXT(2)], motions: { [EXT(1)]: motion(), [EXT(2)]: motion() } }) },
  orphanUnmatched: { editable: false, rows: regressRows, data: base({ matched: ['A'], unmatched: [EXT(9)], motions: { A: motion() } }) },
  externalWithDegraded: { editable: false, rows: regressRows, data: base({ matched: ['A'], unmatched: [EXT(1)], motions: { A: motion(), [EXT(1)]: motion() },
    export_warnings: { present: true, units_degraded: [], dropped_rows: [], truncated: false, limit: 10, unattached_units_degraded: 2 } }) },
}

const browser = await chromium.launch({ headless: true })
const failures = []
const check = (ok, msg) => { if (!ok) failures.push(msg) }
try {
  const context = await browser.newContext({ serviceWorkers: 'block' })
  const requests = [], errors = []
  await context.route('**/*', route => { requests.push(route.request().url()); return route.abort() })
  const page = await context.newPage()
  page.on('pageerror', e => errors.push(String(e)))
  await page.setContent('<meta http-equiv="Content-Security-Policy" content="connect-src \'none\'; img-src \'none\'"><div id="root"></div>')
  await page.evaluate(() => { window.applyCalls = [] })
  await page.addScriptTag({ type: 'module', content: bundle.outputFiles[0].text })
  await page.waitForFunction(() => typeof window.renderFixture === 'function')

  const show = async (name, locale) => {
    await page.evaluate(([s, l]) => { window.fixture = s; return window.renderFixture(l) }, [scenarios[name], locale])
    await page.getByTestId('writeback-panel').waitFor()
  }
  const html = () => page.getByTestId('writeback-panel').evaluate(el => el.outerHTML)
  const has = id => page.getByTestId(id).count().then(c => c > 0)
  const text = id => page.getByTestId(id).first().innerText()

  const snap = {}
  for (const locale of ['zh-TW', 'en']) {
    for (const name of ['regressFull', 'onlyNormal', 'noResults']) { await show(name, locale); snap[`${name}/${locale}`] = await html() }
    // 離線差異勾選→套用
    await show('regressFull', locale)
    await page.evaluate(() => { window.applyCalls = [] })
    const apply = page.getByTestId('writeback-apply-offline')
    const before = await apply.isDisabled()
    await page.getByTestId('writeback-offline-A').check()
    await apply.click()
    await page.getByTestId('writeback-apply-msg').waitFor()
    snap[`apply/${locale}`] = JSON.stringify({
      initiallyDisabled: before, calls: await page.evaluate(() => window.applyCalls), msg: await text('writeback-apply-msg'),
      checkedAfter: await page.getByTestId('writeback-offline-A').isChecked(), disabledAfter: await apply.isDisabled(),
    })
  }

  if (mode === '--capture') {
    writeFileSync(file, JSON.stringify(snap, null, 1) + '\n')
    console.log(`captured ${Object.keys(snap).length} baseline entries -> ${file}`)
  } else if (mode === '--regress') {
    const base0 = JSON.parse(readFileSync(file, 'utf8'))
    for (const k of Object.keys(base0)) check(snap[k] === base0[k], `regression: ${k} differs from baseline`)
    check(Object.keys(snap).length === Object.keys(base0).length, 'regression: entry set differs')
    for (const k of Object.keys(snap)) if (k.startsWith('onlyNormal') || k.startsWith('noResults')) check(!snap[k].includes('writeback-external'), `${k}: external block must not appear`)
    for (const locale of ['zh-TW', 'en']) {
      await show('externalWithDegraded', locale)
      check(await has('writeback-lb-degraded-unattached'), `${locale}: unattached_units_degraded notice lost`)
    }
  } else {
    for (const locale of ['zh-TW', 'en']) {
      const cjk = /[\u4e00-\u9fff]/
      for (const name of ['mixed', 'allExternal']) {
        await show(name, locale)
        const n = name === 'mixed' ? 1 : 0
        const ext = await has('writeback-external') ? await text('writeback-external') : ''
        check(ext !== '', `${locale}/${name}: external block missing`)
        check(ext.includes('2'), `${locale}/${name}: external block lacks count 2`)
        check(!ext.includes('0000000'), `${locale}/${name}: external block shows id fragment`)
        check(!/第 \d+ 步|Step \d+/.test(ext), `${locale}/${name}: external rows look like process steps`)
        check(ext.includes(locale === 'en' ? 'LB result 1' : 'LB 結果 1') && ext.includes(locale === 'en' ? 'LB result 2' : 'LB 結果 2'), `${locale}/${name}: external rows lack neutral labels`)
        check(locale === 'en' ? !cjk.test(ext) : cjk.test(ext), `${locale}/${name}: wrong language in external block`)
        check(!(await page.getByTestId('writeback-panel').innerText()).includes('levelSystem.jobs.writeback.'), `${locale}/${name}: raw i18n key leaked`)
        const placements = await text('writeback-placements')
        check(!placements.includes('0000000'), `${locale}/${name}: external ids still in normal list`)
        check(await page.getByTestId('writeback-placements').locator('[data-testid^="writeback-motion-"]').count() === n, `${locale}/${name}: normal row count != ${n}`)
        if (n) check(/第 1 步|Step 1/.test(placements), `${locale}/${name}: normal step label lost`)
      }
      await show('externalWithDegraded', locale)
      check(await has('writeback-lb-degraded-unattached'), `${locale}: unattached_units_degraded notice lost`)
      check((await has('writeback-external')) && (await text('writeback-external')).includes('1'), `${locale}: single external count`)
      for (const name of ['onlyNormal', 'noResults']) { await show(name, locale); check(!(await has('writeback-external')), `${locale}/${name}: external block must not appear`) }
      // unmatched 有 id 但 motions 無對應列：不出現空區
      await show('orphanUnmatched', locale)
      check(!(await has('writeback-external')), `${locale}/orphanUnmatched: empty external block must not appear`)
      // 精確文案（兩語系各自的區頭與單數形、外來列標示）
      const exact = { 'zh-TW': ['以下 2 項來自 LB，不屬於這份工序表', '以下 1 項來自 LB，不屬於這份工序表'], en: ['2 results from LB do not belong to this process sheet', '1 result from LB does not belong to this process sheet'] }[locale]
      await show('mixed', locale)
      check((await text('writeback-external')).includes(exact[0]), `${locale}: exact plural title mismatch`)
      await show('externalWithDegraded', locale)
      check((await text('writeback-external')).includes(exact[1]), `${locale}: exact singular title mismatch`)
      const other = locale === 'en' ? '以下' : 'results from LB'
      check(!(await text('writeback-external')).includes(other), `${locale}: other-locale text leaked`)
    }
  }
  check(requests.length === 0, `network requests: ${JSON.stringify(requests)}`)
  check(errors.length === 0, `pageerrors: ${JSON.stringify(errors)}`)
} finally {
  await browser.close()
}
if (failures.length) { console.error(`FAIL (${failures.length}):\n- ` + failures.join('\n- ')); process.exit(1) }
console.log(`PASS ${mode}: 0 network requests, 0 pageerrors`)
