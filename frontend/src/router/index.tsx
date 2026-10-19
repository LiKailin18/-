import { lazy } from 'react'
import { createBrowserRouter, Navigate } from 'react-router'

import PageSuspense from '../components/PageSuspense'
import MainLayout from '../layouts/MainLayout'
import GuestOnly from './GuestOnly'
import RequireAuth from './RequireAuth'

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

/**
 * 路由表。
 *
 * 约定：
 * - 登录态由 `useAuthStore` 统一判定，这里只做「放行 / 跳转」
 * - `/status` 保留 M0 的环境自检页（排查部署问题很有用）
 * - 管理端（功能 13）M6b 再挂 `/admin/*`，沿用同一套懒加载方式
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
  { path: '*', element: <Navigate to="/" replace /> },
])
