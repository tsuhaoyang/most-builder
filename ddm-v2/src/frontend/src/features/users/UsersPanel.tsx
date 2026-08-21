import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useUsers, useUpsertUser, usePatchUser } from './api'
import { useMe, isAdmin } from '../../shared/auth/useMe'

const ROLES = ['analyst', 'approver', 'admin'] as const

export function UsersPanel() {
  const { t } = useTranslation()
  // 角色代碼本身（analyst/approver/admin）是後端的穩定鍵，兩語都原樣顯示；
  // 只有「沒有任何角色」這個空集合需要一個可翻譯的說法。
  const roleLabel = (rs: string[]) => rs.length ? rs.join(' · ') : t('users.viewerRole')
  const { data: me } = useMe()
  const qc = useQueryClient()
  const { data: users = [], isLoading, error } = useUsers()
  const upsert = useUpsertUser()
  const patch = usePatchUser()
  const [emp, setEmp] = useState(''); const [name, setName] = useState(''); const [newRoles, setNewRoles] = useState<string[]>(['analyst'])
  const [msg, setMsg] = useState('')

  const admin = isAdmin(me)
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin-users'] })
  const fail = (e: unknown) => setMsg(t('users.failed', { message: (e as Error).message }))
  const toggle = (arr: string[], r: string) => arr.includes(r) ? arr.filter(x => x !== r) : [...arr, r]

  if (!admin) return <div className="bg-white rounded-xl border p-6 text-amber-600">{t('users.adminOnly', { employee: me?.employee_no, roles: roleLabel(me?.roles ?? []) })}</div>
  if (isLoading) return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('users.loading')}</div>
  if (error) return <div className="bg-white rounded-xl border p-6 text-red-600">{t('users.loadFailed', { message: (error as Error).message })}</div>

  const setRoles = (employee_no: string, roles: string[]) =>
    patch.mutate({ employee_no, body: { roles } }, { onSuccess: () => { setMsg(''); refresh() }, onError: fail })
  const setActive = (employee_no: string, is_active: boolean) =>
    patch.mutate({ employee_no, body: { is_active } }, { onSuccess: () => { setMsg(''); refresh() }, onError: fail })
  const addUser = () => {
    if (!emp.trim()) return
    upsert.mutate({ employee_no: emp.trim(), display_name: name.trim() || undefined, roles: newRoles },
      { onSuccess: () => { setEmp(''); setName(''); setNewRoles(['analyst']); setMsg(t('users.saved')); refresh() }, onError: fail })
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4">
        <h2 className="font-semibold mb-1">{t('users.heading')}</h2>
        <p className="text-xs text-slate-500">{t('users.description')}</p>
      </div>

      <div className="bg-white rounded-xl border p-4">
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left">
            <th className="p-1">{t('users.colEmployeeNo')}</th><th className="p-1">{t('users.colName')}</th><th className="p-1">{t('users.colRoles')}</th>
            {ROLES.map(r => <th key={r} className="p-1 text-center">{r}</th>)}<th className="p-1">{t('users.colActive')}</th>
          </tr></thead>
          <tbody>
            {users.map(u => {
              const self = u.employee_no === me?.employee_no
              return (
                <tr key={u.employee_no} className={`border-t ${u.is_active ? '' : 'opacity-50'}`}>
                  <td className="p-1 font-medium">{u.employee_no}{self && <span className="ml-1 text-xs text-sky-600">{t('users.self')}</span>}</td>
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
                      {u.is_active ? t('users.active') : t('users.inactive')}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="bg-white rounded-xl border p-4">
        <h3 className="font-semibold text-sm mb-2">{t('users.formHeading')}</h3>
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label>{t('users.employeeNo')} <input className="border rounded px-2 py-1" value={emp} onChange={e => setEmp(e.target.value)} placeholder="IECxxxxxx" /></label>
          <label>{t('users.name')} <input className="border rounded px-2 py-1" value={name} onChange={e => setName(e.target.value)} /></label>
          <span className="flex items-center gap-2">{t('users.roles')} {ROLES.map(r => (
            <label key={r} className="text-xs"><input type="checkbox" checked={newRoles.includes(r)} onChange={() => setNewRoles(toggle(newRoles, r))} /> {r}</label>
          ))}</span>
          <button disabled={!emp.trim() || upsert.isPending} onClick={addUser} className="px-3 py-1.5 bg-blue-600 text-white rounded disabled:opacity-40">{t('users.save')}</button>
          <span className="text-xs text-slate-500">{msg}</span>
        </div>
      </div>
    </div>
  )
}
