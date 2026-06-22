import { useState } from 'react'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useVocabList, useCreateVocab, useDeleteVocab, type VocabKind } from './api'

const KINDS: { v: VocabKind; l: string }[] = [
  { v: 'object', l: '物件' }, { v: 'component', l: '元件' }, { v: 'tool', l: '器具' },
  { v: 'from', l: '從(來源)' }, { v: 'to', l: '到(目的)' }, { v: 'hand', l: '手勢' },
]

export function MasterData() {
  const { data: me } = useMe()
  const { data: items = [], isLoading } = useVocabList()
  const create = useCreateVocab()
  const del = useDeleteVocab()
  const editable = canEdit(me)

  const [kind, setKind] = useState<VocabKind>('object')
  const [zh, setZh] = useState(''); const [en, setEn] = useState(''); const [code, setCode] = useState('')
  const [msg, setMsg] = useState('')

  function add() {
    if (!zh.trim()) { setMsg('請填中文名'); return }
    create.mutate({ kind, name_zh: zh.trim(), name_en: en.trim() || null, external_code: code.trim() || null }, {
      onSuccess: () => { setZh(''); setEn(''); setCode(''); setMsg('✓ 已新增') },
      onError: e => setMsg('新增失敗：' + (e as Error).message),
    })
  }

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <h2 className="font-semibold">主數據 / 詞彙庫</h2>
      <p className="text-xs text-slate-500">這裡新增/刪除的詞彙，會即時反映到 ① WI、② Level 的下拉（共用快取）。</p>

      {editable &&
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label>類別 <select className="border rounded px-1 py-0.5" value={kind} onChange={e => setKind(e.target.value as VocabKind)}>
            {KINDS.map(k => <option key={k.v} value={k.v}>{k.l}</option>)}</select></label>
          <label>中文名 <input className="border rounded px-1 py-0.5" value={zh} onChange={e => setZh(e.target.value)} /></label>
          <label>英文名 <input className="border rounded px-1 py-0.5 w-28" value={en} onChange={e => setEn(e.target.value)} /></label>
          <label>external_code <input className="border rounded px-1 py-0.5 w-24" value={code} onChange={e => setCode(e.target.value)} /></label>
          <button className="px-2 py-1 bg-blue-600 text-white rounded disabled:opacity-40" disabled={create.isPending} onClick={add}>＋新增</button>
          <span className="text-xs text-slate-400">{msg}</span>
        </div>}

      <table className="w-full text-sm">
        <thead><tr className="bg-slate-100 text-left"><th className="p-1">類別</th><th className="p-1">中文</th><th className="p-1">英文</th><th className="p-1">external_code</th><th className="p-1">來源</th><th className="p-1"></th></tr></thead>
        <tbody>
          {isLoading && <tr><td colSpan={6} className="p-3 text-slate-400">載入中…</td></tr>}
          {items.map(v => (
            <tr key={v.id} className="border-t">
              <td className="p-1">{KINDS.find(k => k.v === v.kind)?.l ?? v.kind}</td>
              <td className="p-1">{v.name_zh}</td><td className="p-1">{v.name_en || ''}</td>
              <td className="p-1 font-mono text-xs">{v.external_code || ''}</td><td className="p-1">{v.source_system}</td>
              <td className="p-1">{editable && <button className="text-red-600 underline" disabled={del.isPending} onClick={() => del.mutate(v.id)}>刪</button>}</td>
            </tr>
          ))}
          {!isLoading && items.length === 0 && <tr><td colSpan={6} className="p-3 text-slate-400">尚無詞彙</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
