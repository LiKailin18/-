import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
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
} from 'antd'
import type { TableProps } from 'antd'
import type { Dayjs } from 'dayjs'
import { useState } from 'react'

import { toApiError } from '../../api/client'
import { createRecord, deleteRecord, listRecords } from '../../api/records'
import type { RecordOut, RecordType } from '../../types/api'

const TYPE_META: Record<RecordType, { text: string; color: string }> = {
  reading: { text: '阅读', color: 'blue' },
  video: { text: '视频', color: 'purple' },
  practice: { text: '练习', color: 'green' },
  review: { text: '复习', color: 'orange' },
  other: { text: '其他', color: 'default' },
}

interface RecordForm {
  type: RecordType
  started_at: Dayjs
  duration_minutes: number
  content?: string
}

/** 学习记录（功能 12）：手动补记 + 查看 + 删除。任务完成产生的记录也会出现在这里。 */
export default function RecordTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [typeFilter, setTypeFilter] = useState<string | undefined>()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<RecordForm>()

  const dateFrom = range?.[0]?.format('YYYY-MM-DD')
  const dateTo = range?.[1]?.format('YYYY-MM-DD')

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['records', page, size, typeFilter, dateFrom, dateTo],
    queryFn: () => listRecords({ page, size, type: typeFilter, date_from: dateFrom, date_to: dateTo }),
  })

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['records'] }),
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
    ])

  const openCreate = () => {
    form.resetFields()
    form.setFieldsValue({ type: 'reading', duration_minutes: 30 })
    setOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await createRecord({
        type: values.type,
        // 后端存 UTC，这里按本地时间转成带偏移的 ISO 字符串
        started_at: values.started_at.toISOString(),
        duration_minutes: values.duration_minutes,
        content: values.content || null,
      })
      message.success('已记录')
      setOpen(false)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (record: RecordOut) => {
    try {
      await deleteRecord(record.id)
      message.success('已删除')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<RecordOut>['columns'] = [
    {
      title: '学习时间',
      dataIndex: 'started_at',
      width: 190,
      render: (value: string) => new Date(value).toLocaleString('zh-CN'),
    },
    {
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (value: RecordType) => (
        <Tag color={TYPE_META[value].color}>{TYPE_META[value].text}</Tag>
      ),
    },
    {
      title: '时长',
      dataIndex: 'duration_minutes',
      width: 100,
      render: (value: number) => `${value} 分钟`,
    },
    {
      title: '内容',
      dataIndex: 'content',
      render: (value: string | null) => value || '—',
    },
    {
      title: '来源',
      width: 110,
      render: (_, record) =>
        record.task_id ? <Tag color="cyan">任务完成</Tag> : <Tag>手动记录</Tag>,
    },
    {
      title: '操作',
      width: 90,
      render: (_, record) => (
        <Popconfirm
          title="删除这条学习记录？"
          description="会同时影响统计数据。"
          okText="删除"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={() => void handleDelete(record)}
        >
          <Button size="small" type="link" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex justify="space-between" wrap gap={8}>
        <Space wrap>
          <DatePicker.RangePicker onChange={(value) => { setPage(1); setRange(value) }} />
          <Select
            allowClear
            placeholder="学习类型"
            style={{ width: 140 }}
            value={typeFilter}
            onChange={(value) => {
              setPage(1)
              setTypeFilter(value)
            }}
            options={Object.entries(TYPE_META).map(([value, meta]) => ({ value, label: meta.text }))}
          />
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
            刷新
          </Button>
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          补记学习记录
        </Button>
      </Flex>

      <Table<RecordOut>
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
          showTotal: (total) => `共 ${total} 条`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
        locale={{ emptyText: '还没有学习记录：完成任务会自动记录，也可以手动补记' }}
      />

      <Modal
        open={open}
        title="补记学习记录"
        onCancel={() => setOpen(false)}
        onOk={() => void submit()}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form<RecordForm> form={form} layout="vertical" requiredMark={false}>
          <Form.Item name="type" label="学习类型" rules={[{ required: true }]}>
            <Select
              options={Object.entries(TYPE_META).map(([value, meta]) => ({
                value,
                label: meta.text,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="started_at"
            label="开始时间"
            rules={[{ required: true, message: '请选择开始时间' }]}
          >
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="duration_minutes"
            label="时长（分钟）"
            rules={[{ required: true, message: '请输入时长' }]}
          >
            <InputNumber min={1} max={1440} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="content" label="学了什么">
            <Input.TextArea rows={3} maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </Flex>
  )
}
