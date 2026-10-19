import { UploadOutlined, UserOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import {
  App as AntdApp,
  Avatar,
  Button,
  Card,
  Col,
  Flex,
  Form,
  Input,
  InputNumber,
  Row,
  Typography,
  Upload,
} from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { toApiError } from '../api/client'
import { changePassword, updateMe, uploadAvatar } from '../api/users'
import AuthImage from '../components/AuthImage'
import { useAuthStore } from '../stores/auth'
import type { UserUpdateIn } from '../types/api'

const { Text, Title } = Typography

interface ProfileForm extends UserUpdateIn {
  email: string
  daily_target_minutes: number
}

interface PasswordForm {
  old_password: string
  new_password: string
  confirm: string
}

/** 个人信息与安全设置 —— 功能 2。 */
export default function ProfilePage() {
  const user = useAuthStore((state) => state.user)
  const setUser = useAuthStore((state) => state.setUser)
  const signOut = useAuthStore((state) => state.signOut)
  const navigate = useNavigate()
  const { message } = AntdApp.useApp()

  const [profileForm] = Form.useForm<ProfileForm>()
  const [passwordForm] = Form.useForm<PasswordForm>()
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPassword, setSavingPassword] = useState(false)

  if (!user) {
    return null
  }

  const onSaveProfile = async (values: ProfileForm) => {
    setSavingProfile(true)
    try {
      const updated = await updateMe({
        email: values.email,
        nickname: values.nickname || null,
        learning_goal: values.learning_goal || null,
        daily_target_minutes: values.daily_target_minutes,
      })
      setUser(updated)
      message.success('已保存')
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSavingProfile(false)
    }
  }

  const onChangePassword = async (values: PasswordForm) => {
    setSavingPassword(true)
    try {
      await changePassword({
        old_password: values.old_password,
        new_password: values.new_password,
      })
      message.success('密码已修改，请重新登录')
      // 改密码会让 token_version +1，当前访问令牌立即失效，所以主动登出
      await signOut()
      navigate('/login', { replace: true })
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSavingPassword(false)
    }
  }

  const onUploadAvatar: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    try {
      const result = await uploadAvatar(file as File)
      setUser({ ...user, avatar_url: result.avatar_url })
      onSuccess?.(result)
      message.success('头像已更新')
    } catch (error) {
      onError?.(error as Error)
      message.error(toApiError(error).message)
    }
  }

  return (
    <Flex vertical gap={16} style={{ maxWidth: 960, margin: '0 auto' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          个人信息
        </Title>
        <Text type="secondary">用户名不可修改；邮箱与昵称可随时调整</Text>
      </div>

      <Card title="头像">
        <Flex align="center" gap={16} wrap>
          {user.avatar_url ? (
            <AuthImage path={user.avatar_url} size={64} />
          ) : (
            <Avatar size={64} icon={<UserOutlined />} />
          )}
          <Upload accept=".png,.jpg,.jpeg" showUploadList={false} customRequest={onUploadAvatar}>
            <Button icon={<UploadOutlined />}>上传头像</Button>
          </Upload>
          <Text type="secondary">PNG / JPG，不超过 2MB</Text>
        </Flex>
      </Card>

      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card title="基本信息">
            <Form<ProfileForm>
              form={profileForm}
              layout="vertical"
              requiredMark={false}
              initialValues={{
                email: user.email,
                nickname: user.nickname ?? '',
                learning_goal: user.learning_goal ?? '',
                daily_target_minutes: user.daily_target_minutes,
              }}
              onFinish={onSaveProfile}
            >
              <Form.Item label="用户名">
                <Input value={user.username} disabled />
              </Form.Item>

              <Form.Item
                name="email"
                label="邮箱"
                rules={[
                  { required: true, message: '请输入邮箱' },
                  { type: 'email', message: '邮箱格式不正确' },
                ]}
              >
                <Input placeholder="you@example.com" />
              </Form.Item>

              <Form.Item name="nickname" label="昵称">
                <Input placeholder="展示用名称，留空则显示用户名" maxLength={32} />
              </Form.Item>

              <Form.Item name="learning_goal" label="学习目标">
                <Input.TextArea
                  rows={2}
                  maxLength={200}
                  showCount
                  placeholder="例如：通过期末考试"
                />
              </Form.Item>

              <Form.Item
                name="daily_target_minutes"
                label="每日学习目标（分钟）"
                rules={[{ required: true, message: '请输入每日目标' }]}
              >
                <InputNumber min={1} max={1440} style={{ width: 200 }} />
              </Form.Item>

              <Button type="primary" htmlType="submit" loading={savingProfile}>
                保存修改
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="修改密码">
            <Text type="secondary">
              修改成功后当前登录状态会失效，需要用新密码重新登录。
            </Text>
            <Form<PasswordForm>
              form={passwordForm}
              layout="vertical"
              requiredMark={false}
              style={{ marginTop: 12 }}
              onFinish={onChangePassword}
            >
              <Form.Item
                name="old_password"
                label="原密码"
                rules={[{ required: true, message: '请输入原密码' }]}
              >
                <Input.Password autoComplete="current-password" />
              </Form.Item>

              <Form.Item
                name="new_password"
                label="新密码"
                rules={[
                  { required: true, message: '请输入新密码' },
                  { min: 8, message: '密码至少 8 位' },
                  {
                    pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
                    message: '密码需同时包含字母与数字',
                  },
                ]}
              >
                <Input.Password autoComplete="new-password" />
              </Form.Item>

              <Form.Item
                name="confirm"
                label="确认新密码"
                dependencies={['new_password']}
                rules={[
                  { required: true, message: '请再次输入新密码' },
                  ({ getFieldValue }) => ({
                    validator: (_rule, value: string) =>
                      !value || getFieldValue('new_password') === value
                        ? Promise.resolve()
                        : Promise.reject(new Error('两次输入的密码不一致')),
                  }),
                ]}
              >
                <Input.Password autoComplete="new-password" />
              </Form.Item>

              <Button type="primary" htmlType="submit" loading={savingPassword}>
                修改密码
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>
    </Flex>
  )
}
