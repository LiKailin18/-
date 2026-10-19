import {
  BarChartOutlined,
  DashboardOutlined,
  FileTextOutlined,
  HomeOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { Breadcrumb, Button, Flex, Layout, Menu, Tag, Typography } from 'antd'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'

const { Content, Header, Sider } = Layout
const { Text } = Typography

const MENU = [
  { key: '/admin', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/admin/users', icon: <TeamOutlined />, label: '用户管理' },
  { key: '/admin/content', icon: <FileTextOutlined />, label: '内容管理' },
  { key: '/admin/ai-usage', icon: <BarChartOutlined />, label: 'AI 用量' },
  { key: '/admin/settings', icon: <SettingOutlined />, label: '系统配置' },
]

/**
 * 管理端框架（契约 §16.7）：同一个 React 应用里的独立布局，左侧菜单 + 面包屑。
 *
 * 页面里**不出现任何 AI 生成入口** —— 管理端不能批量生成内容（成本与合规上的边界）。
 */
export default function AdminLayout() {
  const location = useLocation()
  const navigate = useNavigate()

  const current = MENU.find((item) => item.key === location.pathname) ?? MENU[0]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light" width={200} breakpoint="lg" collapsedWidth={64}>
        <Flex align="center" justify="center" style={{ height: 56, borderBottom: '1px solid #f0f0f0' }}>
          <Text strong>管理端</Text>
        </Flex>
        <Menu
          mode="inline"
          selectedKeys={[current.key]}
          style={{ borderInlineEnd: 'none' }}
          items={MENU.map((item) => ({
            key: item.key,
            icon: item.icon,
            label: <Link to={item.key}>{item.label}</Link>,
          }))}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: '#fff',
            borderBottom: '1px solid #f0f0f0',
            paddingInline: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Breadcrumb
            items={[
              { title: <Link to="/">工作台</Link> },
              { title: current.label },
            ]}
          />
          <Flex align="center" gap={12}>
            <Tag color="gold">功能 13 · 管理端</Tag>
            <Button onClick={() => void navigate('/')} icon={<HomeOutlined />}>
              返回用户端
            </Button>
          </Flex>
        </Header>

        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
