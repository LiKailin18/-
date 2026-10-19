import { QueryClient } from '@tanstack/react-query'

/**
 * 全局唯一的 QueryClient。
 * 单独放一个模块是为了让登出等场景（stores/auth）能清空缓存，
 * 而不必从 main.tsx 反向导入（避免循环依赖）。
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})
