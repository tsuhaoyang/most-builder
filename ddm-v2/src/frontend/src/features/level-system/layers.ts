// 排（層）解析與正規化（ADR-035 D10 F2；實作書附錄 A）。純函式，無副作用。
import type { Job } from './jobsModel'

export interface Parsed { lo: number; hi: number; discrete: string | null }

/** 'k'→{lo:k,hi:k}；'a~b'→{lo:a,hi:b}；'a/b'（離散跳號）→ {discrete:'a/b'}。 */
export function parseLevel(level: string | null | undefined): Parsed {
  const s = (level ?? '').trim()
  if (!s) return { lo: 1, hi: 1, discrete: null }
  if (s.includes('/')) return { lo: NaN, hi: NaN, discrete: s }
  if (s.includes('~')) {
    const [a, b] = s.split('~', 2)
    const lo = parseInt(a, 10)
    const hi = parseInt(b, 10)
    return { lo, hi: Number.isNaN(hi) ? lo : hi, discrete: null }
  }
  const n = parseInt(s, 10)
  return { lo: n, hi: n, discrete: null }
}

/** (lo,hi)→ level 字串：hi>lo → 'lo~hi'；否則 'lo'。 */
export function fmtLevel(lo: number, hi?: number | null): string {
  return hi != null && hi > lo ? `${lo}~${hi}` : `${lo}`
}

/**
 * 把 jobs 的 row（含小數：ownRow/placeBetween 用 x.5 表達「插在中間」）重新編號成 1..k 連續整數。
 * discrete 作業不參與排編號（row 為 NaN）。回傳 row→顯示排號 的對映（就地不改 jobs，呼叫端 patch）。
 */
export function normalizeLayers(jobs: Job[]): Map<number, number> {
  const rows = [...new Set(jobs.filter(j => !j.discrete).map(j => j.row))].sort((a, b) => a - b)
  const m = new Map<number, number>()
  rows.forEach((r, i) => m.set(r, i + 1))
  return m
}
