import { Flex, Spin } from 'antd'
import { Navigate, useLocation } from 'react-router'

import { useAuthStore } from '../stores/auth'

/** 未登录跳登录页；登录态恢复中先显示 loading（避免闪一下登录页）。 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((state) => state.status)
  const location = useLocation()

  if (status === 'unknown') {
    return (
      <Flex justify="center" align="center" style={{ minHeight: '60vh' }}>
        <Spin size="large" />
      </Flex>
    )
  }

  if (status === 'anonymous') {
    // 记住来源，登录后跳回去
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <>{children}</>
}
