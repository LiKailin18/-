import { useQuery } from '@tanstack/react-query'
import { Card, Col, Flex, Row, Segmented, Statistic, Typography } from 'antd'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import { getAdminDaily, getAdminOverview } from '../../api/admin'
import EChart from '../../components/EChart'

const { Text, Title } = Typography

const RANGE_OPTIONS = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]

/** 功能 13.1 仪表盘：全站用户 / 内容 / 学习 / AI 四个视角。 */
export default function AdminDashboardPage() {
  const [days, setDays] = useState(30)

  const dateFrom = dayjs().subtract(days - 1, 'day').format('YYYY-MM-DD')
  const dateTo = dayjs().format('YYYY-MM-DD')

  const { data: overview, isFetching: loadingOverview } = useQuery({
    queryKey: ['admin-overview', days],
    queryFn: () => getAdminOverview(days),
  })

  const { data: daily, isFetching: loadingDaily } = useQuery({
    queryKey: ['admin-daily', dateFrom, dateTo],
    queryFn: () => getAdminDaily(dateFrom, dateTo),
  })

  const items = useMemo(() => daily?.items ?? [], [daily])

  const userOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['新增用户', '活跃用户'] },
      grid: {
        left: 8,
        right: 8,
        bottom: 8,
        top: 40,
        outerBoundsMode: 'same' as const,
        outerBoundsContain: 'axisLabel' as const,
      },
      xAxis: {
        type: 'category' as const,
        data: items.map((item) => dayjs(item.date).format('MM-DD')),
        axisLabel: { interval: days > 30 ? 4 : 0 },
      },
      yAxis: { type: 'value' as const, minInterval: 1 },
      series: [
        {
          name: '新增用户',
          type: 'bar' as const,
          data: items.map((item) => item.new_users),
          itemStyle: { color: '#1677ff' },
          barMaxWidth: 16,
        },
        {
          name: '活跃用户',
          type: 'line' as const,
          smooth: true,
          data: items.map((item) => item.active_users),
          itemStyle: { color: '#52c41a' },
        },
      ],
    }),
    [items, days],
  )

  const usageOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['学习时长', 'AI 调用'] },
      grid: {
        left: 8,
        right: 8,
        bottom: 8,
        top: 40,
        outerBoundsMode: 'same' as const,
        outerBoundsContain: 'axisLabel' as const,
      },
      xAxis: {
        type: 'category' as const,
        data: items.map((item) => dayjs(item.date).format('MM-DD')),
        axisLabel: { interval: days > 30 ? 4 : 0 },
      },
      yAxis: [
        { type: 'value' as const, name: '分钟' },
        { type: 'value' as const, name: '次数', minInterval: 1 },
      ],
      series: [
        {
          name: '学习时长',
          type: 'bar' as const,
          data: items.map((item) => item.study_minutes),
          itemStyle: { color: '#13c2c2' },
          barMaxWidth: 16,
        },
        {
          name: 'AI 调用',
          type: 'line' as const,
          yAxisIndex: 1,
          smooth: true,
          data: items.map((item) => item.ai_calls),
          itemStyle: { color: '#722ed1' },
        },
      ],
    }),
    [items, days],
  )

  const cards = [
    { title: '用户总数', value: overview?.users.total ?? 0, suffix: '人' },
    { title: '近 7 天活跃', value: overview?.users.active_7d ?? 0, suffix: '人' },
    { title: '近 7 天新增', value: overview?.users.new_7d ?? 0, suffix: '人' },
    { title: '已禁用', value: overview?.users.disabled ?? 0, suffix: '人' },
    { title: '学习资料', value: overview?.content.materials ?? 0, suffix: '份' },
    { title: '笔记', value: overview?.content.notes ?? 0, suffix: '条' },
    { title: '学习计划', value: overview?.content.plans ?? 0, suffix: '个' },
    { title: '测试题', value: overview?.content.quizzes ?? 0, suffix: '套' },
    { title: '学习时长', value: overview?.activity.study_minutes ?? 0, suffix: '分钟' },
    {
      title: '任务完成率',
      value: Number(((overview?.activity.task_completion_rate ?? 0) * 100).toFixed(0)),
      suffix: '%',
    },
    { title: 'AI 调用', value: overview?.ai.calls ?? 0, suffix: '次' },
    { title: 'AI token', value: overview?.ai.total_tokens ?? 0, suffix: '' },
  ]

  return (
    <Flex vertical gap={16}>
      <Flex justify="space-between" align="flex-end" wrap gap={12}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            仪表盘
          </Title>
          <Text type="secondary">
            {overview ? `${overview.range.from} ~ ${overview.range.to}` : '加载中…'}
            ；活跃口径：近 7 天有登录
          </Text>
        </div>
        <Segmented
          options={RANGE_OPTIONS}
          value={days}
          onChange={(value) => setDays(value as number)}
        />
      </Flex>

      <Row gutter={[12, 12]}>
        {cards.map((item) => (
          <Col key={item.title} xs={12} md={8} xl={4}>
            <Card size="small" loading={loadingOverview}>
              <Statistic
                title={item.title}
                value={item.value}
                suffix={<Text type="secondary" style={{ fontSize: 12 }}>{item.suffix}</Text>}
                styles={{ content: { fontSize: 20 } }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={12}>
          <Card title="用户趋势" size="small" loading={loadingDaily}>
            <EChart option={userOption} height={300} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="学习与 AI 用量" size="small" loading={loadingDaily}>
            <EChart option={usageOption} height={300} />
          </Card>
        </Col>
      </Row>
    </Flex>
  )
}
