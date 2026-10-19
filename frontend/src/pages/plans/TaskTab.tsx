import { CheckOutlined, DeleteOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
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
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import type { Dayjs } from 'dayjs'
import { useState } from 'react'

import { toApiError } from '../../api/client'
import { listPlans } from '../../api/plans'
import { completeTask, deleteTask, listTasks, updateTask } from '../../api/tasks'
import type { TaskOut, TaskStatus } from '../../types/api'

const { Text } = Typography

const STATUS_META: Record<TaskStatus, { text: string; color: string }> = {
  pending: { text: '待完成', color: 'default' },
  doing: { text: '进行中', color: 'processing' },
  done: { text: '已完成', color: 'success' },
  skipped: { text: '已跳过', color: 'warning' },
}

interface CompleteForm {
  duration_minutes: number
  content?: string
}

/** 每日任务（功能 6）：筛选、完成（自动记学习记录）、跳过、删除。 */
export default function TaskTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [planFilter, setPlanFilter] = useState<string | undefined>()

  const [completing, setCompleting] = useState<TaskOut | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<CompleteForm>()

  const dateFrom = range?.[0]?.format('YYYY-MM-DD')
  const dateTo = range?.[1]?.format('YYYY-MM-DD')

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['tasks', page, size, statusFilter, planFilter, dateFrom, dateTo],
    queryFn: () =>
      listTasks({
        page,
        size,
        status: statusFilter,
        plan_id: planFilter,
        date_from: dateFrom,
        date_to: dateTo,
      }),
  })

  const { data: planPage } = useQuery({
    queryKey: ['plans', 'options'],
    queryFn: () => listPlans({ page: 1, size: 100 }),
  })
  const planOptions = (planPage?.items ?? []).map((plan) => ({
    value: plan.id,
    label: plan.title,
  }))
  const planTitle = (id: string | null) =>
    planOptions.find((option) => option.value === id)?.label ?? '—'

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
      queryClient.invalidateQueries({ queryKey: ['plans'] }),
      queryClient.invalidateQueries({ queryKey: ['records'] }),
    ])

  const openComplete = (task: TaskOut) => {
    setCompleting(task)
    form.setFieldsValue({ duration_minutes: task.est_minutes, content: '' })
  }

  const submitComplete = async () => {
    if (!completing) return
    const values = await form.validateFields()
    setSaving(true)
    try {
      const result = await completeTask(completing.id, {
        duration_minutes: values.duration_minutes,
        content: values.content || null,
      })
      message.success(
        result.study_record_id ? `已完成，并记入 ${values.duration_minutes} 分钟学习时长` : '已完成',
      )
      setCompleting(null)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = async (task: TaskOut) => {
    try {
      await updateTask(task.id, { status: 'skipped' })
      message.success('已跳过（不计入完成率）')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleDelete = async (task: TaskOut) => {
    try {
      await deleteTask(task.id)
      message.success('已删除')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<TaskOut>['columns'] = [
    { title: '日期', dataIndex: 'plan_date', width: 120 },
    {
      title: '任务',
      dataIndex: 'title',
      render: (title: string, record) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{title}</Text>
          {record.description && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.description}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '所属计划',
      width: 180,
      render: (_, record) => planTitle(record.plan_id),
    },
    {
      title: '预估',
      dataIndex: 'est_minutes',
      width: 90,
      render: (value: number) => `${value} 分钟`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (value: TaskStatus) => (
        <Tag color={STATUS_META[value].color}>{STATUS_META[value].text}</Tag>
      ),
    },
    {
      title: '操作',
      width: 200,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button
            size="small"
            type="link"
            icon={<CheckOutlined />}
            disabled={record.status === 'done'}
            onClick={() => openComplete(record)}
          >
            完成
          </Button>
          <Button
            size="small"
            type="link"
            icon={<StopOutlined />}
            disabled={record.status === 'skipped' || record.status === 'done'}
            onClick={() => void handleSkip(record)}
          >
            跳过
          </Button>
          <Popconfirm
            title="删除这个任务？"
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
      <Flex gap={8} wrap>
        <DatePicker.RangePicker onChange={(value) => { setPage(1); setRange(value) }} />
        <Select
          allowClear
          placeholder="任务状态"
          style={{ width: 140 }}
          value={statusFilter}
          onChange={(value) => {
            setPage(1)
            setStatusFilter(value)
          }}
          options={Object.entries(STATUS_META).map(([value, meta]) => ({ value, label: meta.text }))}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="所属计划"
          style={{ width: 200 }}
          value={planFilter}
          onChange={(value) => {
            setPage(1)
            setPlanFilter(value)
          }}
          options={planOptions}
        />
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
      </Flex>

      <Table<TaskOut>
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        scroll={{ x: 900 }}
        pagination={{
          current: page,
          pageSize: size,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 个任务`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
        locale={{ emptyText: '没有符合条件的任务（去「计划」页生成每日任务）' }}
      />

      <Modal
        open={Boolean(completing)}
        title="完成任务"
        onCancel={() => setCompleting(null)}
        onOk={() => void submitComplete()}
        okText="确认完成"
        cancelText="取消"
        confirmLoading={saving}
        destroyOnHidden
      >
        <Text type="secondary">
          完成会同时写入一条学习记录（用于统计与推荐），时长请按实际填写。
        </Text>
        <Form<CompleteForm> form={form} layout="vertical" requiredMark={false} style={{ marginTop: 12 }}>
          <Form.Item
            name="duration_minutes"
            label="本次学习时长（分钟）"
            rules={[{ required: true, message: '请输入时长' }]}
          >
            <InputNumber min={1} max={1440} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="content" label="备注（可选）">
            <Input.TextArea rows={3} maxLength={500} showCount placeholder="例如：看完第一章并做完例题" />
          </Form.Item>
        </Form>
      </Modal>
    </Flex>
  )
}
