import { DeleteOutlined, PlusOutlined, SendOutlined, StopOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  Empty,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useEffect, useRef, useState } from 'react'

import {
  askStream,
  createChatSession,
  deleteChatSession,
  listChatMessages,
  listChatSessions,
} from '../../api/ai'
import { toApiError } from '../../api/client'
import { useMaterialOptions } from './useMaterialOptions'

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface DisplayMessage {
  key: string
  role: 'user' | 'assistant'
  content: string
}

function Bubble({ item }: { item: DisplayMessage }) {
  const isUser = item.role === 'user'
  return (
    <Flex vertical align={isUser ? 'flex-end' : 'flex-start'} gap={4} style={{ maxWidth: '100%' }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {isUser ? '我' : 'AI 助手'}
      </Text>
      <div
        style={{
          maxWidth: '85%',
          padding: '8px 12px',
          borderRadius: 8,
          background: isUser ? '#e6f4ff' : '#fafafa',
          border: '1px solid',
          borderColor: isUser ? '#91caff' : '#f0f0f0',
        }}
      >
        <Paragraph style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {item.content || (isUser ? '' : '思考中…')}
        </Paragraph>
      </div>
    </Flex>
  )
}

/** 智能问答（功能 7）：会话列表 + 流式打字机（SSE，契约 §13）。 */
export default function ChatTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const { options: materialOptions } = useMaterialOptions()

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [pendingUser, setPendingUser] = useState('')
  const [answer, setAnswer] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [newMaterial, setNewMaterial] = useState<string | undefined>()
  const abortRef = useRef<AbortController | null>(null)

  const { data: sessionPage, isFetching: loadingSessions } = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => listChatSessions(1, 50),
  })
  const sessions = sessionPage?.items ?? []

  useEffect(() => {
    if (!sessionId && sessions.length > 0) setSessionId(sessions[0].id)
  }, [sessionId, sessions])

  const { data: messagePage, isFetching: loadingMessages } = useQuery({
    queryKey: ['chat-messages', sessionId],
    queryFn: () => listChatMessages(sessionId as string, 1, 100),
    enabled: Boolean(sessionId),
  })

  const timeline: DisplayMessage[] = (messagePage?.items ?? []).map((item) => ({
    key: item.id,
    role: item.role,
    content: item.content,
  }))
  if (pendingUser) {
    timeline.push({ key: 'pending-user', role: 'user', content: pendingUser })
  }
  if (streaming) {
    timeline.push({ key: 'pending-answer', role: 'assistant', content: answer })
  }

  const scrollRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [timeline.length, answer])

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['chat-messages', sessionId] })
    await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    await queryClient.invalidateQueries({ queryKey: ['ai-usage'] })
  }

  const handleCreate = async () => {
    try {
      const session = await createChatSession({ material_id: newMaterial ?? null })
      message.success('已新建会话')
      setCreateOpen(false)
      setNewMaterial(undefined)
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      setSessionId(session.id)
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteChatSession(id)
      message.success('已删除会话')
      if (sessionId === id) setSessionId(null)
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || !sessionId || streaming) return

    setInput('')
    setPendingUser(text)
    setAnswer('')
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await askStream(
        sessionId,
        text,
        {
          onDelta: (chunk) => setAnswer((prev) => prev + chunk),
          onError: (data) => message.error(`${data.code}：${data.message}`),
        },
        controller.signal,
      )
    } catch (error) {
      if (!controller.signal.aborted) message.error(toApiError(error).message)
    } finally {
      abortRef.current = null
      setStreaming(false)
      setPendingUser('')
      setAnswer('')
      await refresh()
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
    setStreaming(false)
  }

  return (
    <Flex gap={12} style={{ minHeight: 480 }}>
      <Card
        size="small"
        title="会话"
        style={{ width: 260, flex: '0 0 260px' }}
        styles={{ body: { padding: 8 } }}
        extra={
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建
          </Button>
        }
      >
        <Flex vertical gap={4}>
          {sessions.map((session) => (
            <Flex
              key={session.id}
              justify="space-between"
              align="center"
              gap={4}
              onClick={() => setSessionId(session.id)}
              style={{
                cursor: 'pointer',
                borderRadius: 6,
                padding: '6px 8px',
                background: session.id === sessionId ? '#e6f4ff' : undefined,
              }}
            >
              <Flex vertical style={{ minWidth: 0 }}>
                <Text ellipsis style={{ fontSize: 13, maxWidth: 150 }}>
                  {session.title}
                </Text>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {session.message_count} 条 ·{' '}
                  {dayjs(session.last_message_at ?? session.created_at).format('MM-DD HH:mm')}
                </Text>
              </Flex>
              <Popconfirm
                title="删除这个会话？"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={() => void handleDelete(session.id)}
              >
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Flex>
          ))}
          {loadingSessions && <Empty description="加载中…" />}
          {!loadingSessions && sessions.length === 0 && <Empty description="还没有会话" />}
        </Flex>
      </Card>

      <Flex vertical gap={8} style={{ flex: 1, minWidth: 0 }}>
        {sessionId ? (
          <>
            <div
              ref={scrollRef}
              style={{ flex: 1, overflowY: 'auto', paddingRight: 4, maxHeight: 460, minHeight: 320 }}
            >
              {loadingMessages ? (
                <Empty description="加载中…" />
              ) : timeline.length === 0 ? (
                <Empty
                  description={
                    <Space orientation="vertical" size={2}>
                      <Text>问点什么吧，例如：</Text>
                      <Text type="secondary">「这份资料的核心概念是什么？」</Text>
                      <Text type="secondary">「我最近的学习情况有什么问题？」</Text>
                    </Space>
                  }
                />
              ) : (
                <Flex vertical gap={12}>
                  {timeline.map((item) => (
                    <Bubble key={item.key} item={item} />
                  ))}
                </Flex>
              )}
            </div>

            <Space orientation="vertical" style={{ width: '100%' }} size={6}>
              <TextArea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault()
                    void handleSend()
                  }
                }}
                autoSize={{ minRows: 2, maxRows: 5 }}
                maxLength={4000}
                placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                disabled={streaming}
              />
              <Flex justify="space-between" align="center">
                <Text type="secondary" style={{ fontSize: 12 }}>
                  回答由大模型生成，会调用你的学习数据（只读）
                </Text>
                {streaming ? (
                  <Button danger icon={<StopOutlined />} onClick={handleStop}>
                    停止
                  </Button>
                ) : (
                  <Button type="primary" icon={<SendOutlined />} onClick={() => void handleSend()}>
                    发送
                  </Button>
                )}
              </Flex>
            </Space>
          </>
        ) : (
          <Flex vertical align="center" justify="center" style={{ flex: 1 }}>
            <Empty description="先新建或选择一个会话">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                新建会话
              </Button>
            </Empty>
          </Flex>
        )}
      </Flex>

      <Modal
        open={createOpen}
        title="新建问答会话"
        okText="创建"
        cancelText="取消"
        onCancel={() => setCreateOpen(false)}
        onOk={() => void handleCreate()}
        destroyOnHidden
      >
        <Space orientation="vertical" style={{ width: '100%' }} size={8}>
          <Text type="secondary">
            可选绑定一份资料：绑定后模型会优先参考它（用只读工具按需取片段）。
          </Text>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="选择资料（可不选）"
            style={{ width: '100%' }}
            options={materialOptions}
            value={newMaterial}
            onChange={(value) => setNewMaterial(value)}
          />
        </Space>
      </Modal>
    </Flex>
  )
}
