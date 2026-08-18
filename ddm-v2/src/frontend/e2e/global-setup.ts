// ADR-032 Phase A：把共用開發 DB 的預設 e2e 身分（IEC141289）的 locale 釘死回
// zh-TW，在整個 e2e 套件跑之前執行一次。
//
// 為什麼需要這個檔：現有 11 個 spec 用中文文字定位元素（如 `toHaveText(/主數據管理/)`）。
// `/api/v2/me` 現在會回傳這個使用者在**共用開發 DB**裡的真實 locale（ADR-032 D3.1）；
// 若曾經有任何一次手動測試／半成品 spec 真的打中 `PATCH /api/v2/me/locale`
// （而不是像 `locale-switcher.spec.ts` 那樣攔截掉），這個使用者的 locale 就會
// 永久變成 en，下一次整套 e2e 執行時全部中文斷言會變成不可預期的紅燈——
// 而且症狀長得像介面壞了，實際是殘留的測試狀態（同類坑見 CLAUDE.md
// docker port 那條踩過的教訓）。這裡在套件開始前主動重置，讓套件本身
// 對這個失效模式有自癒能力，不必依賴「大家都乖乖 mock」。
async function globalSetup() {
  const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
  try {
    const res = await fetch(`${baseURL}/api/v2/me/locale`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-Username': 'IEC141289' },
      body: JSON.stringify({ locale: 'zh-TW' }),
    })
    if (!res.ok) {
      // 不擋整套 e2e——後端可能還沒跑到這個版本（migration 未套用）。
      // 但要出聲，不要靜默吞掉（CLAUDE.md「No error bypass」）。
      console.warn(`[global-setup] PATCH /api/v2/me/locale 回 ${res.status}，略過重置（locale 鎖定可能失效）`)
    }
  } catch (err) {
    console.warn('[global-setup] 無法連到後端重置 locale（可能 preview_server 未啟動）：', err)
  }
}

export default globalSetup
