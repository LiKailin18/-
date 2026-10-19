import type {
  AdviceOut,
  ChatMessageOut,
  ChatSessionOut,
  Page,
  SummaryBrief,
  SummaryOut,
  SummaryStyle,
  UsageOut,
} from '../types/api'
import { ApiError, api, getAccessToken, refreshAccessToken } from './client'

/** AI 能力接口（契约：docs/api.md §10、§11、§14） */

/**
 * 生成类接口的专用超时。
 *
 * 默认实例是 15s，但 AI 生成一次命中「模型调用 + 结构化重试」，
 * 后端 `ai_agent_timeout` 就有 90s（`config.py`），所以这里统一放宽到 3 分钟，
 * 否则前端会先于后端超时（表现为「请求超时，请稍后重试」，但记录其实已经落库）。
 */
const AI_GENERATE_TIMEOUT = 180_000

// --------------------------------------------------------------------- 问答


export async function createChatSession(payload: {
  title?: string | null
  material_id?: string | null
}): Promise<ChatSessionOut> {
  const { data } = await api.post<ChatSessionOut>('/ai/chat-sessions', payload)
  return data
}

export async function listChatSessions(page = 1, size = 50): Promise<Page<ChatSessionOut>> {
  const { data } = await api.get<Page<ChatSessionOut>>('/ai/chat-sessions', {
    params: { page, size },
  })
  return data
}

export async function listChatMessages(
  sessionId: string,
  page = 1,
  size = 100,
): Promise<Page<ChatMessageOut>> {
  const { data } = await api.get<Page<ChatMessageOut>>(
    `/ai/chat-sessions/${sessionId}/messages`,
    { params: { page, size } },
  )
  return data
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  await api.delete(`/ai/chat-sessions/${sessionId}`)
}

export interface SseHandlers {
  onMeta?: (data: { session_id: string; message_id: string; model: string }) => void
  onTool?: (data: { name: string; status: string }) => void
  onDelta?: (text: string) => void
  onDone?: (data: { message_id: string; total_tokens: number; latency_ms: number }) => void
  onError?: (data: { code: string; message: string }) => void
}

/**
 * 流式提问。
 *
 * `EventSource` 只支持 GET，而这里是 POST，所以用 fetch + ReadableStream 手写 SSE 解析
 * （契约 §13 就是这么要求的）。401 时先刷新令牌再重试一次，与 axios 拦截器行为一致。
 */
export async function askStream(
  sessionId: string,
  content: string,
  handlers: SseHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const url = `/api/v1/ai/chat-sessions/${sessionId}/messages/stream`

  const send = async (): Promise<Response> =>
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
      },
      body: JSON.stringify({ content }),
      signal,
    })

  let response = await send()
  if (response.status === 401) {
    await refreshAccessToken()
    response = await send()
  }

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    let code = `SYS_${response.status}`
    try {
      const body = (await response.json()) as { code?: string; message?: string }
      code = body.code ?? code
      message = body.message ?? message
    } catch {
      /* 非 JSON 错误体，用默认文案 */
    }
    throw new ApiError(response.status, code, message)
  }
  if (!response.body) {
    throw new ApiError(0, 'NETWORK_ERROR', '当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (event: string, data: string) => {
    let payload: Record<string, unknown> = {}
    try {
      payload = JSON.parse(data) as Record<string, unknown>
    } catch {
      return
    }
    if (event === 'meta') handlers.onMeta?.(payload as never)
    else if (event === 'tool') handlers.onTool?.(payload as never)
    else if (event === 'delta') handlers.onDelta?.(String(payload.text ?? ''))
    else if (event === 'done') handlers.onDone?.(payload as never)
    else if (event === 'error') handlers.onError?.(payload as never)
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 以空行分隔消息块；`: ping` 是心跳注释，忽略
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      let eventName = 'message'
      const dataLines: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith(':')) continue
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length) dispatch(eventName, dataLines.join('\n'))
    }
  }
}

// --------------------------------------------------------------------- 总结


export async function createSummary(payload: {
  material_id: string
  style: SummaryStyle
  scope_start?: number
  scope_end?: number | null
}): Promise<SummaryOut> {
  const { data } = await api.post<SummaryOut>('/ai/summaries', payload, {
    timeout: AI_GENERATE_TIMEOUT,
  })
  return data
}

export async function listSummaries(
  page = 1,
  size = 20,
  materialId?: string,
): Promise<Page<SummaryBrief>> {
  const { data } = await api.get<Page<SummaryBrief>>('/ai/summaries', {
    params: { page, size, material_id: materialId },
  })
  return data
}

export async function getSummary(id: string): Promise<SummaryOut> {
  const { data } = await api.get<SummaryOut>(`/ai/summaries/${id}`)
  return data
}

// --------------------------------------------------------------------- 建议


export async function generateAdvice(payload: {
  days: number
  focus: 'review' | 'plan' | 'balance'
}): Promise<AdviceOut> {
  const { data } = await api.post<AdviceOut>('/ai/advice/generate', payload, {
    timeout: AI_GENERATE_TIMEOUT,
  })
  return data
}

export async function getLatestAdvice(): Promise<{ advice: AdviceOut | null; stale: boolean }> {
  const { data } = await api.get<{ advice: AdviceOut | null; stale: boolean }>('/ai/advice')
  return data
}

// --------------------------------------------------------------------- 用量


export async function getAiUsage(days = 7): Promise<UsageOut> {
  const { data } = await api.get<UsageOut>('/ai/usage', { params: { days } })
  return data
}
