import { useQuery } from '@tanstack/react-query'
import { Button, Card, Flex, Progress, Result, Space, Statistic, Tabs, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router'

import { getAiUsage } from '../api/ai'
import AdviceTab from './ai/AdviceTab'
import ChatTab from './ai/ChatTab'
import QuizTab from './ai/QuizTab'
import SummaryTab from './ai/SummaryTab'

const { Text, Title } = Typography

/** AI 能力总览：把功能 7–10 放在一个页面里，顶部统一显示今日用量与配额。 */
export default function AiPage() {
  const navigate = useNavigate()
  const { data: usage, error, isError } = useQuery({
    queryKey: ['ai-usage'],
    queryFn: () => getAiUsage(7),
    retry: false,
  })

  // 管理员可以把 AI 整个关掉（功能 13.5）→ 整组 /ai/* 返回 503。
  // 用「读 status 字段」而不是 instanceof：HMR / 多 chunk 下类身份不一定相同；
  // 取不到 status 时也按「不可用」处理（否则 503 会退化成一片空表格）。
  const status = (error as { status?: number } | null)?.status
  if (isError && (status === 503 || status === undefined)) {
    return (
      <Card>
        <Result
          status="warning"
          title="AI 功能已暂停"
          subTitle="管理员已关闭 AI 功能，总结 / 出题 / 建议 / 问答暂时不可用。已生成的题目仍可继续作答。"
          extra={
            <Button type="primary" onClick={() => void navigate('/')}>
              返回工作台
            </Button>
          }
        />
      </Card>
    )
  }

  const quotaPercent = usage
    ? Math.min(100, Math.round((usage.today_calls / Math.max(1, usage.daily_quota)) * 100))
    : 0

  return (
    <Flex vertical gap={16} style={{ maxWidth: 1280, margin: '0 auto', width: '100%' }}>
      <Flex justify="space-between" align="flex-end" wrap gap={12}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            AI 助手
          </Title>
          <Text type="secondary">
            总结、出题、判分、建议与问答都由真实大模型驱动；所有工具只读，数据不会跨账号
          </Text>
        </div>

        <Card size="small" style={{ minWidth: 380 }}>
          <Flex align="center" gap={24} wrap>
            <Statistic
              title="今日调用"
              value={usage?.today_calls ?? 0}
              suffix={`/ ${usage?.daily_quota ?? '—'}`}
              styles={{ content: { fontSize: 20 } }}
            />
            <Statistic
              title="近 7 天 token"
              value={usage?.total_tokens ?? 0}
              styles={{ content: { fontSize: 20 } }}
            />
            <Flex vertical align="center" gap={2}>
              <Progress type="circle" size={52} percent={quotaPercent} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                今日配额
              </Text>
            </Flex>
            {usage && (
              <Space orientation="vertical" size={2}>
                <Tag color={usage.success_rate >= 0.95 ? 'success' : 'warning'}>
                  成功率 {(usage.success_rate * 100).toFixed(0)}%
                </Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  配额用尽会返回 AI_001
                </Text>
              </Space>
            )}
          </Flex>
        </Card>
      </Flex>

      <Card>
        <Tabs
          defaultActiveKey="chat"
          items={[
            { key: 'chat', label: '智能问答', children: <ChatTab /> },
            { key: 'summary', label: '资料总结', children: <SummaryTab /> },
            { key: 'quiz', label: '测试题', children: <QuizTab /> },
            { key: 'advice', label: '学习建议', children: <AdviceTab /> },
          ]}
        />
      </Card>
    </Flex>
  )
}
