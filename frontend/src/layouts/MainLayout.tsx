import { LogoutOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { App as AntdApp, Dropdown, Flex, Layout, Menu, Typography } from 'antd'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'

import AuthImage from '../components/AuthImage'
import { useAuthStore } from '../stores/auth'

const { Content, Header } = Layout
const { Text } = Typography

/** 主框架：顶部导航 + 用户菜单 + 内容区。 */
export default function MainLayout() {
  const user = useAuthStore((state) => state.user)
  const signOut = useAuthStore((state) => state.signOut)
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = AntdApp.useApp()

  const handleSignOut = async () => {
    await signOut()
    message.success('已退出登录')
    navigate('/login', { replace: true })
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 24,
          background: '#fff',
          borderBottom: '1px solid #f0f0f0',
          paddingInline: 24,
        }}
      >
        <Text strong style={{ fontSize: 16, whiteSpace: 'nowrap' }}>
          智能学习系统
        </Text>

        <Menu
          mode="horizontal"
          selectedKeys={[location.pathname]}
          style={{ flex: 1, borderBottom: 'none' }}
          items={[
            { key: '/', label: <Link to="/">工作台</Link> },
            { key: '/materials', label: <Link to="/materials">学习资料</Link> },
            { key: '/notes', label: <Link to="/notes">在线笔记</Link> },
            { key: '/plans', label: <Link to="/plans">学习计划</Link> },
            { key: '/ai', label: <Link to="/ai">AI 助手</Link> },
            { key: '/stats', label: <Link to="/stats">学习统计</Link> },
            { key: '/profile', label: <Link to="/profile">个人信息</Link> },
          ]}
        />

        <Dropdown
          menu={{
            items: [
              { key: '/profile', icon: <UserOutlined />, label: '个人信息' },
              // 管理端入口只对管理员出现（契约 §16.7：入口只在 role === 'admin' 时显示）
              ...(user?.role === 'admin'
                ? [{ key: '/admin', icon: <SafetyCertificateOutlined />, label: '管理端' }]
                : []),
              { key: '/status', label: '环境自检' },
              { type: 'divider' as const },
              { key: 'signout', icon: <LogoutOutlined />, label: '退出登录' },
            ],
            onClick: ({ key }) => {
              if (key === 'signout') {
                void handleSignOut()
              } else {
                void navigate(key)
              }
            },
          }}
        >
          <Flex align="center" gap={8} style={{ cursor: 'pointer' }}>
            {user?.avatar_url ? (
              <AuthImage path={user.avatar_url} size={28} />
            ) : (
              <UserOutlined style={{ fontSize: 18 }} />
            )}
            <Text>{user?.nickname || user?.username}</Text>
          </Flex>
        </Dropdown>
      </Header>

      <Content style={{ padding: 24 }}>
        <Outlet />
      </Content>
    </Layout>
  )
}
