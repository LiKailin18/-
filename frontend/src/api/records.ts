import type { Page, RecordOut } from '../types/api'
import { api } from './client'

/** 学习记录接口（契约：docs/api.md §9） */

export interface RecordPayload {
  type: string
  started_at: string
  duration_minutes: number
  content?: string | null
  task_id?: string | null
  material_id?: string | null
}

export async function listRecords(params: {
  page: number
  size: number
  date_from?: string
  date_to?: string
  type?: string
}): Promise<Page<RecordOut>> {
  const { data } = await api.get<Page<RecordOut>>('/study-records', { params })
  return data
}

export async function createRecord(payload: RecordPayload): Promise<RecordOut> {
  const { data } = await api.post<RecordOut>('/study-records', payload)
  return data
}

export async function updateRecord(
  id: string,
  payload: Partial<RecordPayload>,
): Promise<RecordOut> {
  const { data } = await api.patch<RecordOut>(`/study-records/${id}`, payload)
  return data
}

export async function deleteRecord(id: string): Promise<void> {
  await api.delete(`/study-records/${id}`)
}
