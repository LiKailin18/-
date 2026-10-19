import { QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { queryClient } from './api/queryClient'
import './styles.css'

dayjs.locale('zh-cn')

const container = document.getElementById('root')
if (!container) {
  throw new Error('找不到 #root 挂载点，请检查 index.html')
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#1677ff' } }}>
        {/* AntdApp 提供 message/modal 的 context，避免静态方法拿不到主题与语言 */}
        <AntdApp>
          <App />
        </AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  </StrictMode>,
)
