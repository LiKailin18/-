import { EditOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  DatePicker,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'

import { listAuditLogs, listSettings, updateSettings } from '../../api/admin'
import { toApiError } from '../../api/client'
import type { AuditLogOut, SettingItemOut } from '../../types/api'

const { Text } = Typography

const TARGET_LABEL: Record<string, string> = {
  user: '用户',
  material: '资料',
  note: '笔记',
  quiz: '测试题',
  setting: '配置',
  system: '系统',
}

const ACTION_LABEL: Record<string, string> = {
  'user.disable': '禁用用户',
  'user.enable': '启用用户',
  'user.role_change': '修改角色',
  'user.reset_password': '重置密码',
  'user.revoke_tokens': '强制下线',
  'material.delete': '下架资料',
  'material.reparse': '重新解析资料',
  'note.delete': '删除笔记',
  'quiz.delete': '下架测试题',
  'setting.update': '修改配置',
}

/** 功能 13.5 系统配置 + 操作审计。 */
export default function AdminSettingsPage() {
  return (
    <Flex vertical gap={12}>
      <div>
        <Text strong style={{ fontSize: 16 }}>
          系统配置与审计
        </Text>
        <br />
        <Text type="secondary" style={{ fontSize: 12 }}>
          配置改完立即生效（写后即清缓存）；审计日志只增不改不删
        </Text>
      </div>

      <Card size="small">
        <Tabs
          defaultActiveKey="settings"
          destroyOnHidden
          items={[
            { key: 'settings', label: '系统配置', children: <SettingsTab /> },
            { key: 'audit', label: '操作审计', children: <AuditTab /> },
          ]}
        />
      </Card>
    </Flex>
  )
}

function SettingsTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<SettingItemOut | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<{ value: unknown }>()

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['admin-settings'],
    queryFn: listSettings,
  })

  const openEdit = (row: SettingItemOut) => {
    form.setFieldsValue({ value: row.value })
    setEditing(row)
  }

  const handleSave = async () => {
    if (!editing) return
    const values = await form.validateFields()
    setSaving(true)
    try {
      await updateSettings([{ key: editing.key, value: values.value }])
      message.success('已保存并立即生效')
      setEditing(null)
      await queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-audit'] })
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSaving(false)
    }
  }

  const columns: TableProps<SettingItemOut>['columns'] = [
    { title: '配置项', dataIndex: 'key', width: 190 },
    {
      title: '当前值',
      width: 150,
      render: (_, row) => {
        if (row.value_type === 'bool') {
          return <Tag color={row.value ? 'success' : 'error'}>{row.value ? '开启' : '关闭'}</Tag>
        }
        return <Text strong>{String(row.value)}</Text>
      },
    },
    {
      title: '类型',
      dataIndex: 'value_type',
      width: 90,
    },
    { title: '说明', dataIndex: 'description' },
    {
      title: '最后修改',
      width: 200,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.updated_at ? dayjs(row.updated_at).format('YYYY-MM-DD HH:mm') : '—'}
          {row.updated_by_username ? ` · ${row.updated_by_username}` : ''}
        </Text>
      ),
    },
    {
      title: '操作',
      width: 100,
      render: (_, row) =>
        row.editable ? (
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(row)}>
            修改
          </Button>
        ) : (
          <Tag>只读</Tag>
        ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} align="center" wrap>
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          模型名是只读展示位（改模型走后端 .env + 重启），避免历史数据的 model 字段无法解释
        </Text>
      </Flex>

      <Table<SettingItemOut>
        rowKey="key"
        size="small"
        columns={columns}
        dataSource={data ?? []}
        loading={isFetching}
        pagination={false}
      />

      <Modal
        open={Boolean(editing)}
        title={`修改 ${editing?.key ?? ''}`}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        onCancel={() => setEditing(null)}
        onOk={() => void handleSave()}
        destroyOnHidden
      >
        <Text type="secondary">{editing?.description}</Text>
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="value" label="新值" valuePropName={editing?.value_type === 'bool' ? 'checked' : 'value'}>
            {editing?.value_type === 'bool' ? (
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            ) : editing?.value_type === 'int' ? (
              <InputNumber min={1} max={10000} style={{ width: 200 }} />
            ) : (
              <Input style={{ width: 320 }} />
            )}
          </Form.Item>
        </Form>
      </Modal>
    </Flex>
  )
}

function AuditTab() {
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [action, setAction] = useState<string | undefined>()
  const [targetType, setTargetType] = useState<string | undefined>()
  const [range, setRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)

  const { data, isFetching, refetch } = useQuery({
    queryKey: [
      'admin-audit',
      page,
      size,
      action,
      targetType,
      range?.[0]?.format('YYYY-MM-DD'),
      range?.[1]?.format('YYYY-MM-DD'),
    ],
    queryFn: () =>
      listAuditLogs({
        page,
        size,
        action,
        target_type: targetType,
        date_from: range?.[0]?.format('YYYY-MM-DD'),
        date_to: range?.[1]?.format('YYYY-MM-DD'),
      }),
  })

  const columns: TableProps<AuditLogOut>['columns'] = [
    {
      title: '时间',
      width: 170,
      render: (_, row) => dayjs(row.created_at).format('YYYY-MM-DD HH:mm:ss'),
    },
    { title: '管理员', width: 130, render: (_, row) => <Tag>{row.admin?.username ?? '—'}</Tag> },
    {
      title: '动作',
      width: 150,
      render: (_, row) => (
        <Space size={4}>
          <Text>{ACTION_LABEL[row.action] ?? row.action}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.action}
          </Text>
        </Space>
      ),
    },
    {
      title: '对象',
      width: 130,
      render: (_, row) => (
        <Text type="secondary">
          {TARGET_LABEL[row.target_type] ?? row.target_type}
          {row.target_id ? ` · ${row.target_id.slice(0, 8)}` : ''}
        </Text>
      ),
    },
    {
      title: '变更快照',
      render: (_, row) => (
        <Text code style={{ fontSize: 12 }}>
          {JSON.stringify(row.detail)}
        </Text>
      ),
    },
    { title: 'IP', dataIndex: 'ip', width: 130 },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap>
        <Select
          allowClear
          placeholder="动作"
          style={{ width: 190 }}
          value={action}
          onChange={(value) => {
            setPage(1)
            setAction(value)
          }}
          options={Object.entries(ACTION_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <Select
          allowClear
          placeholder="对象类型"
          style={{ width: 140 }}
          value={targetType}
          onChange={(value) => {
            setPage(1)
            setTargetType(value)
          }}
          options={Object.entries(TARGET_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <DatePicker.RangePicker
          onChange={(value) => {
            setPage(1)
            setRange(value)
          }}
        />
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
      </Flex>

      <Table<AuditLogOut>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        scroll={{ x: 1100 }}
        pagination={{
          current: page,
          pageSize: size,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条记录`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
      />
    </Flex>
  )
}
