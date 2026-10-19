import { useQuery } from '@tanstack/react-query'
import { Button, Flex, Result, Spin } from 'antd'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'

import { fetchMe } from '../api/users'
import { useAuthStore } from '../stores/auth'

/**
 * 管理端守卫（契约：docs/api.md §16.7）。
 *
 * 关键点：进入 `/admin/*` 时**重新请求 `/users/me`**，不能只信内存里的 role ——
 * 覆盖「用户在另一个标签页被降权 / 被禁用」的场景；顺手把 store 里的用户刷新一遍。
 */
export default function RequireRole({ children }: { children: React.ReactNode }) {
  const setUser = useAuthStore((state) => state.setUser)
  const navigate = useNavigate()

  const { data, isPending, isError, error } = useQuery({
    queryKey: ['admin', 'me-check'],
    queryFn: fetchMe,
    staleTime: 0,
    gcTime: 0,
    retry: false,
  })

  useEffect(() => {
    if (data) setUser(data)
  }, [data, setUser])

  if (isPending) {
    return (
      <Flex justify="center" align="center" style={{ minHeight: '60vh' }}>
        <Spin size="large" description="正在校验管理端权限…">
          <div style={{ padding: 40 }} />
        </Spin>
      </Flex>
    )
  }

  if (isError || !data) {
    return (
      <Result
        status="error"
        title="无法确认权限"
        subTitle={error instanceof Error ? error.message : '请重新登录后再试'}
        extra={
          <Button type="primary" onClick={() => void navigate('/')}>
            返回工作台
          </Button>
        }
      />
    )
  }

  if (data.role !== 'admin') {
    return (
      <Result
        status="403"
        title="403"
        subTitle="只有管理员可以访问管理端"
        extra={
          <Button type="primary" onClick={() => void navigate('/')}>
            返回工作台
          </Button>
        }
      />
    )
  }

  return <>{children}</>
}
