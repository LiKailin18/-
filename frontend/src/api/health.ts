import { raw } from './client'

/** 健康检查响应（契约：docs/api.md §1.6） */
export interface HealthResponse {
  status: 'ok' | 'degraded'
  db: 'ok' | 'down'
  version: string
}

/**
 * 探测后端连通性。
 *
 * 后端在数据库不可用时会返回 503，这属于「预期内的状态」而不是异常，
 * 因此放宽 validateStatus，让它作为正常数据交给页面展示。
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await raw.get<HealthResponse>('/health', {
    validateStatus: (status) => status === 200 || status === 503,
  })
  return data
}
