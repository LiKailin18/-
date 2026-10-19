import { FileTextOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  Descriptions,
  Empty,
  Flex,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'

import { createSummary, getSummary, listSummaries } from '../../api/ai'
import { toApiError } from '../../api/client'
import type { SummaryOut, SummaryStyle } from '../../types/api'
import { useMaterialOptions } from './useMaterialOptions'

const { Text, Title, Paragraph } = Typography

const STYLE_META: Record<SummaryStyle, { text: string; hint: string }> = {
  outline: { text: '提纲', hint: '分层列点，适合快速回顾结构' },
  key_points: { text: '要点', hint: '只提炼关键结论' },
  detailed: { text: '详细', hint: '逐节展开，适合复习' },
}

const MODE_TEXT: Record<string, string> = {
  direct: '单次生成',
  map_reduce: '分段归并',
}

/** 资料总结（功能 8）：选资料 → 生成 → 查看要点与正文。 */
export default function SummaryTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const { options: materialOptions, titleOf } = useMaterialOptions()

  const [materialId, setMaterialId] = useState<string | undefined>()
  const [style, setStyle] = useState<SummaryStyle>('outline')
  const [generating, setGenerating] = useState(false)
  const [detail, setDetail] = useState<SummaryOut | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  const { data: page, isFetching, refetch } = useQuery({
    queryKey: ['summaries'],
    queryFn: () => listSummaries(1, 30),
  })
  const summaries = page?.items ?? []

  // 列表加载完自动展示第一条详情，避免右侧空着
  useEffect(() => {
    if (!detail && summaries.length > 0) {
      setLoadingDetail(true)
      void getSummary(summaries[0].id)
        .then(setDetail)
        .finally(() => setLoadingDetail(false))
    }
  }, [detail, summaries])

  const openDetail = async (id: string) => {
    setLoadingDetail(true)
    try {
      setDetail(await getSummary(id))
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleGenerate = async () => {
    if (!materialId) {
      message.warning('请先选择一份资料')
      return
    }
    setGenerating(true)
    try {
      const result = await createSummary({ material_id: materialId, style })
      setDetail(result)
      message.success(`已生成${STYLE_META[style].text}（${result.mode === 'direct' ? '单次' : '分段归并'}）`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['summaries'] }),
        queryClient.invalidateQueries({ queryKey: ['ai-usage'] }),
      ])
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap align="center">
        <Select
          showSearch
          optionFilterProp="label"
          placeholder="选择资料"
          style={{ width: 260 }}
          options={materialOptions}
          value={materialId}
          onChange={(value) => setMaterialId(value)}
        />
        <Select
          style={{ width: 160 }}
          value={style}
          onChange={(value) => setStyle(value)}
          options={(Object.keys(STYLE_META) as SummaryStyle[]).map((key) => ({
            value: key,
            label: STYLE_META[key].text,
          }))}
        />
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={generating}
          onClick={() => void handleGenerate()}
        >
          生成总结
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {STYLE_META[style].hint}
        </Text>
      </Flex>

      <Flex gap={12} align="flex-start">
        <Card
          size="small"
          title="历史总结"
          style={{ width: 280, flex: '0 0 280px' }}
          styles={{ body: { padding: 8 } }}
          extra={
            <Button size="small" icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()} />
          }
        >
          <Flex vertical gap={4}>
            {summaries.map((item) => (
              <Flex
                key={item.id}
                vertical
                gap={2}
                onClick={() => void openDetail(item.id)}
                style={{
                  cursor: 'pointer',
                  borderRadius: 6,
                  padding: '6px 8px',
                  background: item.id === detail?.id ? '#e6f4ff' : undefined,
                }}
              >
                <Text ellipsis style={{ fontSize: 13, maxWidth: 210 }}>
                  {titleOf(item.material_id)}
                </Text>
                <Space size={4} wrap>
                  <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>
                    {STYLE_META[item.style]?.text ?? item.style}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {item.char_count} 字 · {dayjs(item.created_at).format('MM-DD HH:mm')}
                  </Text>
                </Space>
              </Flex>
            ))}
            {isFetching && <Empty description="加载中…" />}
            {!isFetching && summaries.length === 0 && <Empty description="还没有总结" />}
          </Flex>
        </Card>

        <Card
          size="small"
          style={{ flex: 1, minWidth: 0 }}
          title={
            detail ? (
              <Space size={6}>
                <FileTextOutlined />
                <Text>{titleOf(detail.material_id)}</Text>
              </Space>
            ) : (
              '总结详情'
            )
          }
          loading={loadingDetail}
        >
          {detail ? (
            <Flex vertical gap={12}>
              <Descriptions size="small" column={4} items={[
                { key: 'mode', label: '方式', children: MODE_TEXT[detail.mode] ?? detail.mode },
                { key: 'segments', label: '分段', children: detail.segments },
                { key: 'len', label: '字数', children: detail.char_count },
                { key: 'model', label: '模型', children: <Text code>{detail.model}</Text> },
              ]} />

              {detail.key_points.length > 0 && (
                <div>
                  <Title level={5} style={{ marginBottom: 6 }}>
                    要点
                  </Title>
                  <Flex vertical gap={4}>
                    {detail.key_points.map((point, index) => (
                      <Text key={`${index}-${point.slice(0, 8)}`}>
                        {index + 1}. {point}
                      </Text>
                    ))}
                  </Flex>
                </div>
              )}

              <div>
                <Title level={5} style={{ marginBottom: 6 }}>
                  正文
                </Title>
                <Paragraph style={{ whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12, borderRadius: 8, marginBottom: 0 }}>
                  {detail.summary_md}
                </Paragraph>
              </div>

              <Text type="secondary" style={{ fontSize: 12 }}>
                用量：{detail.prompt_tokens + detail.completion_tokens} tokens
                {detail.latency_ms ? ` · ${(detail.latency_ms / 1000).toFixed(1)}s` : ''} ·{' '}
                {dayjs(detail.created_at).format('YYYY-MM-DD HH:mm')}
              </Text>
            </Flex>
          ) : (
            <Empty description="选一份资料生成总结，或点左侧历史记录查看" />
          )}
        </Card>
      </Flex>
    </Flex>
  )
}
