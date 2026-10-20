import { Card, Flex, Tabs, Typography } from 'antd'
import { useSearchParams } from 'react-router'

import PlanTab from './plans/PlanTab'
import RecordTab from './plans/RecordTab'
import TaskTab from './plans/TaskTab'

const { Text, Title } = Typography

const TAB_KEYS = ['plans', 'tasks', 'records'] as const

/**
 * 学习计划（功能 5 / 6 / 12）：计划、每日任务、学习记录三个视角放在一个页面里。
 *
 * Tab 与地址栏同步（`/plans?tab=tasks`）—— 工作台的推荐按钮要能直接跳到具体 Tab。
 */
export default function PlansPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const activeKey = TAB_KEYS.includes(requested as (typeof TAB_KEYS)[number])
    ? (requested as string)
    : 'plans'

  return (
    <Flex vertical gap={16} style={{ maxWidth: 1280, margin: '0 auto', width: '100%' }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          学习计划
        </Title>
        <Text type="secondary">
          计划区间内可一键生成每日任务；完成任务会自动记入学习时长（统计与推荐的数据源）
        </Text>
      </div>

      <Card>
        <Tabs
          activeKey={activeKey}
          onChange={(key) => setParams(key === 'plans' ? {} : { tab: key }, { replace: true })}
          items={[
            { key: 'plans', label: '我的计划', children: <PlanTab /> },
            { key: 'tasks', label: '每日任务', children: <TaskTab /> },
            { key: 'records', label: '学习记录', children: <RecordTab /> },
          ]}
        />
      </Card>
    </Flex>
  )
}
