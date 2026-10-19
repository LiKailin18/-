import type { TokenOut, UserOut } from '../types/api'
import { raw } from './client'

/** 认证接口（契约：docs/api.md §3） */

export async function register(payload: {
  username: string
  email: string
  password: string
  nickname?: string | null
}): Promise<UserOut> {
  const { data } = await raw.post<UserOut>('/api/v1/auth/register', payload)
  return data
}

/** 登录用表单格式（OAuth2 规范，字段名固定 username / password） */
export async function login(username: string, password: string): Promise<TokenOut> {
  const form = new URLSearchParams({ username, password })
  const { data } = await raw.post<TokenOut>('/api/v1/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data
}

export async function logout(): Promise<void> {
  await raw.post('/api/v1/auth/logout')
}
