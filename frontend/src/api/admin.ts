import type {
  AdminAiStatsOut,
  AdminDailyOut,
  AdminMaterialPage,
  AdminNotePage,
  AdminOverviewOut,
  AdminQuizPage,
  AdminUserDetailOut,
  AdminUserPage,
  AiUsagePage,
  AuditLogPage,
  ResetPasswordOut,
  SettingItemOut,
  UserRole,
} from '../types/api'
import { api } from './client'

/** 功能 13 管理端接口（契约：docs/api.md §16）。全部走 /admin 前缀，非管理员 403。 */

const BASE = '/admin'

// --------------------------------------------------------------------- 13.1 仪表盘

export async function getAdminOverview(days = 30): Promise<AdminOverviewOut> {
  const { data } = await api.get<AdminOverviewOut>(`${BASE}/stats/overview`, { params: { days } })
  return data
}

export async function getAdminDaily(dateFrom?: string, dateTo?: string): Promise<AdminDailyOut> {
  const { data } = await api.get<AdminDailyOut>(`${BASE}/stats/daily`, {
    params: { from: dateFrom, to: dateTo },
  })
  return data
}

export async function getAdminAiStats(days = 30): Promise<AdminAiStatsOut> {
  const { data } = await api.get<AdminAiStatsOut>(`${BASE}/stats/ai`, { params: { days } })
  return data
}

// --------------------------------------------------------------------- 13.2 用户

export interface AdminUserListParams {
  page: number
  size: number
  keyword?: string
  role?: UserRole
  is_active?: boolean
  order?: string
}

export async function listAdminUsers(params: AdminUserListParams): Promise<AdminUserPage> {
  const { data } = await api.get<AdminUserPage>(`${BASE}/users`, { params })
  return data
}

export async function getAdminUser(id: string): Promise<AdminUserDetailOut> {
  const { data } = await api.get<AdminUserDetailOut>(`${BASE}/users/${id}`)
  return data
}

export async function updateAdminUser(
  id: string,
  payload: { is_active?: boolean; disabled_reason?: string | null; role?: UserRole },
): Promise<AdminUserDetailOut> {
  const { data } = await api.patch<AdminUserDetailOut>(`${BASE}/users/${id}`, payload)
  return data
}

export async function resetUserPassword(id: string): Promise<ResetPasswordOut> {
  const { data } = await api.post<ResetPasswordOut>(`${BASE}/users/${id}/reset-password`)
  return data
}

export async function revokeUserTokens(id: string): Promise<void> {
  await api.post(`${BASE}/users/${id}/revoke-tokens`)
}

// --------------------------------------------------------------------- 13.3 内容

export async function listAdminMaterials(params: {
  page: number
  size: number
  keyword?: string
  user_id?: string
  parse_status?: string
  file_ext?: string
}): Promise<AdminMaterialPage> {
  const { data } = await api.get<AdminMaterialPage>(`${BASE}/materials`, { params })
  return data
}

export async function deleteAdminMaterial(id: string): Promise<void> {
  await api.delete(`${BASE}/materials/${id}`)
}

export async function reparseAdminMaterial(id: string): Promise<void> {
  await api.post(`${BASE}/materials/${id}/reparse`)
}

export async function listAdminNotes(params: {
  page: number
  size: number
  keyword?: string
  user_id?: string
}): Promise<AdminNotePage> {
  const { data } = await api.get<AdminNotePage>(`${BASE}/notes`, { params })
  return data
}

export async function deleteAdminNote(id: string): Promise<void> {
  await api.delete(`${BASE}/notes/${id}`)
}

export async function listAdminQuizzes(params: {
  page: number
  size: number
  user_id?: string
  material_id?: string
}): Promise<AdminQuizPage> {
  const { data } = await api.get<AdminQuizPage>(`${BASE}/quizzes`, { params })
  return data
}

export async function deleteAdminQuiz(id: string): Promise<void> {
  await api.delete(`${BASE}/quizzes/${id}`)
}

// --------------------------------------------------------------------- 13.4 AI 用量

export async function listAiUsage(params: {
  page: number
  size: number
  user_id?: string
  scene?: string
  ok?: boolean
  date_from?: string
  date_to?: string
}): Promise<AiUsagePage> {
  const { data } = await api.get<AiUsagePage>(`${BASE}/ai-usage`, { params })
  return data
}

// --------------------------------------------------------------------- 13.5 配置与审计

export async function listSettings(): Promise<SettingItemOut[]> {
  const { data } = await api.get<{ items: SettingItemOut[] }>(`${BASE}/settings`)
  return data.items
}

export async function updateSettings(
  items: { key: string; value: unknown }[],
): Promise<SettingItemOut[]> {
  const { data } = await api.patch<{ items: SettingItemOut[] }>(`${BASE}/settings`, { items })
  return data.items
}

export async function listAuditLogs(params: {
  page: number
  size: number
  action?: string
  target_type?: string
  date_from?: string
  date_to?: string
}): Promise<AuditLogPage> {
  const { data } = await api.get<AuditLogPage>(`${BASE}/audit-logs`, { params })
  return data
}
