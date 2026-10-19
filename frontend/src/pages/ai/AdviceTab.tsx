import { BulbOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'

import { generateAdvice, getLatestAdvice } from '../../api/ai'
import { toApiError } from '../../api/client'
import type { AdviceSuggestionOut } from '../../types/api'

const { Text, Title, Paragraph } = Typography

const FOCUS_META: Record<string, { text: string; hint: string }> = {
  review: { text: '复习巩固', hint: '优先补薄弱知识点' },
  plan: { text: '计划推进', hint: '盯着未完成的任务与计划进度' },
  balance: { text: '劳逸结合', hint: '兼顾时长分布与坚持度' },
}

const PRIORITY_META: Record<string, { text: string; color: string }> = {
  high: { text: '高', color: 'red' },
  medium: { text: '中', color: 'gold' },
  low: { text: '低', color: 'blue' },
}

interface WeakPoint {
  knowledge: string
  attempts: number
  correct: number
  accuracy: number
}

interface NextDay {
  date: string
  minutes: number
  focus: string
}

/** 学习建议（功能 10）：基于真实统计生成建议、薄弱点与未来 7 天安排。 */
export default function AdviceTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const [days, setDays] = useState(7)
  const [focus, setFocus] = useState<'review' | 'plan' | 'balance'>('review')
  const [generating, setGenerating] = useState(false)

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['advice-latest'],
    queryFn: getLatestAdvice,
  })

  const advice = data?.advice ?? null
  const weakPoints = (advice?.weak_points ?? []) as unknown as WeakPoint[]
  const nextDays = (advice?.next_7_days ?? []) as unknown as NextDay[]
  const maxMinutes = Math.max(1, ...nextDays.map((item) => item.minutes))

  const handleGenerate = async () => {
    setGenerating(true)
    try {
      await generateAdvice({ days, focus })
      message.success('已生成学习建议')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['advice-latest'] }),
        queryClient.invalidateQueries({ queryKey: ['ai-usage'] }),
      ])
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setGenerating(false)
    }
  }

  const suggestionColumns: TableProps<AdviceSuggestionOut>['columns'] = [
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (value: string) => {
        const meta = PRIORITY_META[value] ?? { text: value, color: 'default' }
        return <Tag color={meta.color}>{meta.text}</Tag>
      },
    },
    {
      title: '建议',
      width: 220,
      render: (_, record) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{record.title}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.reason}
          </Text>
        </Space>
      ),
    },
    { title: '怎么做', dataIndex: 'action' },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap align="center">
        <Select
          style={{ width: 150 }}
          value={days}
          onChange={setDays}
          options={[
            { value: 7, label: '最近 7 天' },
            { value: 14, label: '最近 14 天' },
            { value: 30, label: '最近 30 天' },
          ]}
        />
        <Select
          style={{ width: 160 }}
          value={focus}
          onChange={setFocus}
          options={Object.entries(FOCUS_META).map(([value, meta]) => ({ value, label: meta.text }))}
        />
        <Button type="primary" icon={<BulbOutlined />} loading={generating} onClick={() => void handleGenerate()}>
          生成学习建议
        </Button>
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {FOCUS_META[focus].hint}；数字部分由后端按你的真实记录计算并覆盖模型输出
        </Text>
      </Flex>

      {advice ? (
        <>
          {advice.stale && (
            <Alert
              type="warning"
              showIcon
              title="这份建议生成后你的学习记录有更新，建议重新生成"
            />
          )}

          <Card
            size="small"
            title={
              <Space size={6}>
                <Text>总体诊断</Text>
                <Tag>{advice.period_days} 天</Tag>
                <Tag color="purple">{FOCUS_META[advice.focus]?.text ?? advice.focus}</Tag>
              </Space>
            }
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                {dayjs(advice.created_at).format('YYYY-MM-DD HH:mm')} ·{' '}
                <Text code>{advice.model}</Text>
              </Text>
            }
          >
            <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{advice.summary}</Paragraph>
          </Card>

          <Card size="small" title={`改进建议（${advice.suggestions.length} 条）`}>
            {advice.suggestions.length ? (
              <Table<AdviceSuggestionOut>
                rowKey="title"
                size="small"
                columns={suggestionColumns}
                dataSource={advice.suggestions}
                pagination={false}
              />
            ) : (
              <Empty description="没有建议" />
            )}
          </Card>

          <Row gutter={12}>
            <Col xs={24} lg={12}>
              <Card size="small" title="薄弱知识点" style={{ height: '100%' }}>
                {weakPoints.length ? (
                  <Table<WeakPoint>
                    rowKey="knowledge"
                    size="small"
                    pagination={false}
                    dataSource={weakPoints}
                    columns={[
                      { title: '知识点', dataIndex: 'knowledge' },
                      {
                        title: '正确率',
                        width: 160,
                        render: (_, record) => (
                          <Space size={6}>
                            <Text type={record.accuracy < 0.6 ? 'danger' : undefined}>
                              {(record.accuracy * 100).toFixed(0)}%
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              ({record.correct}/{record.attempts})
                            </Text>
                          </Space>
                        ),
                      },
                    ]}
                  />
                ) : (
                  <Empty description="还没有足够的答题记录（多做几套测试题就有了）" />
                )}
              </Card>
            </Col>

            <Col xs={24} lg={12}>
              <Card size="small" title="未来 7 天安排" style={{ height: '100%' }}>
                {nextDays.length ? (
                  <Flex vertical gap={8}>
                    {nextDays.map((item) => (
                      <Flex key={item.date} align="center" gap={8}>
                        <Text style={{ width: 64, fontSize: 12 }}>{dayjs(item.date).format('MM-DD')}</Text>
                        <div style={{ flex: 1, background: '#f5f5f5', borderRadius: 4, height: 18 }}>
                          <div
                            style={{
                              width: `${Math.round((item.minutes / maxMinutes) * 100)}%`,
                              background: '#1677ff',
                              height: '100%',
                              borderRadius: 4,
                            }}
                          />
                        </div>
                        <Text style={{ width: 60, fontSize: 12, textAlign: 'right' }}>
                          {item.minutes} 分钟
                        </Text>
                        <Text type="secondary" ellipsis style={{ width: 140, fontSize: 12 }}>
                          {item.focus}
                        </Text>
                      </Flex>
                    ))}
                  </Flex>
                ) : (
                  <Empty description="没有安排（需要先有学习计划）" />
                )}
              </Card>
            </Col>
          </Row>

          <Text type="secondary" style={{ fontSize: 12 }}>
            生成耗时 {advice.latency_ms ? `${(advice.latency_ms / 1000).toFixed(1)}s` : '—'}
          </Text>
        </>
      ) : (
        <Card>
          <Flex vertical align="center" gap={8} style={{ padding: 24 }}>
            <Title level={5} style={{ margin: 0 }}>
              还没有学习建议
            </Title>
            <Text type="secondary">
              建议基于你的学习记录、任务完成率与答题正确率生成，先积累一点数据会更准
            </Text>
            <Button type="primary" icon={<BulbOutlined />} loading={generating} onClick={() => void handleGenerate()}>
              立即生成
            </Button>
          </Flex>
        </Card>
      )}
    </Flex>
  )
}
