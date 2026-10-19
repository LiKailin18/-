import type { Page, TaskCompleteOut, TaskOut } from '../types/api'
import { api } from './client'

/** 学习任务接口（契约：docs/api.md §8） */

export async function listTasks(params: {
  page: number
  size: number
  plan_id?: string
  plan_date?: string
  date_from?: string
  date_to?: string
  status?: string
}): Promise<Page<TaskOut>> {
  const { data } = await api.get<Page<TaskOut>>('/tasks', { params })
  return data
}

export async function updateTask(
  id: string,
  payload: { title?: string; status?: string; plan_date?: string; est_minutes?: number },
): Promise<TaskOut> {
  const { data } = await api.patch<TaskOut>(`/tasks/${id}`, payload)
  return data
}

/** 原子操作：置为完成 + 写一条学习记录 */
export async function completeTask(
  id: string,
  payload: { duration_minutes: number; content?: string | null; create_record?: boolean },
): Promise<TaskCompleteOut> {
  const { data } = await api.post<TaskCompleteOut>(`/tasks/${id}/complete`, payload)
  return data
}

export async function deleteTask(id: string): Promise<void> {
  await api.delete(`/tasks/${id}`)
}
