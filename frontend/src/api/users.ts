import type { AvatarOut, PasswordChangeIn, UserOut, UserUpdateIn } from '../types/api'
import { api } from './client'

/** 用户接口（契约：docs/api.md §4） */

export async function fetchMe(): Promise<UserOut> {
  const { data } = await api.get<UserOut>('/users/me')
  return data
}

export async function updateMe(payload: UserUpdateIn): Promise<UserOut> {
  const { data } = await api.patch<UserOut>('/users/me', payload)
  return data
}

export async function changePassword(payload: PasswordChangeIn): Promise<void> {
  await api.post('/users/me/password', payload)
}

export async function uploadAvatar(file: File): Promise<AvatarOut> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<AvatarOut>('/users/me/avatar', form)
  return data
}
