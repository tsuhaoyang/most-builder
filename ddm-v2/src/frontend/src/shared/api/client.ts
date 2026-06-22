// 唯一 API 入口：注入 dev 身分 header、統一錯誤。後端權威（前端不自算）。
const DEV_USER = (import.meta as any).env?.VITE_DEV_USER ?? 'IEC141289'

function buildHeaders(json = true): Record<string, string> {
  const h: Record<string, string> = { 'X-Username': DEV_USER }
  if (json) h['Content-Type'] = 'application/json'
  return h
}

async function toError(r: Response): Promise<Error> {
  let d: any = null
  try { d = await r.json() } catch { /* ignore */ }
  const detail = d?.detail ? (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail)) : r.statusText
  return new Error(`${r.status} ${detail}`)
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: buildHeaders(false) })
  if (!r.ok) throw await toError(r)
  return r.json() as Promise<T>
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: buildHeaders(), body: body ? JSON.stringify(body) : undefined })
  if (!r.ok) throw await toError(r)
  return r.json() as Promise<T>
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: 'PUT', headers: buildHeaders(), body: body ? JSON.stringify(body) : undefined })
  if (!r.ok) throw await toError(r)
  return r.json() as Promise<T>
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: 'PATCH', headers: buildHeaders(), body: body ? JSON.stringify(body) : undefined })
  if (!r.ok) throw await toError(r)
  return r.json() as Promise<T>
}

// 檔案上傳：用 FormData，不可設 Content-Type（瀏覽器自帶 boundary）
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'X-Username': DEV_USER }, body: form })
  if (!r.ok) throw await toError(r)
  return r.json() as Promise<T>
}

export async function apiDelete(path: string): Promise<void> {
  const r = await fetch(path, { method: 'DELETE', headers: buildHeaders(false) })
  if (!r.ok) throw await toError(r)
}
