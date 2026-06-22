import { useMutation } from '@tanstack/react-query'
import { apiPost } from '../../shared/api/client'
import type { LevelPayloadRow } from './logic'

export interface LevelIssue { code: string; row_index: number; message: string }
export interface LevelValidateResult { valid: boolean; issues: LevelIssue[] }

// R1–R9 驗證（後端權威）
export const useValidateLevel = () =>
  useMutation({ mutationFn: (rows: LevelPayloadRow[]) =>
    apiPost<LevelValidateResult>('/api/v2/level/validate', rows) })
