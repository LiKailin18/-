import { DeleteOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  Flex,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'

import {
  deleteAdminMaterial,
  deleteAdminNote,
  deleteAdminQuiz,
  listAdminMaterials,
  listAdminNotes,
  listAdminQuizzes,
  reparseAdminMaterial,
} from '../../api/admin'
import { toApiError } from '../../api/client'
import type { AdminMaterialItemOut, AdminNoteItemOut, AdminQuizItemOut } from '../../types/api'

const { Text } = Typography

const PARSE_META: Record<string, { text: string; color: string }> = {
  pending: { text: '待解析', color: 'default' },
  parsing: { text: '解析中', color: 'processing' },
  success: { text: '成功', color: 'success' },
  failed: { text: '失败', color: 'error' },
  unsupported: { text: '扫描件', color: 'warning' },
}

/** 功能 13.3 内容管理：跨用户查看与下架资料 / 笔记 / 测试题。 */
export default function AdminContentPage() {
  return (
    <Flex vertical gap={12}>
      <div>
        <Text strong style={{ fontSize: 16 }}>
          内容管理
        </Text>
        <br />
        <Text type="secondary" style={{ fontSize: 12 }}>
          列表**不返回**笔记正文、题目与答案；下架是软删除，历史答卷与统计口径不受影响
        </Text>
      </div>

      <Card size="small">
        <Tabs
          defaultActiveKey="materials"
          destroyOnHidden
          items={[
            { key: 'materials', label: '学习资料', children: <MaterialsTab /> },
            { key: 'notes', label: '笔记', children: <NotesTab /> },
            { key: 'quizzes', label: '测试题', children: <QuizzesTab /> },
          ]}
        />
      </Card>
    </Flex>
  )
}

function MaterialsTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [keyword, setKeyword] = useState<string | undefined>()
  const [parseStatus, setParseStatus] = useState<string | undefined>()
  const [fileExt, setFileExt] = useState<string | undefined>()

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['admin-materials', page, size, keyword, parseStatus, fileExt],
    queryFn: () =>
      listAdminMaterials({
        page,
        size,
        keyword,
        parse_status: parseStatus,
        file_ext: fileExt,
      }),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-materials'] })
    await queryClient.invalidateQueries({ queryKey: ['admin-audit'] })
  }

  const handleDelete = async (row: AdminMaterialItemOut) => {
    try {
      await deleteAdminMaterial(row.id)
      message.success(`已下架「${row.title}」`)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleReparse = async (row: AdminMaterialItemOut) => {
    try {
      await reparseAdminMaterial(row.id)
      message.success(`已把「${row.title}」重新排队解析`)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<AdminMaterialItemOut>['columns'] = [
    { title: '标题', dataIndex: 'title', width: 200 },
    {
      title: '归属',
      width: 130,
      render: (_, row) => <Tag>{row.owner.username}</Tag>,
    },
    {
      title: '类型 / 大小',
      width: 140,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.file_ext} · {(row.size_bytes / 1024).toFixed(0)} KB
        </Text>
      ),
    },
    {
      title: '解析状态',
      width: 120,
      render: (_, row) => {
        const meta = PARSE_META[row.parse_status] ?? {
          text: row.parse_status,
          color: 'default',
        }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '字数',
      width: 100,
      render: (_, row) => row.char_count ?? '—',
    },
    {
      title: '创建时间',
      width: 160,
      render: (_, row) => dayjs(row.created_at).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      width: 190,
      fixed: 'right',
      render: (_, row) => (
        <Space size={4} wrap>
          <Popconfirm
            title="重新解析这份资料？"
            description="会清空解析结果并重新排队（异步执行）"
            okText="重新解析"
            cancelText="取消"
            onConfirm={() => void handleReparse(row)}
          >
            <Button size="small" type="link" icon={<SyncOutlined />}>
              重新解析
            </Button>
          </Popconfirm>
          <Popconfirm
            title="下架这份资料？"
            description="软删除 + 删除磁盘文件，用户端不再可见"
            okText="下架"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={() => void handleDelete(row)}
          >
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>
              下架
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap>
        <Input.Search
          allowClear
          placeholder="标题关键词"
          style={{ width: 220 }}
          onSearch={(value) => {
            setPage(1)
            setKeyword(value || undefined)
          }}
        />
        <Select
          allowClear
          placeholder="解析状态"
          style={{ width: 140 }}
          value={parseStatus}
          onChange={(value) => {
            setPage(1)
            setParseStatus(value)
          }}
          options={Object.entries(PARSE_META).map(([value, meta]) => ({ value, label: meta.text }))}
        />
        <Select
          allowClear
          placeholder="文件类型"
          style={{ width: 130 }}
          value={fileExt}
          onChange={(value) => {
            setPage(1)
            setFileExt(value)
          }}
          options={[
            { value: '.pdf', label: 'PDF' },
            { value: '.docx', label: 'Word' },
          ]}
        />
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
      </Flex>

      <Table<AdminMaterialItemOut>
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
          showTotal: (total) => `共 ${total} 份资料`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
      />
    </Flex>
  )
}

function NotesTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [keyword, setKeyword] = useState<string | undefined>()

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['admin-notes', page, size, keyword],
    queryFn: () => listAdminNotes({ page, size, keyword }),
  })

  const handleDelete = async (row: AdminNoteItemOut) => {
    try {
      await deleteAdminNote(row.id)
      message.success(`已删除「${row.title}」`)
      await queryClient.invalidateQueries({ queryKey: ['admin-notes'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-audit'] })
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<AdminNoteItemOut>['columns'] = [
    { title: '标题', dataIndex: 'title', width: 200 },
    {
      title: '摘要',
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.excerpt}
          {row.excerpt.length >= 120 ? '…' : ''}
        </Text>
      ),
    },
    { title: '归属', width: 130, render: (_, row) => <Tag>{row.owner.username}</Tag> },
    {
      title: '标签',
      width: 160,
      render: (_, row) =>
        row.tags.length ? row.tags.map((tag) => <Tag key={tag}>{tag}</Tag>) : '—',
    },
    {
      title: '更新时间',
      width: 160,
      render: (_, row) => dayjs(row.updated_at).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      width: 100,
      fixed: 'right',
      render: (_, row) => (
        <Popconfirm
          title="删除这条笔记？"
          okText="删除"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={() => void handleDelete(row)}
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
      <Flex gap={8} wrap>
        <Input.Search
          allowClear
          placeholder="标题 / 正文关键词"
          style={{ width: 240 }}
          onSearch={(value) => {
            setPage(1)
            setKeyword(value || undefined)
          }}
        />
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
      </Flex>

      <Table<AdminNoteItemOut>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        scroll={{ x: 1000 }}
        pagination={{
          current: page,
          pageSize: size,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条笔记`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
      />
    </Flex>
  )
}

function QuizzesTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['admin-quizzes', page, size],
    queryFn: () => listAdminQuizzes({ page, size }),
  })

  const handleDelete = async (row: AdminQuizItemOut) => {
    try {
      await deleteAdminQuiz(row.id)
      message.success(`已下架「${row.title}」（历史答卷保留）`)
      await queryClient.invalidateQueries({ queryKey: ['admin-quizzes'] })
      await queryClient.invalidateQueries({ queryKey: ['admin-audit'] })
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<AdminQuizItemOut>['columns'] = [
    { title: '标题', dataIndex: 'title', width: 220 },
    { title: '归属', width: 130, render: (_, row) => <Tag>{row.owner.username}</Tag> },
    {
      title: '题数 / 题型',
      width: 200,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.question_count} 题 · {row.types.join('/') || '—'}
        </Text>
      ),
    },
    { title: '难度', dataIndex: 'difficulty', width: 100 },
    {
      title: '创建时间',
      width: 160,
      render: (_, row) => dayjs(row.created_at).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      width: 100,
      fixed: 'right',
      render: (_, row) => (
        <Popconfirm
          title="下架这套题？"
          description="用户不能再做它，但历史答卷仍计入统计"
          okText="下架"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={() => void handleDelete(row)}
        >
          <Button size="small" type="link" danger icon={<DeleteOutlined />}>
            下架
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap>
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          列表不含题目与答案（管理端不需要看答案，少一个泄露面）
        </Text>
      </Flex>

      <Table<AdminQuizItemOut>
        rowKey="id"
        size="small"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isFetching}
        scroll={{ x: 1000 }}
        pagination={{
          current: page,
          pageSize: size,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 套题`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage)
            setSize(nextSize)
          },
        }}
      />
    </Flex>
  )
}
