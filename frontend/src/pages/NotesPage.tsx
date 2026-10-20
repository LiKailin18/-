import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  Drawer,
  Flex,
  Form,
  Input,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'

import { toApiError } from '../api/client'
import { createNote, deleteNote, getNote, listNotes, updateNote } from '../api/notes'
import type { NoteListItem } from '../types/api'

const { Paragraph, Text, Title } = Typography

interface NoteForm {
  title: string
  tags: string
  content: string
}

/** 在线笔记（功能 4）：列表 + 搜索 + 抽屉式编辑器。 */
export default function NotesPage() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [keyword, setKeyword] = useState('')

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [form] = Form.useForm<NoteForm>()

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['notes', page, size, keyword],
    queryFn: () => listNotes({ page, size, keyword: keyword || undefined }),
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['notes'] })

  const openCreate = () => {
    setEditingId(null)
    setEditorOpen(true)
  }

  const openEdit = (record: NoteListItem) => {
    setEditingId(record.id)
    setEditorOpen(true)
  }

  /** 抽屉挂载完成后再回填表单 —— 否则 useForm 还没连上 Form 组件 */
  const handleAfterOpen = async (open: boolean) => {
    if (!open || !editingId) return
    setLoadingDetail(true)
    try {
      // 列表里只有 excerpt，正文必须单独取详情
      const detail = await getNote(editingId)
      form.setFieldsValue({
        title: detail.title,
        tags: detail.tags.join(','),
        content: detail.content,
      })
    } catch (error) {
      message.error(toApiError(error).message)
      setEditorOpen(false)
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    const payload = {
      title: values.title,
      content: values.content ?? '',
      tags: values.tags
        ? values.tags
            .split(',')
            .map((tag) => tag.trim())
            .filter(Boolean)
        : [],
    }
    setSaving(true)
    try {
      if (editingId) {
        await updateNote(editingId, payload)
        message.success('已保存')
      } else {
        await createNote(payload)
        message.success('已新建笔记')
      }
      setEditorOpen(false)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (record: NoteListItem) => {
    try {
      await deleteNote(record.id)
      message.success('已删除')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<NoteListItem>['columns'] = [
    {
      title: '标题',
      dataIndex: 'title',
      width: 220,
      render: (title: string, record) => (
        <Space orientation="vertical" size={2}>
          <Text strong>{title}</Text>
          <Space size={4} wrap>
            {record.tags.map((tag) => (
              <Tag key={tag} color="geekblue">
                {tag}
              </Tag>
            ))}
            {record.material_id && <Tag color="cyan">关联资料</Tag>}
          </Space>
        </Space>
      ),
    },
    {
      title: '摘要',
      dataIndex: 'excerpt',
      render: (excerpt: string) => (
        <Text type="secondary" style={{ fontSize: 13 }}>
          {excerpt || '（空笔记）'}
        </Text>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 170,
      render: (value: string) => new Date(value).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      width: 150,
      render: (_, record) => (
        <Space size={4}>
          <Button
            size="small"
            type="link"
            icon={<EditOutlined />}
            onClick={() => void openEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="删除这条笔记？"
            description="删除后不可恢复。"
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
    <Flex vertical gap={16} style={{ maxWidth: 1280, margin: '0 auto', width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          在线笔记
        </Title>
        <Text type="secondary">支持标题与正文的模糊搜索；列表只显示摘要，正文在编辑器中查看</Text>
      </div>

      <Card
        title="我的笔记"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建笔记
            </Button>
          </Space>
        }
      >
        <Input.Search
          allowClear
          placeholder="搜索标题或正文"
          style={{ width: 320, marginBottom: 12 }}
          onSearch={(value) => {
            setPage(1)
            setKeyword(value)
          }}
        />

        <Table<NoteListItem>
          rowKey="id"
          columns={columns}
          dataSource={data?.items ?? []}
          loading={isFetching}
          scroll={{ x: 800 }}
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
          locale={{ emptyText: '还没有笔记，点右上角新建一条' }}
        />
      </Card>

      <Drawer
        open={editorOpen}
        title={editingId ? '编辑笔记' : '新建笔记'}
        size={640}
        destroyOnHidden
        afterOpenChange={(open) => void handleAfterOpen(open)}
        onClose={() => setEditorOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setEditorOpen(false)}>取消</Button>
            <Button type="primary" loading={saving} disabled={loadingDetail} onClick={() => void handleSave()}>
              保存
            </Button>
          </Space>
        }
      >
        <Form<NoteForm>
          form={form}
          layout="vertical"
          requiredMark={false}
          initialValues={{ title: '', tags: '', content: '' }}
        >
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input maxLength={200} showCount placeholder="例如：极限的两种定义" />
          </Form.Item>

          <Form.Item name="tags" label="标签（逗号分隔）">
            <Input placeholder="高数,极限" maxLength={200} />
          </Form.Item>

          <Form.Item name="content" label="正文">
            <Input.TextArea
              rows={16}
              maxLength={100_000}
              showCount
              placeholder="支持 Markdown 文本"
            />
          </Form.Item>
        </Form>

        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
          正文上限 10 万字；列表页只返回 120 字摘要，避免大字段拖慢列表。
        </Paragraph>
      </Drawer>
    </Flex>
  )
}
