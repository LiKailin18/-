import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { App as AntdApp, Button, Card, Flex, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { register } from '../../api/auth'
import { toApiError } from '../../api/client'

const { Text, Title } = Typography

interface RegisterForm {
  username: string
  email: string
  password: string
  confirm: string
  nickname?: string
}

export default function RegisterPage() {
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()
  const [submitting, setSubmitting] = useState(false)

  const onFinish = async (values: RegisterForm) => {
    setSubmitting(true)
    try {
      await register({
        username: values.username,
        email: values.email,
        password: values.password,
        nickname: values.nickname || null,
      })
      // 契约：注册不自动登录（docs/api.md §3）
      message.success('注册成功，请登录')
      navigate('/login', { replace: true })
    } catch (error) {
      const apiError = toApiError(error)
      message.error(apiError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Flex justify="center" align="center" style={{ minHeight: '100vh', padding: 24 }}>
      <Card style={{ width: 420 }}>
        <Flex vertical gap={4} style={{ marginBottom: 20 }}>
          <Title level={4} style={{ margin: 0 }}>
            注册账号
          </Title>
          <Text type="secondary">用户名 3-32 位字母数字下划线；密码至少 8 位且含字母与数字</Text>
        </Flex>

        <Form<RegisterForm> layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { pattern: /^[A-Za-z0-9_]{3,32}$/, message: '3-32 位字母、数字或下划线' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用于登录的唯一标识" />
          </Form.Item>

          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '邮箱格式不正确' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="you@example.com" />
          </Form.Item>

          <Form.Item name="nickname" label="昵称（可选）">
            <Input placeholder="展示用名称，留空则显示用户名" maxLength={32} />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少 8 位' },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
                message: '密码需同时包含字母与数字',
              },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" />
          </Form.Item>

          <Form.Item
            name="confirm"
            label="确认密码"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator: (_rule, value: string) =>
                  !value || getFieldValue('password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致')),
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="再次输入密码" />
          </Form.Item>

          <Button type="primary" htmlType="submit" block loading={submitting}>
            注册
          </Button>
        </Form>

        <Flex justify="center" style={{ marginTop: 16 }}>
          <Text type="secondary">
            已有账号？<Link to="/login">返回登录</Link>
          </Text>
        </Flex>
      </Card>
    </Flex>
  )
}
