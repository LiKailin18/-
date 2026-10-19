import { Flex, Spin } from 'antd'
import { Navigate } from 'react-router'

import { useAuthStore } from '../stores/auth'

/** 已登录用户不应再看到登录/注册页。 */
export default function GuestOnly({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((state) => state.status)

  if (status === 'unknown') {
    return (
      <Flex justify="center" align="center" style={{ minHeight: '60vh' }}>
        <Spin size="large" />
      </Flex>
    )
  }

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
