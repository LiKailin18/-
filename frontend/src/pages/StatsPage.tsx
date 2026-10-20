import { useQuery } from '@tanstack/react-query'
import { Card, Col, Empty, Flex, Row, Segmented, Statistic, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import { getStatsDaily, getStatsOverview, getStatsSubjects, getWeakPoints } from '../api/stats'
import EChart from '../components/EChart'
import type { WeakPointItem } from '../types/api'

const { Text, Title } = Typography

const RANGE_OPTIONS = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]

const percent = (value: number) => `${(value * 100).toFixed(0)}%`

/** 学习数据统计（功能 11）：概览 + 时长/任务趋势 + 科目分布 + 正确率趋势 + 薄弱知识点。 */
export default function StatsPage() {
  const [days, setDays] = useState(7)

  const dateFrom = dayjs().subtract(days - 1, 'day').format('YYYY-MM-DD')
  const dateTo = dayjs().format('YYYY-MM-DD')

  const { data: overview, isFetching: loadingOverview } = useQuery({
    queryKey: ['stats-overview', days],
    queryFn: () => getStatsOverview(days),
  })

  const { data: daily, isFetching: loadingDaily } = useQuery({
    queryKey: ['stats-daily', dateFrom, dateTo],
    queryFn: () => getStatsDaily(dateFrom, dateTo),
  })

  const { data: subjects, isFetching: loadingSubjects } = useQuery({
    queryKey: ['stats-subjects', dateFrom, dateTo],
    queryFn: () => getStatsSubjects(dateFrom, dateTo),
  })

  const { data: weakPoints, isFetching: loadingWeak } = useQuery({
    queryKey: ['stats-weak-points'],
    queryFn: () => getWeakPoints(30, 5),
  })

  const trend = useMemo(() => daily?.items ?? [], [daily])
  const subjectItems = subjects?.items ?? []
  const weakItems = weakPoints?.items ?? []

  const hasAnyRecord = trend.some((item) => item.minutes > 0 || item.task_done > 0)
  const hasAnyQuiz = trend.some((item) => item.quiz_attempts > 0)

  const trendOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' as const },
      // ECharts 6 的 legend 默认在「底部」，会压住 x 轴 —— 显式放到顶部
      legend: { data: ['学习时长', '完成任务'], top: 0, left: 'center' },
      grid: {
        left: 8,
        right: 8,
        bottom: 8,
        top: 48,
        // 自动为坐标轴标签/名称留白（已注册 LegacyGridContainLabel）
        containLabel: true,
      },
      xAxis: {
        type: 'category' as const,
        data: trend.map((item) => dayjs(item.date).format('MM-DD')),
        axisLabel: { interval: days > 30 ? 4 : 0 },
      },
      yAxis: [
        { type: 'value' as const, name: '分钟' },
        { type: 'value' as const, name: '任务数', minInterval: 1 },
      ],
      series: [
        {
          name: '学习时长',
          type: 'bar' as const,
          data: trend.map((item) => item.minutes),
          itemStyle: { color: '#1677ff' },
          barMaxWidth: 18,
        },
        {
          name: '完成任务',
          type: 'line' as const,
          yAxisIndex: 1,
          smooth: true,
          data: trend.map((item) => item.task_done),
          itemStyle: { color: '#52c41a' },
        },
      ],
    }),
    [trend, days],
  )

  const subjectOption = useMemo(
    () => ({
      tooltip: { trigger: 'item' as const, formatter: '{b}：{c} 分钟（{d}%）' },
      legend: { bottom: 0, type: 'scroll' as const },
      series: [
        {
          type: 'pie' as const,
          // 饼图上移一点，给底部图例让位
          center: ['50%', '44%'],
          radius: ['36%', '60%'],
          avoidLabelOverlap: true,
          label: { formatter: '{b}' },
          data: subjectItems.map((item) => ({ name: item.subject, value: item.minutes })),
        },
      ],
    }),
    [subjectItems],
  )

  const accuracyOption = useMemo(
    () => ({
      tooltip: {
        trigger: 'axis' as const,
        formatter: (params: unknown) => {
          const list = params as { axisValue: string; value: number }[]
          const first = list[0]
          return `${first?.axisValue ?? ''}<br/>正确率 ${first?.value ?? 0}%`
        },
      },
      grid: {
        left: 8,
        right: 8,
        bottom: 8,
        top: 30,
        containLabel: true,
      },
      xAxis: {
        type: 'category' as const,
        data: trend.map((item) => dayjs(item.date).format('MM-DD')),
        axisLabel: { interval: days > 30 ? 4 : 0 },
      },
      yAxis: { type: 'value' as const, min: 0, max: 100, name: '%' },
      series: [
        {
          type: 'line' as const,
          smooth: true,
          connectNulls: true,
          areaStyle: { opacity: 0.12 },
          itemStyle: { color: '#722ed1' },
          data: trend.map((item) =>
            item.quiz_attempts > 0 ? Math.round(item.quiz_accuracy * 100) : null,
          ),
        },
      ],
    }),
    [trend, days],
  )

  const weakColumns: TableProps<WeakPointItem>['columns'] = [
    { title: '知识点', dataIndex: 'knowledge' },
    {
      title: '正确率',
      width: 120,
      render: (_, record) => (
        <Text type={record.accuracy < 0.6 ? 'danger' : undefined}>{percent(record.accuracy)}</Text>
      ),
    },
    {
      title: '答题数',
      width: 100,
      render: (_, record) => `${record.correct}/${record.attempts}`,
    },
    {
      title: '建议',
      width: 160,
      render: (_, record) => (
        <Tag color={record.accuracy < 0.6 ? 'red' : 'gold'}>
          {record.accuracy < 0.6 ? '优先复习' : '再巩固'}
        </Tag>
      ),
    },
  ]

  return (
    <Flex vertical gap={16} style={{ maxWidth: 1280, margin: '0 auto', width: '100%' }}>
      <Flex justify="space-between" align="flex-end" wrap gap={12}>
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>
            学习统计
          </Title>
          <Text type="secondary">
            {overview
              ? `${overview.period.from} ~ ${overview.period.to}（${overview.period.days} 天）`
              : '加载中…'}
            ；口径：任务完成率不计「跳过」，日期按业务时区切分
          </Text>
        </div>
        <Segmented
          options={RANGE_OPTIONS}
          value={days}
          onChange={(value) => setDays(value as number)}
        />
      </Flex>

      <Row gutter={[12, 12]}>
        {[
          { title: '学习总时长', value: overview?.total_minutes ?? 0, suffix: '分钟' },
          { title: '日均时长', value: overview?.daily_avg_minutes ?? 0, suffix: '分钟' },
          { title: '活跃天数', value: overview?.active_days ?? 0, suffix: '天' },
          { title: '连续学习', value: overview?.streak_days ?? 0, suffix: '天' },
          {
            title: '任务完成率',
            value: Number(((overview?.task_completion_rate ?? 0) * 100).toFixed(0)),
            suffix: `%（${overview?.task_done ?? 0}/${overview?.task_total ?? 0}）`,
          },
          {
            title: '答题正确率',
            value: Number(((overview?.quiz_accuracy ?? 0) * 100).toFixed(0)),
            suffix: `%（${overview?.quiz_attempts ?? 0} 次）`,
          },
        ].map((item) => (
          <Col key={item.title} xs={12} md={8} lg={4}>
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

      <Card
        title="学习时长与任务完成"
        size="small"
        loading={loadingDaily}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>柱＝分钟，线＝完成任务数</Text>}
      >
        {hasAnyRecord ? (
          <EChart option={trendOption} height={300} />
        ) : (
          <Empty description="这段时间还没有学习记录（完成任务或记一次学习就有了）" />
        )}
      </Card>

      <Row gutter={[12, 12]} align="stretch">
        <Col xs={24} lg={10}>
          <Card title="科目分布" size="small" loading={loadingSubjects} style={{ height: '100%' }}>
            {subjectItems.length ? (
              <EChart option={subjectOption} height={300} />
            ) : (
              <Empty
                style={{ minHeight: 300, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
                description="还没有带科目的学习记录（任务所属计划里填了「科目」就会归到对应科目）"
              />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card
            title="答题正确率趋势"
            size="small"
            loading={loadingDaily}
            style={{ height: '100%' }}
            extra={<Text type="secondary" style={{ fontSize: 12 }}>只统计交过卷的日期</Text>}
          >
            {hasAnyQuiz ? (
              <EChart option={accuracyOption} height={300} />
            ) : (
              <Empty
                style={{ minHeight: 300, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}
                description="还没有答卷记录（去 AI 助手 → 测试题做一套）"
              />
            )}
          </Card>
        </Col>
      </Row>

      <Card
        title="薄弱知识点"
        size="small"
        loading={loadingWeak}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>近 30 天，样本少于 3 次不计</Text>}
      >
        <Table<WeakPointItem>
          rowKey="knowledge"
          size="small"
          pagination={false}
          columns={weakColumns}
          dataSource={weakItems}
          locale={{ emptyText: '还没有足够的答题记录' }}
        />
      </Card>
    </Flex>
  )
}
