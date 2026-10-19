import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FileTextOutlined,
  InboxOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
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
  Typography,
  Upload,
} from 'antd'
import type { TableProps, UploadProps } from 'antd'
import { useRef, useState } from 'react'

import { toApiError } from '../api/client'
import {
  deleteMaterial,
  downloadMaterial,
  listMaterials,
  readMaterialText,
  reparseMaterial,
  updateMaterial,
  uploadMaterial,
} from '../api/materials'
import type { MaterialOut, ParseStatus } from '../types/api'

const { Paragraph, Text, Title } = Typography

const STATUS_META: Record<ParseStatus, { text: string; color: string }> = {
  pending: { text: '排队中', color: 'blue' },
  parsing: { text: '解析中', color: 'blue' },
  success: { text: '已就绪', color: 'green' },
  failed: { text: '解析失败', color: 'red' },
  unsupported: { text: '扫描版不支持', color: 'orange' },
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 学习资料管理（功能 3）：上传 → 后台解析 → 列表/预览/下载/重解析/删除。 */
export default function MaterialsPage() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | undefined>()

  // 上传时可选填的元信息
  const [subject, setSubject] = useState('')
  const [tags, setTags] = useState('')

  const [editing, setEditing] = useState<MaterialOut | null>(null)
  const [editForm] = Form.useForm<{ title: string; subject?: string; tags?: string }>()

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewTitle, setPreviewTitle] = useState('')
  const [previewText, setPreviewText] = useState('')
  const [previewTotal, setPreviewTotal] = useState(0)
  const [previewHasMore, setPreviewHasMore] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const previewId = useRef<string | null>(null)

  const pollCount = useRef(0)

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['materials', page, size, keyword, statusFilter],
    queryFn: () =>
      listMaterials({ page, size, keyword: keyword || undefined, parse_status: statusFilter }),
    // 只要还有 pending/parsing 的资料就每 2 秒刷新一次（契约要求最多 30 次）
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const stillParsing = items.some(
        (item) => item.parse_status === 'pending' || item.parse_status === 'parsing',
      )
      if (!stillParsing) {
        pollCount.current = 0
        return false
      }
      pollCount.current += 1
      return pollCount.current > 30 ? false : 2000
    },
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['materials'] })

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: '.pdf,.docx',
    showUploadList: false,
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        const created = await uploadMaterial(file as File, {
          subject: subject || undefined,
          tags: tags || undefined,
        })
        onSuccess?.(created)
        message.success(`已上传「${created.title}」，正在后台解析…`)
        await refresh()
      } catch (error) {
        onError?.(error as Error)
        message.error(toApiError(error).message)
      }
    },
  }

  const openPreview = async (record: MaterialOut) => {
    previewId.current = record.id
    setPreviewTitle(record.title)
    setPreviewOpen(true)
    setPreviewLoading(true)
    try {
      const chunk = await readMaterialText(record.id, 0, 4000)
      setPreviewText(chunk.text)
      setPreviewTotal(chunk.total_chars)
      setPreviewHasMore(chunk.has_more)
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const loadMoreText = async () => {
    if (!previewId.current) return
    setPreviewLoading(true)
    try {
      const chunk = await readMaterialText(previewId.current, previewText.length, 4000)
      setPreviewText((prev) => prev + chunk.text)
      setPreviewHasMore(chunk.has_more)
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleDelete = async (record: MaterialOut) => {
    try {
      await deleteMaterial(record.id)
      message.success('已删除')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleDownload = async (record: MaterialOut) => {
    try {
      await downloadMaterial(record.id, record.file_name)
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleReparse = async (record: MaterialOut) => {
    try {
      await reparseMaterial(record.id)
      message.success('已提交重新解析')
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const openEdit = (record: MaterialOut) => {
    setEditing(record)
    editForm.setFieldsValue({
      title: record.title,
      subject: record.subject ?? '',
      tags: record.tags.join(','),
    })
  }

  const submitEdit = async () => {
    if (!editing) return
    const values = await editForm.validateFields()
    try {
      await updateMaterial(editing.id, {
        title: values.title,
        subject: values.subject || null,
        tags: values.tags
          ? values.tags
              .split(',')
              .map((tag) => tag.trim())
              .filter(Boolean)
          : [],
      })
      message.success('已保存')
      setEditing(null)
      await refresh()
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const columns: TableProps<MaterialOut>['columns'] = [
    {
      title: '标题',
      dataIndex: 'title',
      render: (_, record) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{record.title}</Text>
          <Space size={4} wrap>
            <Tag>{record.file_ext.replace('.', '').toUpperCase()}</Tag>
            {record.tags.map((tag) => (
              <Tag key={tag} color="geekblue">
                {tag}
              </Tag>
            ))}
          </Space>
        </Space>
      ),
    },
    { title: '科目', dataIndex: 'subject', width: 100, render: (value) => value || '—' },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      width: 90,
      render: (value: number) => formatSize(value),
    },
    {
      title: '规模',
      width: 130,
      render: (_, record) =>
        record.parse_status === 'success'
          ? `${record.page_count ? record.page_count + ' 页 / ' : ''}${record.char_count ?? 0} 字`
          : '—',
    },
    {
      title: '状态',
      dataIndex: 'parse_status',
      width: 140,
      render: (status: ParseStatus, record) => {
        const meta = STATUS_META[status]
        return (
          <Space orientation="vertical" size={0}>
            <Tag color={meta.color} icon={status === 'parsing' ? <SyncOutlined spin /> : undefined}>
              {meta.text}
            </Tag>
            {record.parse_error && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.parse_error.slice(0, 30)}
              </Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      width: 160,
      render: (value: string) => new Date(value).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      width: 250,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button
            size="small"
            type="link"
            icon={<FileTextOutlined />}
            disabled={record.parse_status !== 'success'}
            onClick={() => void openPreview(record)}
          >
            正文
          </Button>
          <Button
            size="small"
            type="link"
            icon={<DownloadOutlined />}
            onClick={() => void handleDownload(record)}
          >
            下载
          </Button>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          {(record.parse_status === 'failed' || record.parse_status === 'unsupported') && (
            <Button
              size="small"
              type="link"
              icon={<ReloadOutlined />}
              onClick={() => void handleReparse(record)}
            >
              重解析
            </Button>
          )}
          <Popconfirm
            title="删除这份资料？"
            description="会同时删除已上传的文件，不可恢复。"
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
    <Flex vertical gap={16}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          学习资料
        </Title>
        <Text type="secondary">支持 PDF 与 DOCX，单文件不超过 20MB；上传后会自动解析正文</Text>
      </div>

      <Card title="上传资料">
        <Flex gap={8} wrap style={{ marginBottom: 12 }}>
          <Input
            placeholder="科目（可选），如：高数"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            style={{ width: 220 }}
            maxLength={64}
          />
          <Input
            placeholder="标签（可选，逗号分隔），如：极限,定义"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            style={{ width: 300 }}
          />
        </Flex>

        <Upload.Dragger {...uploadProps}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到这里上传</p>
          <p className="ant-upload-hint">仅支持 .pdf / .docx，扫描版 PDF 暂不支持 OCR</p>
        </Upload.Dragger>
      </Card>

      <Card
        title="我的资料"
        extra={
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
            刷新
          </Button>
        }
      >
        <Flex gap={8} wrap style={{ marginBottom: 12 }}>
          <Input.Search
            allowClear
            placeholder="搜索标题"
            style={{ width: 260 }}
            onSearch={(value) => {
              setPage(1)
              setKeyword(value)
            }}
          />
          <Select
            allowClear
            placeholder="解析状态"
            style={{ width: 160 }}
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
        </Flex>

        <Table<MaterialOut>
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
            showTotal: (total) => `共 ${total} 份`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage)
              setSize(nextSize)
            },
          }}
          locale={{ emptyText: '还没有资料，先上传一份吧' }}
        />
      </Card>

      <Modal
        open={Boolean(editing)}
        title="编辑资料"
        onCancel={() => setEditing(null)}
        onOk={() => void submitEdit()}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={editForm} layout="vertical" requiredMark={false}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="subject" label="科目">
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="tags" label="标签（逗号分隔）">
            <Input placeholder="极限,定义" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        open={previewOpen}
        title={`正文预览：${previewTitle}`}
        size={720}
        onClose={() => setPreviewOpen(false)}
      >
        <Paragraph type="secondary">
          共 {previewTotal} 字，当前显示 {previewText.length} 字（每片 4000 字）
        </Paragraph>
        <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{previewText || '（无正文）'}</Paragraph>
        {previewHasMore && (
          <Button loading={previewLoading} onClick={() => void loadMoreText()}>
            加载更多
          </Button>
        )}
      </Drawer>
    </Flex>
  )
}
