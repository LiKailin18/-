import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 开发期由 Vite 代理转发，前端只调同源路径 —— 开发环境不产生跨域（CLAUDE.md §8）
    // 目标写 127.0.0.1 而不是 localhost：Windows 上 localhost 可能先解析到 IPv6 ::1，
    // 而后端监听的是 127.0.0.1，会导致代理 ECONNREFUSED
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    // 管理端与 echarts 体积较大，交给后续按需拆包（M6/M6b），此处仅提示阈值
    chunkSizeWarningLimit: 1200,
  },
})
