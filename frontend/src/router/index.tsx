import { lazy } from 'react'
import { createBrowserRouter, Navigate } from 'react-router'

import PageSuspense from '../components/PageSuspense'
import MainLayout from '../layouts/MainLayout'
import GuestOnly from './GuestOnly'
import RequireAuth from './RequireAuth'
import RequireRole from './RequireRole'

// 路由级懒加载：首屏只下载登录页/布局，资料、个人中心等按需加载
const DashboardPage = lazy(() => import('../pages/DashboardPage'))
const MaterialsPage = lazy(() => import('../pages/MaterialsPage'))
const NotesPage = lazy(() => import('../pages/NotesPage'))
const PlansPage = lazy(() => import('../pages/PlansPage'))
const AiPage = lazy(() => import('../pages/AiPage'))
const StatsPage = lazy(() => import('../pages/StatsPage'))
const ProfilePage = lazy(() => import('../pages/ProfilePage'))
const HomePage = lazy(() => import('../pages/HomePage'))
const LoginPage = lazy(() => import('../pages/auth/LoginPage'))
const RegisterPage = lazy(() => import('../pages/auth/RegisterPage'))

// 功能 13 管理端：独立布局 + 独立 chunk（普通用户不会下载这些代码）
const AdminLayout = lazy(() => import('../layouts/AdminLayout'))
const AdminDashboardPage = lazy(() => import('../pages/admin/AdminDashboardPage'))
const AdminUsersPage = lazy(() => import('../pages/admin/AdminUsersPage'))
const AdminContentPage = lazy(() => import('../pages/admin/AdminContentPage'))
const AdminAiUsagePage = lazy(() => import('../pages/admin/AdminAiUsagePage'))
const AdminSettingsPage = lazy(() => import('../pages/admin/AdminSettingsPage'))

/**
 * 路由表。
 *
 * 约定：
 * - 登录态由 `useAuthStore` 统一判定，这里只做「放行 / 跳转」
 * - `/status` 保留 M0 的环境自检页（排查部署问题很有用）
 * - 管理端（功能 13）挂在 `/admin/*`，走 `RequireRole` 守卫 + 独立 `AdminLayout`（M6b）
 */
export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <GuestOnly>
        <PageSuspense>
          <LoginPage />
        </PageSuspense>
      </GuestOnly>
    ),
  },
  {
    path: '/register',
    element: (
      <GuestOnly>
        <PageSuspense>
          <RegisterPage />
        </PageSuspense>
      </GuestOnly>
    ),
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <MainLayout />
      </RequireAuth>
    ),
    children: [
      {
        index: true,
        element: (
          <PageSuspense>
            <DashboardPage />
          </PageSuspense>
        ),
      },
      {
        path: 'materials',
        element: (
          <PageSuspense>
            <MaterialsPage />
          </PageSuspense>
        ),
      },
      {
        path: 'notes',
        element: (
          <PageSuspense>
            <NotesPage />
          </PageSuspense>
        ),
      },
      {
        path: 'plans',
        element: (
          <PageSuspense>
            <PlansPage />
          </PageSuspense>
        ),
      },
      {
        path: 'ai',
        element: (
          <PageSuspense>
            <AiPage />
          </PageSuspense>
        ),
      },
      {
        path: 'stats',
        element: (
          <PageSuspense>
            <StatsPage />
          </PageSuspense>
        ),
      },
      {
        path: 'profile',
        element: (
          <PageSuspense>
            <ProfilePage />
          </PageSuspense>
        ),
      },
      {
        path: 'status',
        element: (
          <PageSuspense>
            <HomePage />
          </PageSuspense>
        ),
      },
    ],
  },
  {
    path: '/admin',
    element: (
      <RequireAuth>
        <RequireRole>
          <PageSuspense>
            <AdminLayout />
          </PageSuspense>
        </RequireRole>
      </RequireAuth>
    ),
    children: [
      {
        index: true,
        element: (
          <PageSuspense>
            <AdminDashboardPage />
          </PageSuspense>
        ),
      },
      {
        path: 'users',
        element: (
          <PageSuspense>
            <AdminUsersPage />
          </PageSuspense>
        ),
      },
      {
        path: 'content',
        element: (
          <PageSuspense>
            <AdminContentPage />
          </PageSuspense>
        ),
      },
      {
        path: 'ai-usage',
        element: (
          <PageSuspense>
            <AdminAiUsagePage />
          </PageSuspense>
        ),
      },
      {
        path: 'settings',
        element: (
          <PageSuspense>
            <AdminSettingsPage />
          </PageSuspense>
        ),
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
