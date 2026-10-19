import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  DatePicker,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'

import { toApiError } from '../../api/client'
import { listMaterials } from '../../api/materials'
import { createPlan, deletePlan, generateTasks, listPlans, updatePlan } from '../../api/plans'
import type { PlanOut, PlanStatus } from '../../types/api'

const { Text } = Typography

const STATUS_META: Record<PlanStatus, { text: string; color: string }> = {
  draft: { text: '草稿', color: 'default' },
  active: { text: '进行中', color: 'processing' },
  done: { text: '已完成', color: 'success' },
  archived: { text: '已归档', color: 'default' },
}

interface PlanForm {
  title: string
  subject?: string
  goal?: string
  range: [import('dayjs').Dayjs, import('dayjs').Dayjs]
  daily_minutes: number
  material_ids?: string[]
}

/** 学习计划（功能 5）：CRUD + 幂等生成每日任务。 */
export default function PlanTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<PlanOut | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<PlanForm>()

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['plans', page, size, statusFilter],
    queryFn: () => listPlans({ page, size, status: statusFilter }),
  })

  // 关联资料下拉（一次取前 100 份足够）
  const { data: materialPage } = useQuery({
    queryKey: ['materials', 'options'],
    queryFn: () => listMaterials({ page: 1, size: 100 }),
  })
  const materialOptions = (materialPage?.items ?? []).map((item) => ({
    value: item.id,
    label: item.title,
  }))

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['plans'] })

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ daily_minutes: 60 })
    setOpen(true)
  }

  const openEdit = (record: PlanOut) => {
    setEditing(record)
    form.setFieldsValue({
      title: record.title,
      subject: record.subject ?? undefined,
      goal: record.goal ?? undefined,
      daily_minutes: record.daily_minutes,
      material_ids: record.material_ids,
    })
    setOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (editing) {
        await updatePlan(editing.id, {
          title: values.title,
          subject: values.subject || null,
          goal: values.goal || null,
          daily_minutes: values.daily_minutes,
          material_ids: values.material_ids ?? [],
        })
        message.success('已保存')
      } else {
        await createPlan({
          title: values.title,
          subject: values.subject || null,
          goal: values.goal || null,
          start_date: values.range[0].format('YYYY-MM-DD'),
          end_date: values.range[1].format('YYYY-MM-DD'),
          daily_minutes: values.daily_minutes,
          material_ids: values.material_ids ?? [],
        })
        message.success('已创建计划，可以生成每日任务了')
      }
      setOpen(false)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleGenerate = async (record: PlanOut, overwrite = false) => {
    try {
      const result = await generateTasks(record.id, overwrite)
      message.success(`已生成 ${result.created} 条任务，跳过 ${result.skipped} 天`)
      await refresh()
    } catch (error) {
      // 409 PLAN_001 表示「已全部生成」，用 warning 更贴切
      message.warning(toApiError(error).message)
    }
  }

  const handleDelete = async (record: PlanOut) => {
    try {
      await deletePlan(record.id)
      message.success('已删除（未完成的任务一并移除，已完成的保留用于统计）')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<PlanOut>['columns'] = [
    {
      title: '计划',
      dataIndex: 'title',
      render: (title: string, record) => (
        <Space orientation="vertical" size={2}>
          <Text strong>{title}</Text>
          {record.goal && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              目标：{record.goal}
            </Text>
          )}
        </Space>
      ),
    },
    { title: '科目', dataIndex: 'subject', width: 100, render: (v) => v || '—' },
    {
      title: '区间',
      width: 200,
      render: (_, record) => `${record.start_date} ~ ${record.end_date}`,
    },
    {
      title: '每日',
      dataIndex: 'daily_minutes',
      width: 90,
      render: (v: number) => `${v} 分钟`,
    },
    {
      title: '进度',
      width: 160,
      render: (_, record) => (
        <Space orientation="vertical" size={0} style={{ width: '100%' }}>
          <Progress percent={Math.round(record.progress.progress * 100)} size="small" />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.progress.task_done}/{record.progress.task_total} 个任务
          </Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: PlanStatus) => (
        <Tag color={STATUS_META[value].color}>{STATUS_META[value].text}</Tag>
      ),
    },
    {
      title: '操作',
      width: 260,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button
            size="small"
            type="link"
            icon={<ThunderboltOutlined />}
            onClick={() => void handleGenerate(record)}
          >
            生成任务
          </Button>
          <Popconfirm
            title="重建每日任务？"
            description="未完成的任务会被替换，已完成的保留。"
            okText="重建"
            cancelText="取消"
            onConfirm={() => void handleGenerate(record, true)}
          >
            <Button size="small" type="link">
              重建
            </Button>
          </Popconfirm>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="删除这个计划？"
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => void handleDelete(record)}
          >
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex justify="space-between" wrap gap={8}>
        <Space>
          <Select
            allowClear
            placeholder="计划状态"
            style={{ width: 140 }}
            value={statusFilter}
            onChange={(value) => {
              setPage(1)
              setStatusFilter(value)
            }}
            options={Object.entries(STATUS_META).map(([value, meta]) => ({
              value,
              label: meta.text,
            }))}
          />
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
            刷新
          </Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建计划
        </Button>
      </Flex>

      <Table<PlanOut>
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        scroll={{ x: 1000 }}
        pagination={{
          current: page,
          pageSize: size,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个计划`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
        locale={{ emptyText: '还没有计划，先新建一个' }}
      />

      <Modal
        open={open}
        title={editing ? '编辑计划' : '新建计划'}
        onCancel={() => setOpen(false)}
        onOk={() => void submit()}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form<PlanForm> form={form} layout="vertical" requiredMark={false}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={200} placeholder="例如：高数期末冲刺" />
          </Form.Item>

          <Form.Item name="subject" label="科目">
            <Input maxLength={64} placeholder="用于统计，如：高数" />
          </Form.Item>

          {!editing && (
            <Form.Item name="range" label="计划区间" rules={[{ required: true, message: '请选择区间' }]}>
              <DatePicker.RangePicker style={{ width: '100%' }} />
            </Form.Item>
          )}

          <Form.Item
            name="daily_minutes"
            label="每日目标（分钟）"
            rules={[{ required: true, message: '请输入每日目标' }]}
          >
            <InputNumber min={1} max={600} style={{ width: 160 }} />
          </Form.Item>

          <Form.Item name="goal" label="学习目标">
            <Input.TextArea rows={2} maxLength={500} showCount placeholder="例如：期末 85+" />
          </Form.Item>

          <Form.Item name="material_ids" label="关联资料">
            <Select
              mode="multiple"
              allowClear
              placeholder="可选，用于把计划与资料关联起来"
              options={materialOptions}
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </Modal>
    </Flex>
  )
}
