import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { App as AntdApp, Button, Card, Flex, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'

import { useAuthStore } from '../../stores/auth'

const { Text, Title } = Typography

interface LoginForm {
  username: string
  password: string
}

export default function LoginPage() {
  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = AntdApp.useApp()
  const [submitting, setSubmitting] = useState(false)

  const onFinish = async (values: LoginForm) => {
    setSubmitting(true)
    try {
      await login(values.username, values.password)
      message.success('登录成功')
      // 被守卫拦下时会记住来源，登录后跳回去
      const from = (location.state as { from?: string } | null)?.from
      navigate(from ?? '/', { replace: true })
    } catch (error) {
      // 后端已经给出可直接展示的中文文案，这里不要自己拼
      message.error(error instanceof Error ? error.message : '登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Flex justify="center" align="center" style={{ minHeight: '100vh', padding: 24 }}>
      <Card style={{ width: 380 }}>
        <Flex vertical gap={4} style={{ marginBottom: 20 }}>
          <Title level={4} style={{ margin: 0 }}>
            智能学习系统
          </Title>
          <Text type="secondary">登录后开始你的学习计划</Text>
        </Flex>

        <Form<LoginForm> layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              autoComplete="current-password"
            />
          </Form.Item>

          <Button type="primary" htmlType="submit" block loading={submitting}>
            登录
          </Button>
        </Form>

        <Flex justify="center" style={{ marginTop: 16 }}>
          <Text type="secondary">
            还没有账号？<Link to="/register">立即注册</Link>
          </Text>
        </Flex>
      </Card>
    </Flex>
  )
}
