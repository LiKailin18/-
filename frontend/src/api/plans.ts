import type { GenerateTasksOut, Page, PlanDetailOut, PlanOut, PlanStatus } from '../types/api'
import { api } from './client'

/** 学习计划接口（契约：docs/api.md §7） */

export interface PlanPayload {
  title: string
  subject?: string | null
  goal?: string | null
  start_date: string
  end_date: string
  daily_minutes: number
  material_ids?: string[]
  status?: PlanStatus
}

export async function listPlans(params: {
  page: number
  size: number
  status?: string
}): Promise<Page<PlanOut>> {
  const { data } = await api.get<Page<PlanOut>>('/plans', { params })
  return data
}

export async function getPlan(id: string): Promise<PlanDetailOut> {
  const { data } = await api.get<PlanDetailOut>(`/plans/${id}`)
  return data
}

export async function createPlan(payload: PlanPayload): Promise<PlanOut> {
  const { data } = await api.post<PlanOut>('/plans', payload)
  return data
}

export async function updatePlan(id: string, payload: Partial<PlanPayload>): Promise<PlanOut> {
  const { data } = await api.patch<PlanOut>(`/plans/${id}`, payload)
  return data
}

export async function deletePlan(id: string): Promise<void> {
  await api.delete(`/plans/${id}`)
}

/** 幂等生成：全部已存在时后端返回 409 PLAN_001 */
export async function generateTasks(id: string, overwrite = false): Promise<GenerateTasksOut> {
  const { data } = await api.post<GenerateTasksOut>(`/plans/${id}/generate-tasks`, { overwrite })
  return data
}
