// 唯一 API 入口：注入 dev 身分 header、統一錯誤。後端權威（前端不自算）。
const DEV_USER = (import.meta as any).env?.VITE_DEV_USER ?? 'IEC141289'

function buildHeaders(json = true): Record<string, string> {
  const h: Record<string, string> = { 'X-Username': DEV_USER }
  if (json) h['Content-Type'] = 'application/json'
  return h
}

/**
 * 後端錯誤。`detail` 保留原始結構供呼叫端判別錯誤碼
 * （如 ADR-023 的 CERTIFIED_IMMUTABLE / RULE_SET_FROZEN）。
 */
export class ApiError extends Error {
  constructor(public status: number, public detail: unknown, message: string) {
    super(message)
    this.name = 'ApiError'
  }

  /** 後端結構化錯誤碼（`{code, message}` 形狀時才有）。 */
  get code(): string | null {
    const d = this.detail as any
    return d && typeof d === 'object' && typeof d.code === 'string' ? d.code : null
  }

  /** 給人看的訊息：結構化錯誤取 message，不吐原始 JSON。 */
  get humanMessage(): string {
    const d = this.detail as any
    if (typeof d === 'string') return d
    if (d && typeof d === 'object' && typeof d.message === 'string') return d.message
    return this.message
  }
}

async function toError(r: Response): Promise<Error> {
  let d: any = null
  try { d = await r.json() } catch { /* ignore */ }
  const detail = d?.detail ?? null
  // 訊息格式維持 `${status} ${detail}`；物件型 detail 優先取 message（人話）而非整包 JSON。
  const text = detail === null
    ? r.statusText
    : typeof detail === 'string'
      ? detail
      : typeof detail?.message === 'string'
        ? detail.message
        : JSON.stringify(detail)
  return new ApiError(r.status, detail, `${r.status} ${text}`)
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

// DELETE 且需要回應 body（如 motion-modules row 級刪除回新版本 detail）
export async function apiDeleteJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { method: 'DELETE', headers: buildHeaders(false) })
  if (!r.ok) throw await toError(r)
  return r.json() as Promise<T>
}
