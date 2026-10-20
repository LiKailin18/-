import { ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  Button,
  Card,
  Col,
  DatePicker,
  Flex,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { useMemo, useState } from 'react'

import { getAdminAiStats, listAiUsage } from '../../api/admin'
import EChart from '../../components/EChart'
import type { AiUsageItemOut } from '../../types/api'

const { Text } = Typography

const SCENE_META: Record<string, { text: string; color: string }> = {
  qa: { text: '智能问答', color: 'blue' },
  summary: { text: '资料总结', color: 'geekblue' },
  quiz: { text: '测试题', color: 'purple' },
  advice: { text: '学习建议', color: 'cyan' },
}

const RANGE_OPTIONS = [
  { label: '近 7 天', value: 7 },
  { label: '近 30 天', value: 30 },
  { label: '近 90 天', value: 90 },
]

/** 功能 13.4 AI 用量：按场景 / 用户 / 日期 + 调用明细。 */
export default function AdminAiUsagePage() {
  const [days, setDays] = useState(30)
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(10)
  const [scene, setScene] = useState<string | undefined>()
  const [okFilter, setOkFilter] = useState<boolean | undefined>()
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)

  const dateFrom = range?.[0]?.format('YYYY-MM-DD')
  const dateTo = range?.[1]?.format('YYYY-MM-DD')

  const { data: stats, isFetching: loadingStats } = useQuery({
    queryKey: ['admin-ai-stats', days],
    queryFn: () => getAdminAiStats(days),
  })

  const { data: usage, isFetching, refetch } = useQuery({
    queryKey: ['admin-ai-usage', page, size, scene, okFilter, dateFrom, dateTo],
    queryFn: () =>
      listAiUsage({
        page,
        size,
        scene,
        ok: okFilter,
        date_from: dateFrom,
        date_to: dateTo,
      }),
  })

  const daily = useMemo(() => stats?.daily ?? [], [stats])

  const dailyOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' as const },
      legend: { data: ['调用次数', '失败次数'], top: 0, left: 'center' },
      grid: {
        left: 8,
        right: 8,
        bottom: 8,
        top: 48,
        containLabel: true,
      },
      xAxis: {
        type: 'category' as const,
        data: daily.map((item) => dayjs(item.date).format('MM-DD')),
        axisLabel: { interval: days > 30 ? 4 : 0 },
      },
      yAxis: { type: 'value' as const, minInterval: 1 },
      series: [
        {
          name: '调用次数',
          type: 'bar' as const,
          data: daily.map((item) => item.calls),
          itemStyle: { color: '#722ed1' },
          barMaxWidth: 16,
        },
        {
          name: '失败次数',
          type: 'bar' as const,
          data: daily.map((item) => item.failed),
          itemStyle: { color: '#ff4d4f' },
          barMaxWidth: 16,
        },
      ],
    }),
    [daily, days],
  )

  const sceneColumns: TableProps<NonNullable<typeof stats>['by_scene'][number]>['columns'] = [
    {
      title: '场景',
      dataIndex: 'scene',
      width: 130,
      render: (value: string) => (
        <Tag color={SCENE_META[value]?.color}>{SCENE_META[value]?.text ?? value}</Tag>
      ),
    },
    { title: '调用次数', dataIndex: 'calls', width: 110 },
    { title: 'token', dataIndex: 'total_tokens', width: 130 },
    {
      title: '成功率',
      width: 110,
      render: (_, row) => `${(row.success_rate * 100).toFixed(1)}%`,
    },
    {
      title: '平均耗时',
      width: 130,
      render: (_, row) => `${(row.avg_latency_ms / 1000).toFixed(1)}s`,
    },
  ]

  const columns: TableProps<AiUsageItemOut>['columns'] = [
    {
      title: '时间',
      width: 160,
      render: (_, row) => dayjs(row.created_at).format('YYYY-MM-DD HH:mm:ss'),
    },
    { title: '用户', width: 140, render: (_, row) => <Tag>{row.user.username}</Tag> },
    {
      title: '场景',
      width: 110,
      render: (_, row) => (
        <Tag color={SCENE_META[row.scene]?.color}>{SCENE_META[row.scene]?.text ?? row.scene}</Tag>
      ),
    },
    { title: '模型', dataIndex: 'model', width: 140 },
    {
      title: 'token',
      width: 190,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.total_tokens}（入 {row.prompt_tokens} / 出 {row.completion_tokens}）
        </Text>
      ),
    },
    {
      title: '步数 / 耗时',
      width: 130,
      render: (_, row) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.steps} 步 · {row.latency_ms ? `${(row.latency_ms / 1000).toFixed(1)}s` : '—'}
        </Text>
      ),
    },
    {
      title: '结果',
      width: 130,
      render: (_, row) =>
        row.ok ? (
          <Tag color="success">成功</Tag>
        ) : (
          <Tag color="error">{row.error_code ?? '失败'}</Tag>
        ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex justify="space-between" align="flex-end" wrap gap={12}>
        <div>
          <Text strong style={{ fontSize: 16 }}>
            AI 用量监控
          </Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            失败调用同样计次（它也真的发出了请求）；成功率 = ok / 总调用
          </Text>
        </div>
        <Segmented
          options={RANGE_OPTIONS}
          value={days}
          onChange={(value) => setDays(value as number)}
        />
      </Flex>

      <Row gutter={[12, 12]}>
        <Col xs={24} xl={12}>
          <Card title="每日调用" size="small" loading={loadingStats}>
            <EChart option={dailyOption} height={280} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="按场景" size="small" loading={loadingStats}>
            <Table
              rowKey="scene"
              size="small"
              pagination={false}
              columns={sceneColumns}
              dataSource={stats?.by_scene ?? []}
              locale={{ emptyText: '这段时间没有调用' }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              调用量 Top 用户：
              {(stats?.top_users ?? [])
                .slice(0, 5)
                .map((user) => `${user.username}(${user.calls})`)
                .join('、') || '—'}
            </Text>
          </Card>
        </Col>
      </Row>

      <Card
        title="调用明细"
        size="small"
        extra={
          <Space wrap>
            <Select
              allowClear
              placeholder="场景"
              style={{ width: 130 }}
              value={scene}
              onChange={(value) => {
                setPage(1)
                setScene(value)
              }}
              options={Object.entries(SCENE_META).map(([value, meta]) => ({
                value,
                label: meta.text,
              }))}
            />
            <Select
              allowClear
              placeholder="结果"
              style={{ width: 120 }}
              value={okFilter}
              onChange={(value) => {
                setPage(1)
                setOkFilter(value)
              }}
              options={[
                { value: true, label: '成功' },
                { value: false, label: '失败' },
              ]}
            />
            <DatePicker.RangePicker
              onChange={(value) => {
                setPage(1)
                setRange(value)
              }}
            />
            <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()} />
          </Space>
        }
      >
        <Table<AiUsageItemOut>
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={usage?.items ?? []}
          loading={isFetching}
          scroll={{ x: 1100 }}
          pagination={{
            current: page,
            pageSize: size,
            total: usage?.total ?? 0,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 次调用`,
            onChange: (nextPage, nextSize) => {
              setPage(nextPage)
              setSize(nextSize)
            },
          }}
        />
      </Card>
    </Flex>
  )
}
