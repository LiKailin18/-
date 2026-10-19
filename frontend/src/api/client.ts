import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

/**
 * 网络层（CLAUDE.md §7）。
 *
 * 三条硬约束：
 * 1. 业务请求只走 `api` 实例（baseURL=/api/v1）；`raw` 不带拦截器，
 *    专供登录/注册/刷新使用，避免刷新逻辑递归调用自己
 * 2. access token **只存内存**，不进 localStorage（docs/技术栈定稿.md §3.3）
 * 3. 401 + AUTH_002 才触发刷新，且用单例 Promise 串行化 —— 并发请求共享同一次刷新，
 *    否则 5 个请求会打 5 次刷新接口（契约 §1.5）
 */

/** 后端统一错误体 */
export interface ApiErrorBody {
  code: string
  message: string
  detail?: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail?: unknown

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

/** 不带拦截器的原始实例：登录、注册、刷新都走它 */
export const raw = axios.create({ baseURL: '/', timeout: 15000 })

/** 业务实例 */
export const api = axios.create({ baseURL: '/api/v1', timeout: 15000 })

let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error

  const axiosError = error as AxiosError<ApiErrorBody>
  const body = axiosError.response?.data

  if (body && typeof body === 'object' && 'code' in body && 'message' in body) {
    return new ApiError(axiosError.response!.status, body.code, body.message, body.detail)
  }

  if (axiosError.code === 'ECONNABORTED') {
    return new ApiError(408, 'NETWORK_TIMEOUT', '请求超时，请稍后重试')
  }
  return new ApiError(0, 'NETWORK_ERROR', '网络异常，请检查后端是否已启动')
}

/** 刷新中的 Promise：并发请求共享同一个，避免刷新风暴 */
let refreshPromise: Promise<string> | null = null

export function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = raw
      .post<{ access_token: string }>('/api/v1/auth/refresh')
      .then((res) => {
        setAccessToken(res.data.access_token)
        return res.data.access_token
      })
      .catch((error: unknown) => {
        setAccessToken(null)
        throw toApiError(error)
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    const apiError = toApiError(error)
    const config = (error as AxiosError).config as RetriableConfig | undefined

    // 只有「access token 过期」才刷新重放；其余错误直接抛给调用方
    if (apiError.code === 'AUTH_002' && config && !config._retried) {
      config._retried = true
      try {
        const token = await refreshAccessToken()
        config.headers.Authorization = `Bearer ${token}`
        return await api.request(config)
      } catch {
        // 刷新失败：丢弃原错误，把刷新失败的原因抛出去（通常是 AUTH_003 → 前端跳登录）
        throw apiError
      }
    }

    throw apiError
  },
)
