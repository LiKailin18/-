import { ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Descriptions, Flex, Tag, Typography } from 'antd'

import { fetchHealth } from '../api/health'

const { Paragraph, Text, Title } = Typography

/**
 * M0 的验收清单（写进页面便于自检与答辩演示）。
 * 这里只列目标、不写「已完成」状态 —— 真实状态以前面的健康卡片为准。
 */
const M0_CHECKLIST = [
  'FastAPI 应用可启动，GET /health 返回契约字段 {status, db, version}',
  '前端 Vite + React 19 + antd 6 可构建、可运行',
  '前端经 Vite 代理调通后端 /health（开发期不产生跨域）',
  'Alembic 异步迁移可生成并执行首个版本（含 pg_trgm 扩展）',
  'PostgreSQL 可用，/health 返回 status=ok、db=ok',
  'pytest 冒烟用例全部通过',
]

/**
 * M0 阶段的连通性自检页；M1 起被真实登录页替换。
 *
 * 实现说明：antd 6 已废弃 `List`（推荐改用虚拟滚动组件 `Listy`）。
 * 本页只是一段静态清单，直接用原生列表渲染即可；
 * 项目中的业务列表（资料/笔记/任务）一律使用 `Table`，分页与操作列更合适。
 * 同理 `Alert` 的 `message` 已改名 `title`，不要再用旧名。
 */
export default function HomePage() {
  const { data, isPending, isFetching, isError, error, refetch } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
  })

  const dbDown = data?.db === 'down'

  return (
    <Flex vertical gap={16} style={{ maxWidth: 880, margin: '0 auto', padding: 24 }}>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          智能学习系统
        </Title>
        <Text type="secondary">
          基于大语言模型的智能学习系统 · 毕业设计 · M0 环境骨架自检页
        </Text>
      </div>

      <Card
        title="后端连通性"
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={isFetching}
            onClick={() => void refetch()}
          >
            重新检测
          </Button>
        }
      >
        {isPending ? (
          <Text type="secondary">检测中…</Text>
        ) : isError ? (
          <Alert
            type="error"
            showIcon
            title="无法连接后端"
            description={
              <>
                <Paragraph style={{ marginBottom: 4 }}>
                  请确认后端已启动：
                  <Text code>
                    cd backend && .venv\Scripts\python -m uvicorn app.main:app --reload
                  </Text>
                </Paragraph>
                <Text type="secondary">
                  {error instanceof Error ? error.message : String(error)}
                </Text>
              </>
            }
          />
        ) : (
          <Descriptions
            column={1}
            size="small"
            items={[
              {
                key: 'status',
                label: '服务状态',
                children: (
                  <Tag color={data.status === 'ok' ? 'success' : 'warning'}>{data.status}</Tag>
                ),
              },
              {
                key: 'db',
                label: '数据库',
                children: <Tag color={data.db === 'ok' ? 'success' : 'error'}>{data.db}</Tag>,
              },
              { key: 'version', label: '后端版本', children: data.version },
            ]}
          />
        )}
      </Card>

      {dbDown && (
        <Alert
          type="warning"
          showIcon
          title="数据库未连接（接口已按契约返回 503）"
          description={
            <>
              <Paragraph style={{ marginBottom: 4 }}>
                本机尚未安装 PostgreSQL 或 Docker。启动数据库后重新检测即可变为{' '}
                <Text code>ok</Text>。
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                已装 Docker：
                <Text code>
                  powershell -ExecutionPolicy Bypass -File deploy\setup-db.ps1
                </Text>
                <br />
                已装 PostgreSQL：确认 <Text code>backend/.env</Text> 的{' '}
                <Text code>DATABASE_URL</Text> 与库名 <Text code>smart_learning</Text> 一致，
                并已执行 <Text code>alembic upgrade head</Text>
              </Paragraph>
            </>
          }
        />
      )}

      <Card title="M0 验收清单">
        <ol style={{ margin: 0, paddingLeft: 20 }}>
          {M0_CHECKLIST.map((item) => (
            <li key={item} style={{ marginBottom: 6 }}>
              <Text>{item}</Text>
            </li>
          ))}
        </ol>
      </Card>

      <Text type="secondary" style={{ fontSize: 12 }}>
        本页是环境自检页（/status），用于确认前后端与数据库连通（契约见 docs/api.md §1.6）。
        登录后可从顶部菜单进入。
      </Text>
    </Flex>
  )
}
