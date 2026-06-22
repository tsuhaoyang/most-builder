import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useUsers, useUpsertUser, usePatchUser } from './api'
import { useMe, isAdmin } from '../../shared/auth/useMe'

const ROLES = ['IE', 'manager', 'admin'] as const
const roleLabel = (rs: string[]) => rs.length ? rs.join(' · ') : 'viewer（唯讀）'

export function UsersPanel() {
  const { data: me } = useMe()
  const qc = useQueryClient()
  const { data: users = [], isLoading, error } = useUsers()
  const upsert = useUpsertUser()
  const patch = usePatchUser()
  const [emp, setEmp] = useState(''); const [name, setName] = useState(''); const [newRoles, setNewRoles] = useState<string[]>(['IE'])
  const [msg, setMsg] = useState('')

  const admin = isAdmin(me)
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin-users'] })
  const fail = (e: unknown) => setMsg('⚠️ ' + (e as Error).message)
  const toggle = (arr: string[], r: string) => arr.includes(r) ? arr.filter(x => x !== r) : [...arr, r]

  if (!admin) return <div className="bg-white rounded-xl border p-6 text-amber-600">使用者管理僅限 admin。目前身分：{me?.employee_no}（{roleLabel(me?.roles ?? [])}）。</div>
  if (isLoading) return <div className="bg-white rounded-xl border p-6 text-slate-500">載入使用者…</div>
  if (error) return <div className="bg-white rounded-xl border p-6 text-red-600">載入失敗：{(error as Error).message}</div>

  const setRoles = (employee_no: string, roles: string[]) =>
    patch.mutate({ employee_no, body: { roles } }, { onSuccess: () => { setMsg(''); refresh() }, onError: fail })
  const setActive = (employee_no: string, is_active: boolean) =>
    patch.mutate({ employee_no, body: { is_active } }, { onSuccess: () => { setMsg(''); refresh() }, onError: fail })
  const addUser = () => {
    if (!emp.trim()) return
    upsert.mutate({ employee_no: emp.trim(), display_name: name.trim() || undefined, roles: newRoles },
      { onSuccess: () => { setEmp(''); setName(''); setNewRoles(['IE']); setMsg('✓ 已新增/更新'); refresh() }, onError: fail })
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold mb-1">使用者與角色</h2>
        <p className="text-xs text-slate-500">角色階層 viewer &lt; IE &lt; manager &lt; admin（admin 限定管理）。穩定鍵＝員工編號；身分由閘道帶入。無勾選＝viewer（唯讀）。</p>
      </div>

      <div className="bg-white rounded-xl border p-4">
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left">
            <th className="p-1">員工編號</th><th className="p-1">名稱</th><th className="p-1">角色</th>
            {ROLES.map(r => <th key={r} className="p-1 text-center">{r}</th>)}<th className="p-1">啟用</th>
          </tr></thead>
          <tbody>
            {users.map(u => {
              const self = u.employee_no === me?.employee_no
              return (
                <tr key={u.employee_no} className={`border-t ${u.is_active ? '' : 'opacity-50'}`}>
                  <td className="p-1 font-medium">{u.employee_no}{self && <span className="ml-1 text-xs text-sky-600">（你）</span>}</td>
                  <td className="p-1">{u.display_name}</td>
                  <td className="p-1 text-slate-500">{roleLabel(u.roles)}</td>
                  {ROLES.map(r => (
                    <td key={r} className="p-1 text-center">
                      <input type="checkbox" checked={u.roles.includes(r)} disabled={patch.isPending}
                        onChange={() => setRoles(u.employee_no, toggle(u.roles, r))} />
                    </td>
                  ))}
                  <td className="p-1">
                    <button className={`px-2 py-0.5 rounded text-xs ${u.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200'}`}
                      disabled={patch.isPending} onClick={() => setActive(u.employee_no, !u.is_active)}>
                      {u.is_active ? '啟用中' : '已停用'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-xl border p-4">
        <h3 className="font-semibold text-sm mb-2">新增 / 設定使用者</h3>
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label>員工編號 <input className="border rounded px-2 py-1" value={emp} onChange={e => setEmp(e.target.value)} placeholder="IECxxxxxx" /></label>
          <label>名稱 <input className="border rounded px-2 py-1" value={name} onChange={e => setName(e.target.value)} /></label>
          <span className="flex items-center gap-2">角色 {ROLES.map(r => (
            <label key={r} className="text-xs"><input type="checkbox" checked={newRoles.includes(r)} onChange={() => setNewRoles(toggle(newRoles, r))} /> {r}</label>
          ))}</span>
          <button disabled={!emp.trim() || upsert.isPending} onClick={addUser} className="px-3 py-1.5 bg-blue-600 text-white rounded disabled:opacity-40">儲存</button>
          <span className="text-xs text-slate-500">{msg}</span>
        </div>
      </div>
    </div>
  )
}
