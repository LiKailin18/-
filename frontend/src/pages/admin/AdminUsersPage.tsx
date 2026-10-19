import {
  KeyOutlined,
  LogoutOutlined,
  ReloadOutlined,
  StopOutlined,
  UnlockOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  Descriptions,
  Drawer,
  Flex,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'

import {
  getAdminUser,
  listAdminUsers,
  resetUserPassword,
  revokeUserTokens,
  updateAdminUser,
} from '../../api/admin'
import { toApiError } from '../../api/client'
import { useAuthStore } from '../../stores/auth'
import type { AdminUserDetailOut, AdminUserItemOut, UserRole } from '../../types/api'

const { Text } = Typography

const ROLE_META: Record<UserRole, { text: string; color: string }> = {
  user: { text: '普通用户', color: 'blue' },
  admin: { text: '管理员', color: 'gold' },
}

/**
 * 功能 13.2 用户管理。
 *
 * 「禁止操作自己」前端也挡一道（按钮禁用 + 提示），但**真正的拦截在后端**
 * （400 `ADMIN_001`）—— 前端只是减少误点的机会。
 */
export default function AdminUsersPage() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const currentUser = useAuthStore((state) => state.user)

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [keyword, setKeyword] = useState<string | undefined>()
  const [role, setRole] = useState<UserRole | undefined>()
  const [activeFilter, setActiveFilter] = useState<boolean | undefined>()
  const [order, setOrder] = useState('-created_at')

  const [disabling, setDisabling] = useState<AdminUserItemOut | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [resetResult, setResetResult] = useState<{ username: string; password: string } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<{ disabled_reason: string }>()

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['admin-users', page, size, keyword, role, activeFilter, order],
    queryFn: () =>
      listAdminUsers({
        page,
        size,
        keyword,
        role,
        is_active: activeFilter,
        order,
      }),
  })

  const { data: detail } = useQuery({
    queryKey: ['admin-user', detailId],
    queryFn: () => getAdminUser(detailId as string),
    enabled: Boolean(detailId),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    await queryClient.invalidateQueries({ queryKey: ['admin-user'] })
    await queryClient.invalidateQueries({ queryKey: ['admin-audit'] })
  }

  const isSelf = (row: AdminUserItemOut) => row.id === currentUser?.id

  const handleDisable = async () => {
    if (!disabling) return
    const values = await form.validateFields()
    setSubmitting(true)
    try {
      await updateAdminUser(disabling.id, {
        is_active: false,
        disabled_reason: values.disabled_reason,
      })
      message.success(`已禁用 ${disabling.username}，其登录态已失效`)
      setDisabling(null)
      form.resetFields()
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleEnable = async (row: AdminUserItemOut) => {
    try {
      await updateAdminUser(row.id, { is_active: true })
      message.success(`已启用 ${row.username}`)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleRoleChange = async (row: AdminUserItemOut, next: UserRole) => {
    try {
      await updateAdminUser(row.id, { role: next })
      message.success(`已把 ${row.username} 改为${ROLE_META[next].text}（旧登录态已失效）`)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleReset = async (row: AdminUserItemOut) => {
    try {
      const result = await resetUserPassword(row.id)
      setResetResult({ username: row.username, password: result.temporary_password })
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleRevoke = async (row: AdminUserItemOut) => {
    try {
      await revokeUserTokens(row.id)
      message.success(`已强制 ${row.username} 下线`)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<AdminUserItemOut>['columns'] = [
    {
      title: '用户',
      width: 200,
      render: (_, row) => (
        <Space size={6} wrap>
          <Text strong>{row.username}</Text>
          {row.nickname && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {row.nickname}
            </Text>
          )}
          {isSelf(row) && <Tag color="processing">当前登录</Tag>}
        </Space>
      ),
    },
    { title: '邮箱', dataIndex: 'email', width: 200 },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (value: UserRole) => <Tag color={ROLE_META[value].color}>{ROLE_META[value].text}</Tag>,
    },
    {
      title: '状态',
      width: 130,
      render: (_, row) =>
        row.is_active ? (
          <Tag color="success">正常</Tag>
        ) : (
          <Tooltip title={row.disabled_reason ?? '未填写原因'}>
            <Tag color="error">已禁用</Tag>
          </Tooltip>
        ),
    },
    {
      title: '近 30 天',
      width: 210,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          资料 {row.counts.materials} · 笔记 {row.counts.notes} · AI {row.counts.ai_calls_30d} 次 ·{' '}
          {row.counts.study_minutes_30d} 分钟
        </Text>
      ),
    },
    {
      title: '注册 / 最后登录',
      width: 190,
      render: (_, row) => (
        <Flex vertical>
          <Text style={{ fontSize: 12 }}>{dayjs(row.created_at).format('YYYY-MM-DD HH:mm')}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.last_login_at ? dayjs(row.last_login_at).format('YYYY-MM-DD HH:mm') : '从未登录'}
          </Text>
        </Flex>
      ),
    },
    {
      title: '操作',
      width: 300,
      fixed: 'right',
      render: (_, row) => {
        const self = isSelf(row)
        return (
          <Space size={4} wrap>
            <Button size="small" type="link" onClick={() => setDetailId(row.id)}>
              详情
            </Button>

            {row.is_active ? (
              <Button
                size="small"
                type="link"
                danger
                icon={<StopOutlined />}
                disabled={self}
                title={self ? '不能禁用自己的账号' : undefined}
                onClick={() => {
                  form.resetFields()
                  setDisabling(row)
                }}
              >
                禁用
              </Button>
            ) : (
              <Button
                size="small"
                type="link"
                icon={<UnlockOutlined />}
                onClick={() => void handleEnable(row)}
              >
                启用
              </Button>
            )}

            <Popconfirm
              title={row.role === 'admin' ? '降为普通用户？' : '提升为管理员？'}
              description="角色变更后该用户的旧登录态会立即失效"
              okText="确认"
              cancelText="取消"
              disabled={self}
              onConfirm={() =>
                void handleRoleChange(row, row.role === 'admin' ? 'user' : 'admin')
              }
            >
              <Button
                size="small"
                type="link"
                icon={<UserOutlined />}
                disabled={self}
                title={self ? '不能修改自己的角色' : undefined}
              >
                {row.role === 'admin' ? '降权' : '提权'}
              </Button>
            </Popconfirm>

            <Popconfirm
              title="重置为随机密码？"
              description="旧密码立即失效，随机密码只显示一次"
              okText="重置"
              cancelText="取消"
              disabled={self}
              onConfirm={() => void handleReset(row)}
            >
              <Button
                size="small"
                type="link"
                icon={<KeyOutlined />}
                disabled={self}
                title={self ? '不能重置自己的密码' : undefined}
              >
                重置密码
              </Button>
            </Popconfirm>

            <Popconfirm
              title="强制该用户下线？"
              description="其所有设备的登录态立即失效"
              okText="下线"
              cancelText="取消"
              disabled={self}
              onConfirm={() => void handleRevoke(row)}
            >
              <Button
                size="small"
                type="link"
                icon={<LogoutOutlined />}
                disabled={self}
                title={self ? '不能强制自己下线' : undefined}
              >
                下线
              </Button>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex justify="space-between" align="flex-end" wrap gap={8}>
        <div>
          <Text strong style={{ fontSize: 16 }}>
            用户管理
          </Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            管理员不能禁用 / 降权 / 重置自己（防把系统锁死）；变更会立即让该用户的旧令牌失效
          </Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
      </Flex>

      <Card size="small">
        <Flex gap={8} wrap>
          <Input.Search
            allowClear
            placeholder="用户名 / 邮箱 / 昵称"
            style={{ width: 240 }}
            onSearch={(value) => {
              setPage(1)
              setKeyword(value || undefined)
            }}
          />
          <Select
            allowClear
            placeholder="角色"
            style={{ width: 130 }}
            value={role}
            onChange={(value) => {
              setPage(1)
              setRole(value)
            }}
            options={[
              { value: 'user', label: '普通用户' },
              { value: 'admin', label: '管理员' },
            ]}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 130 }}
            value={activeFilter}
            onChange={(value) => {
              setPage(1)
              setActiveFilter(value)
            }}
            options={[
              { value: true, label: '正常' },
              { value: false, label: '已禁用' },
            ]}
          />
          <Select
            style={{ width: 190 }}
            value={order}
            onChange={(value) => setOrder(value)}
            options={[
              { value: '-created_at', label: '注册时间（新→旧）' },
              { value: 'created_at', label: '注册时间（旧→新）' },
              { value: 'username', label: '用户名' },
              { value: '-last_login_at', label: '最后登录（新→旧）' },
            ]}
          />
        </Flex>
      </Card>

      <Table<AdminUserItemOut>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        scroll={{ x: 1200 }}
        pagination={{
          current: page,
          pageSize: size,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个用户`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
      />

      {/* 禁用（必填原因） */}
      <Modal
        open={Boolean(disabling)}
        title={`禁用 ${disabling?.username ?? ''}`}
        okText="确认禁用"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        confirmLoading={submitting}
        onCancel={() => setDisabling(null)}
        onOk={() => void handleDisable()}
        destroyOnHidden
      >
        <Text type="secondary">
          禁用后该用户的所有令牌立即失效，且登录时会看到这里填写的原因。
        </Text>
        <Form form={form} layout="vertical" requiredMark={false} style={{ marginTop: 12 }}>
          <Form.Item
            name="disabled_reason"
            label="禁用原因（会展示给用户）"
            rules={[{ required: true, message: '请填写禁用原因' }]}
          >
            <Input.TextArea rows={3} maxLength={200} showCount placeholder="例如：上传违规内容" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 临时密码（只显示一次） */}
      <Modal
        open={Boolean(resetResult)}
        title="已重置密码"
        okText="我已记下"
        onOk={() => setResetResult(null)}
        onCancel={() => setResetResult(null)}
        cancelButtonProps={{ style: { display: 'none' } }}
        destroyOnHidden
      >
        <Flex vertical gap={8}>
          <Text>
            用户 <Text strong>{resetResult?.username}</Text> 的临时密码：
          </Text>
          <Text code copyable style={{ fontSize: 18 }}>
            {resetResult?.password}
          </Text>
          <Text type="secondary">
            该密码只在这里出现一次（服务端不存明文），请线下告知用户，并提醒其登录后修改。
          </Text>
        </Flex>
      </Modal>

      {/* 详情 */}
      <Drawer
        open={Boolean(detailId)}
        size={520}
        title="用户详情"
        onClose={() => setDetailId(null)}
        destroyOnHidden
      >
        {detail ? (
          <Flex vertical gap={12}>
            <Descriptions
              column={1}
              size="small"
              items={[
                { key: 'username', label: '用户名', children: detail.username },
                { key: 'nickname', label: '昵称', children: detail.nickname ?? '—' },
                { key: 'email', label: '邮箱', children: detail.email },
                {
                  key: 'role',
                  label: '角色',
                  children: <Tag color={ROLE_META[detail.role].color}>{ROLE_META[detail.role].text}</Tag>,
                },
                {
                  key: 'active',
                  label: '状态',
                  children: detail.is_active ? (
                    <Tag color="success">正常</Tag>
                  ) : (
                    <Tag color="error">已禁用：{detail.disabled_reason ?? '未填写原因'}</Tag>
                  ),
                },
                {
                  key: 'created',
                  label: '注册时间',
                  children: dayjs(detail.created_at).format('YYYY-MM-DD HH:mm'),
                },
                {
                  key: 'login',
                  label: '最后登录',
                  children: detail.last_login_at
                    ? dayjs(detail.last_login_at).format('YYYY-MM-DD HH:mm')
                    : '从未登录',
                },
              ]}
            />
            <Descriptions
              column={2}
              size="small"
              title="近 30 天"
              items={[
                { key: 'materials', label: '资料', children: detail.counts.materials },
                { key: 'notes', label: '笔记', children: detail.counts.notes },
                { key: 'ai', label: 'AI 调用', children: `${detail.counts.ai_calls_30d} 次` },
                { key: 'tokens', label: 'AI token', children: detail.ai_tokens_30d },
                { key: 'minutes', label: '学习时长', children: `${detail.counts.study_minutes_30d} 分钟` },
                { key: 'quiz', label: '答题正确率', children: `${(detail.quiz_accuracy_30d * 100).toFixed(0)}%（${detail.quiz_attempts_30d} 次）` },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              管理端**不展示**用户笔记正文与题目答案（契约 §16.3/§16.7）。
            </Text>
          </Flex>
        ) : (
          <Text type="secondary">加载中…</Text>
        )}
      </Drawer>
    </Flex>
  )
}

export type { AdminUserDetailOut }
