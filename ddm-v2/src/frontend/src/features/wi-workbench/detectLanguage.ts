/**
 * Client-side language detection — a faithful mirror of the backend
 * `detect_language` in `src/ddm_v2/nlp/prompts/language_aware.py`.
 *
 * This is a **preview only** (shows the user what language the parser will likely
 * treat the input as). The authoritative language is whatever the backend returns
 * in `ai.plan.language` after parsing; this local guess must not be persisted or
 * sent as the language.
 *
 * Rules (kept in lockstep with the Python side):
 *   - empty / whitespace only            -> 'zh' (backend default)
 *   - CJK chars / non-space chars >= 0.30 -> 'zh'
 *   - ASCII letters / non-space >= 0.50 AND CJK ratio < 0.10 -> 'en'
 *   - otherwise                           -> 'mixed'
 */
export type DetectedLanguage = 'zh' | 'en' | 'mixed'

export function detectLanguage(text: string): DetectedLanguage {
  if (!text) return 'zh'

  let cjk = 0
  let asciiLetters = 0
  let nonSpace = 0

  for (const ch of text) {
    if (/\s/.test(ch)) continue
    nonSpace += 1
    const code = ch.codePointAt(0) ?? 0
    // CJK Unified Ideographs: U+4E00..U+9FFF
    if (code >= 0x4e00 && code <= 0x9fff) cjk += 1
    // ASCII letters a-z A-Z
    else if ((code >= 0x41 && code <= 0x5a) || (code >= 0x61 && code <= 0x7a)) asciiLetters += 1
  }

  if (nonSpace === 0) return 'zh'

  const cjkRatio = cjk / nonSpace
  const asciiRatio = asciiLetters / nonSpace

  if (cjkRatio >= 0.3) return 'zh'
  if (asciiRatio >= 0.5 && cjkRatio < 0.1) return 'en'
  return 'mixed'
}
