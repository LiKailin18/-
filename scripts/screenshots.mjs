// 界面截图脚本（论文材料用）。
//
// 用 Playwright 无头浏览器逐页截图到 docs/assets/screenshots/。
// 首次使用需要装一次浏览器内核（约 150 MB）：
//   cd frontend && npm i -D playwright && npx playwright install chromium
// 然后（前端已跑在 http://127.0.0.1:8080 或 5173）：
//   node scripts/screenshots.mjs
//
// 默认账号：
//   管理员  admin / Admin1234!  （覆盖工作台 + 管理端五页）
//   普通用户 e2e3553388 / Test1234!  （覆盖用户端页面）

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8080'
const OUT = new URL('../docs/assets/screenshots/', import.meta.url).pathname
mkdirSync(OUT, { recursive: true })

const shots = [
  { path: '01-login.png', url: '/login', name: '登录页' },
  { path: '02-dashboard.png', url: '/', name: '工作台（推荐 + 今日任务）' },
  { path: '03-materials.png', url: '/materials', name: '学习资料' },
  { path: '04-notes.png', url: '/notes', name: '在线笔记' },
  { path: '05-plans.png', url: '/plans', name: '学习计划' },
  { path: '06-ai.png', url: '/ai', name: 'AI 助手' },
  { path: '07-stats.png', url: '/stats', name: '学习统计' },
  { path: '08-admin-dashboard.png', url: '/admin', name: '管理端·仪表盘' },
  { path: '09-admin-users.png', url: '/admin/users', name: '管理端·用户' },
  { path: '10-admin-content.png', url: '/admin/content', name: '管理端·内容' },
  { path: '11-admin-ai.png', url: '/admin/ai-usage', name: '管理端·AI 用量' },
  { path: '12-admin-settings.png', url: '/admin/settings', name: '管理端·配置' },
]

async function login(page, username, password) {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('用户名').fill(username)
  await page.getByPlaceholder('密码').fill(password)
  await page.getByRole('button', { name: '登 录' }).click()
  await page.waitForURL('**/')
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

try {
  // 1) 普通用户视角（前 7 张）
  await login(page, 'e2e3553388', 'Test1234!')
  for (const shot of shots.filter((s) => !s.path.startsWith('08'))) {
    await page.goto(`${BASE}${shot.url}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(800)
    await page.screenshot({ path: `${OUT}/${shot.path}`, fullPage: false })
    console.log(`✓ ${shot.path}  ${shot.name}`)
  }

  // 2) 管理员视角（管理端五页）
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('Admin1234!')
  await page.getByRole('button', { name: '登 录' }).click()
  await page.waitForURL('**/')
  for (const shot of shots.filter((s) => s.path.startsWith('08'))) {
    await page.goto(`${BASE}${shot.url}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)
    await page.screenshot({ path: `${OUT}/${shot.path}`, fullPage: false })
    console.log(`✓ ${shot.path}  ${shot.name}`)
  }
  console.log(`\n完成，共 ${shots.length} 张，输出目录：${OUT}`)
} finally {
  await browser.close()
}
