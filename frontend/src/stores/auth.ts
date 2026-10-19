import { create } from 'zustand'

import { login as loginRequest, logout as logoutRequest } from '../api/auth'
import { refreshAccessToken, setAccessToken } from '../api/client'
import { queryClient } from '../api/queryClient'
import { fetchMe } from '../api/users'
import type { UserOut } from '../types/api'

export type AuthStatus = 'unknown' | 'authenticated' | 'anonymous'

interface AuthState {
  user: UserOut | null
  status: AuthStatus

  login: (username: string, password: string) => Promise<void>
  /** 启动时用 refresh Cookie 换回 access token */
  bootstrap: () => Promise<void>
  signOut: () => Promise<void>
  setUser: (user: UserOut) => void
}

/**
 * 登录态（CLAUDE.md §5.2：全局 store 只放登录态，业务数据一律走 TanStack Query）。
 *
 * access token 不进 store，而是放在 api/client 的模块变量里 ——
 * 它是网络层的东西，且必须只存在内存中（刷新页面即失效，靠 refresh Cookie 恢复）。
 */
export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: 'unknown',

  async login(username, password) {
    const token = await loginRequest(username, password)
    setAccessToken(token.access_token)
    const user = await fetchMe()
    set({ user, status: 'authenticated' })
  },

  async bootstrap() {
    try {
      // access token 只在内存里，页面刷新后必然为空 —— 用 httpOnly Cookie 换回来
      await refreshAccessToken()
      const user = await fetchMe()
      set({ user, status: 'authenticated' })
    } catch {
      // 没有有效 Cookie 是正常情况（未登录），不是错误
      setAccessToken(null)
      set({ user: null, status: 'anonymous' })
    }
  },

  async signOut() {
    try {
      await logoutRequest()
    } catch {
      // 后端不可达也必须让本地登出成功
    }
    setAccessToken(null)
    queryClient.clear()
    set({ user: null, status: 'anonymous' })
  },

  setUser(user) {
    set({ user })
  },
}))
