import { useEffect } from 'react'
import { RouterProvider } from 'react-router'

import { router } from './router'
import { useAuthStore } from './stores/auth'

export default function App() {
  const bootstrap = useAuthStore((state) => state.bootstrap)

  // 启动时用 httpOnly 的 refresh Cookie 换回 access token（token 只在内存，
  // 页面刷新后必然为空）。整个应用只跑一次。
  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  return <RouterProvider router={router} />
}
