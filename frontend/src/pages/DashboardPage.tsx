import {
  AlertOutlined,
  CalendarOutlined,
  CheckSquareOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  RightOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Col, Empty, Flex, Row, Space, Statistic, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router'

import { getRecommendations, getStatsOverview } from '../api/stats'
import { listTasks } from '../api/tasks'
import { useAuthStore } from '../stores/auth'
import type { RecommendationKind, TaskStatus } from '../types/api'

const { Text, Title } = Typography

const KIND_META: Record<RecommendationKind, { label: string; color: string; icon: React.ReactNode }> = {
  task: { label: '该做的任务', color: 'blue', icon: <CheckSquareOutlined /> },
  review: { label: '补短板', color: 'red', icon: <AlertOutlined /> },
  plan: { label: '计划推进', color: 'geekblue', icon: <CalendarOutlined /> },
  material: { label: '资料待处理', color: 'orange', icon: <FileTextOutlined /> },
  habit: { label: '学习习惯', color: 'green', icon: <ClockCircleOutlined /> },
}

const TASK_STATUS: Record<TaskStatus, { text: string; color: string }> = {
  pending: { text: '待完成', color: 'default' },
  doing: { text: '进行中', color: 'processing' },
  done: { text: '已完成', color: 'success' },
  skipped: { text: '已跳过', color: 'warning' },
}

/**
 * 工作台：进来先看「今天做什么」。
 *
 * 数据来自 M6 的统计与推荐接口——推荐是规则算出来的（秒回、可解释），
 * 完整的图表在「学习统计」页，深度的叙述性建议在「AI 助手 → 学习建议」。
 */
export default function DashboardPage() {
  const user = useAuthStore((state) => state.user)
  const navigate = useNavigate()
  const today = dayjs().format('YYYY-MM-DD')

  const { data: overview, isFetching: loadingOverview } = useQuery({
    queryKey: ['stats-overview', 7],
    queryFn: () => getStatsOverview(7),
  })

  const { data: recommendations, isFetching: loadingRecs } = useQuery({
    queryKey: ['recommendations'],
    queryFn: () => getRecommendations(5),
  })

  const { data: taskPage, isFetching: loadingTasks } = useQuery({
    queryKey: ['tasks', 'today', today],
    queryFn: () => listTasks({ page: 1, size: 5, date_from: today, date_to: today }),
  })

  if (!user) return null

  const tasks = taskPage?.items ?? []
  const tips = recommendations?.items ?? []

  return (
    <Flex vertical gap={16} style={{ maxWidth: 1100, margin: '0 auto' }}>
      <Flex justify="space-between" align="flex-end" wrap gap={8}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            工作台
          </Title>
          <Text type="secondary">
            欢迎回来，{user.nickname || user.username} · 今天是 {today}
          </Text>
        </div>
        <Space>
          <Button onClick={() => void navigate('/stats')}>看统计图表</Button>
          <Button type="primary" onClick={() => void navigate('/plans?tab=tasks')}>
            去完成任务
          </Button>
        </Space>
      </Flex>

      <Row gutter={[12, 12]}>
        {[
          { title: '近 7 天学习', value: overview?.total_minutes ?? 0, suffix: '分钟' },
          {
            title: '任务完成率',
            value: Number(((overview?.task_completion_rate ?? 0) * 100).toFixed(0)),
            suffix: `%（${overview?.task_done ?? 0}/${overview?.task_total ?? 0}）`,
          },
          { title: '连续学习', value: overview?.streak_days ?? 0, suffix: '天' },
          {
            title: '答题正确率',
            value: Number(((overview?.quiz_accuracy ?? 0) * 100).toFixed(0)),
            suffix: `%（${overview?.quiz_attempts ?? 0} 次）`,
          },
        ].map((item) => (
          <Col key={item.title} xs={12} md={6}>
            <Card size="small" loading={loadingOverview}>
              <Statistic
                title={item.title}
                value={item.value}
                suffix={<Text type="secondary" style={{ fontSize: 12 }}>{item.suffix}</Text>}
                styles={{ content: { fontSize: 22 } }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} lg={14}>
          <Card
            title="今天做什么"
            size="small"
            loading={loadingRecs}
            style={{ height: '100%' }}
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                按学习数据实时算出来的，不消耗 AI 配额
              </Text>
            }
          >
            {tips.length ? (
              <Flex vertical gap={10}>
                {tips.map((tip) => {
                  const meta = KIND_META[tip.kind]
                  return (
                    <Flex
                      key={`${tip.kind}-${tip.ref_id ?? 'none'}`}
                      align="flex-start"
                      justify="space-between"
                      gap={12}
                    >
                      <Flex vertical gap={2} style={{ minWidth: 0 }}>
                        <Space size={6} wrap>
                          <Tag color={meta.color} icon={meta.icon} style={{ marginInlineEnd: 0 }}>
                            {meta.label}
                          </Tag>
                          <Text strong>{tip.title}</Text>
                        </Space>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {tip.reason}
                        </Text>
                      </Flex>
                      <Button
                        size="small"
                        type="link"
                        icon={<RightOutlined />}
                        iconPlacement="end"
                        onClick={() => void navigate(tip.route)}
                      >
                        {tip.action}
                      </Button>
                    </Flex>
                  )
                })}
              </Flex>
            ) : (
              <Empty description="状态不错，继续保持（没有需要特别提醒的事）" />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card
            title="今日任务"
            size="small"
            loading={loadingTasks}
            style={{ height: '100%' }}
            extra={
              <Button type="link" size="small" onClick={() => void navigate('/plans?tab=tasks')}>
                全部任务
              </Button>
            }
          >
            {tasks.length ? (
              <Flex vertical gap={8}>
                {tasks.map((task) => (
                  <Flex key={task.id} align="center" justify="space-between" gap={8}>
                    <Text
                      ellipsis
                      style={{
                        maxWidth: 200,
                        textDecoration: task.status === 'done' ? 'line-through' : undefined,
                      }}
                    >
                      {task.title}
                    </Text>
                    <Space size={6}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {task.est_minutes} 分钟
                      </Text>
                      <Tag color={TASK_STATUS[task.status].color}>{TASK_STATUS[task.status].text}</Tag>
                    </Space>
                  </Flex>
                ))}
              </Flex>
            ) : (
              <Empty description="今天没有任务（去「学习计划」生成每日任务）" />
            )}
          </Card>
        </Col>
      </Row>

      <Card size="small">
        <Flex align="center" justify="space-between" wrap gap={12}>
          <Space size={16} wrap>
            <Text type="secondary">
              资料 <Text strong>{overview?.materials ?? 0}</Text> 份
            </Text>
            <Text type="secondary">
              笔记 <Text strong>{overview?.notes ?? 0}</Text> 条
            </Text>
            <Text type="secondary">
              AI 调用 <Text strong>{overview?.ai_calls ?? 0}</Text> 次（近 7 天）
            </Text>
          </Space>
          <Space>
            <Button type="link" onClick={() => void navigate('/materials')}>
              学习资料
            </Button>
            <Button type="link" onClick={() => void navigate('/notes')}>
              在线笔记
            </Button>
            <Button type="link" onClick={() => void navigate('/ai')}>
              AI 助手
            </Button>
          </Space>
        </Flex>
      </Card>
    </Flex>
  )
}
