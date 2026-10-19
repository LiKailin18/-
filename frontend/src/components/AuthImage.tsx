import { UserOutlined } from '@ant-design/icons'
import { Avatar } from 'antd'
import { useEffect, useState } from 'react'

import { api } from '../api/client'

/**
 * 受保护图片（头像）。
 *
 * 为什么不用 <img src={url}>：access token 只存在内存里，浏览器加载图片时**不会**
 * 带上 Authorization 头，直接 src 会 401。所以这里用 axios 取 blob 再转 object URL，
 * 复用同一套鉴权与 401 刷新逻辑（CLAUDE.md §7）。
 */
export default function AuthImage({ path, size }: { path: string; size: number }) {
  const [src, setSrc] = useState<string | undefined>()

  useEffect(() => {
    let objectUrl: string | undefined
    let cancelled = false

    // avatar_url 里带 /api/v1 前缀，而 axios 实例的 baseURL 已经是它了
    const relative = path.replace(/^\/api\/v1/, '')

    api
      .get<Blob>(relative, { responseType: 'blob' })
      .then(({ data }) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(data)
        setSrc(objectUrl)
      })
      .catch(() => {
        // 加载失败就退回默认图标，不打扰用户
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  return <Avatar size={size} src={src} icon={<UserOutlined />} />
}
