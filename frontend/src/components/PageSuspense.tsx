import { Flex, Spin } from 'antd'
import { Suspense } from 'react'

/** 路由级懒加载的兜底 UI（页面 chunk 加载中）。 */
export default function PageSuspense({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <Flex justify="center" align="center" style={{ minHeight: 240 }}>
          <Spin size="large" />
        </Flex>
      }
    >
      {children}
    </Suspense>
  )
}
