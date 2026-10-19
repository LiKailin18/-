import {
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntdApp,
  Button,
  Card,
  Checkbox,
  Flex,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'

import { toApiError } from '../../api/client'
import {
  deleteQuiz,
  generateQuiz,
  getAttempt,
  getQuiz,
  listAttempts,
  listQuizzes,
  submitAttempt,
} from '../../api/quizzes'
import type { AttemptDetail, QuizAttemptOut, QuizBrief, QuizOut, QuizQuestionOut } from '../../types/api'
import { useMaterialOptions } from './useMaterialOptions'

const { Text } = Typography

type QuizType = 'single' | 'multiple' | 'judge' | 'blank'

const TYPE_TEXT: Record<QuizType, string> = {
  single: '单选',
  multiple: '多选',
  judge: '判断',
  blank: '填空',
}

const TYPE_OPTIONS = (Object.keys(TYPE_TEXT) as QuizType[]).map((key) => ({
  value: key,
  label: TYPE_TEXT[key],
}))

const DIFFICULTY_META: Record<string, { text: string; color: string }> = {
  easy: { text: '简单', color: 'green' },
  medium: { text: '中等', color: 'gold' },
  hard: { text: '困难', color: 'red' },
}

interface GenerateForm {
  material_id: string
  count: number
  types: QuizType[]
  difficulty: 'easy' | 'medium' | 'hard'
  title?: string
}

/** 单题的作答控件：按题型换控件，value 始终是「选项原文的数组」。 */
function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: QuizQuestionOut
  value: string[]
  onChange: (next: string[]) => void
}) {
  if (question.type === 'multiple') {
    return (
      <Checkbox.Group
        value={value}
        onChange={(next) => onChange(next as string[])}
        options={question.options.map((option) => ({ value: option, label: option }))}
        style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
      />
    )
  }
  if (question.type === 'blank') {
    return (
      <Input
        value={value[0] ?? ''}
        onChange={(event) => onChange([event.target.value])}
        placeholder="填写答案"
        style={{ maxWidth: 320 }}
      />
    )
  }
  return (
    <Radio.Group
      value={value[0]}
      onChange={(event) => onChange([event.target.value as string])}
      options={question.options.map((option) => ({ value: option, label: option }))}
      style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
    />
  )
}

/** 测试题（功能 9）：生成、答题、交卷判分、历史成绩。 */
export default function QuizTab() {
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const { options: materialOptions, titleOf } = useMaterialOptions()

  const [generateOpen, setGenerateOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [form] = Form.useForm<GenerateForm>()

  const [taking, setTaking] = useState<QuizOut | null>(null)
  const [answers, setAnswers] = useState<Record<number, string[]>>({})
  const [startedAt, setStartedAt] = useState<number>(0)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<QuizAttemptOut | null>(null)
  const [resultTitle, setResultTitle] = useState('答题结果')

  const [historyQuiz, setHistoryQuiz] = useState<QuizBrief | null>(null)

  const { data: page, isFetching, refetch } = useQuery({
    queryKey: ['quizzes'],
    queryFn: () => listQuizzes(1, 50),
  })
  const quizzes = page?.items ?? []

  const { data: attemptsPage, isFetching: loadingAttempts } = useQuery({
    queryKey: ['quiz-attempts', historyQuiz?.id],
    queryFn: () => listAttempts(historyQuiz?.id as string, 1, 50),
    enabled: Boolean(historyQuiz),
  })

  const handleGenerate = async () => {
    const values = await form.validateFields()
    setGenerating(true)
    try {
      const quiz = await generateQuiz({
        material_id: values.material_id,
        title: values.title || null,
        count: values.count,
        types: values.types,
        difficulty: values.difficulty,
      })
      message.success(`已生成 ${quiz.question_count} 道题`)
      setGenerateOpen(false)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['quizzes'] }),
        queryClient.invalidateQueries({ queryKey: ['ai-usage'] }),
      ])
      // 生成完直接进入答题
      setTaking(await getQuiz(quiz.id, false))
      setAnswers({})
      setStartedAt(Date.now())
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setGenerating(false)
    }
  }

  const startQuiz = async (quiz: QuizBrief) => {
    try {
      setTaking(await getQuiz(quiz.id, false))
      setAnswers({})
      setResult(null)
      setStartedAt(Date.now())
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const handleSubmit = async () => {
    if (!taking) return
    const answered = Object.entries(answers).filter(([, value]) => value.length > 0)
    const missing = taking.questions.length - answered.length
    if (missing > 0) {
      message.warning(`还有 ${missing} 题未作答，题干没写的会按错误计分`)
    }

    setSubmitting(true)
    try {
      const attempt = await submitAttempt(taking.id, {
        answers: answered.map(([no, value]) => ({ no: Number(no), answer: value })),
        duration_seconds: Math.max(1, Math.round((Date.now() - startedAt) / 1000)),
      })
      setResult(attempt)
      setResultTitle(`得分 ${attempt.score.toFixed(0)} 分`)
      setTaking(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['quizzes'] }),
        queryClient.invalidateQueries({ queryKey: ['quiz-attempts'] }),
        queryClient.invalidateQueries({ queryKey: ['ai-usage'] }),
      ])
    } catch (error) {
      message.error(toApiError(error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (quiz: QuizBrief) => {
    try {
      await deleteQuiz(quiz.id)
      message.success('已删除')
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const openAttempt = async (attemptId: string) => {
    try {
      const attempt = await getAttempt(attemptId)
      setResultTitle('历史答卷')
      setResult(attempt)
      setHistoryQuiz(null)
    } catch (error) {
      message.error(toApiError(error).message)
    }
  }

  const stemOf = (no: number) =>
    taking?.questions.find((item) => item.no === no)?.stem ?? `第 ${no} 题`

  const detailColumns: TableProps<AttemptDetail>['columns'] = [
    { title: '题号', dataIndex: 'no', width: 60 },
    {
      title: '题目',
      render: (_, record) => <Text style={{ fontSize: 13 }}>{stemOf(record.no)}</Text>,
    },
    {
      title: '你的答案',
      width: 160,
      render: (_, record) => (
        <Text type={record.is_correct ? 'success' : 'danger'}>
          {record.your_answer.length ? record.your_answer.join(' / ') : '（未作答）'}
        </Text>
      ),
    },
    {
      title: '正确答案',
      width: 160,
      render: (_, record) => <Text>{record.correct_answer.join(' / ')}</Text>,
    },
    {
      title: '结果',
      width: 80,
      render: (_, record) => (
        <Tag color={record.is_correct ? 'success' : 'error'}>{record.is_correct ? '对' : '错'}</Tag>
      ),
    },
    {
      title: '解析',
      width: 240,
      render: (_, record) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {record.explanation ?? '—'}
        </Text>
      ),
    },
  ]

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap align="center">
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={() => {
            form.setFieldsValue({ count: 5, types: ['single'], difficulty: 'medium' })
            setGenerateOpen(true)
          }}
        >
          生成测试题
        </Button>
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => void refetch()}>
          刷新
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          列表不含答案；进入答题后才向服务端取题干（答案不下发到浏览器）
        </Text>
      </Flex>

      <Table<QuizBrief>
        rowKey="id"
        size="small"
        loading={isFetching}
        dataSource={quizzes}
        pagination={false}
        locale={{ emptyText: '还没有测试题，先生成一份' }}
        columns={[
          {
            title: '试卷',
            render: (_, quiz) => (
              <Space size={6} wrap>
                <Text strong>{quiz.title}</Text>
                <Tag color={DIFFICULTY_META[quiz.difficulty]?.color}>
                  {DIFFICULTY_META[quiz.difficulty]?.text ?? quiz.difficulty}
                </Tag>
                {quiz.types.map((type) => (
                  <Tag key={type}>{TYPE_TEXT[type as QuizType] ?? type}</Tag>
                ))}
              </Space>
            ),
          },
          {
            title: '资料',
            width: 160,
            render: (_, quiz) => titleOf(quiz.material_id),
          },
          {
            title: '题数 / 创建时间',
            width: 210,
            render: (_, quiz) => (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {quiz.question_count} 题 · {dayjs(quiz.created_at).format('YYYY-MM-DD HH:mm')}
              </Text>
            ),
          },
          {
            title: '操作',
            width: 200,
            render: (_, quiz) => (
              <Space size={4} wrap>
                <Button
                  size="small"
                  type="link"
                  icon={<EditOutlined />}
                  onClick={() => void startQuiz(quiz)}
                >
                  答题
                </Button>
                <Button
                  size="small"
                  type="link"
                  icon={<HistoryOutlined />}
                  onClick={() => {
                    setResult(null)
                    setHistoryQuiz(quiz)
                  }}
                >
                  成绩
                </Button>
                <Popconfirm
                  title="删除这套题？"
                  okText="删除"
                  okButtonProps={{ danger: true }}
                  cancelText="取消"
                  onConfirm={() => void handleDelete(quiz)}
                >
                  <Button size="small" type="link" danger icon={<DeleteOutlined />}>
                    删除
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      {/* 生成测试题 */}
      <Modal
        open={generateOpen}
        title="生成测试题"
        okText="生成并开始答题"
        cancelText="取消"
        confirmLoading={generating}
        onCancel={() => setGenerateOpen(false)}
        onOk={() => void handleGenerate()}
        destroyOnHidden
      >
        <Form<GenerateForm>
          form={form}
          layout="vertical"
          requiredMark={false}
          initialValues={{ count: 5, types: ['single'], difficulty: 'medium' }}
        >
          <Form.Item name="material_id" label="资料" rules={[{ required: true, message: '请选择资料' }]}>
            <Select showSearch optionFilterProp="label" placeholder="选择资料" options={materialOptions} />
          </Form.Item>
          <Form.Item name="title" label="标题（可选）">
            <Input maxLength={200} placeholder="不填则自动命名" />
          </Form.Item>
          <Flex gap={12}>
            <Form.Item name="count" label="题目数量" style={{ flex: 1 }}>
              <InputNumber min={1} max={20} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="difficulty" label="难度" style={{ flex: 1 }}>
              <Select
                options={Object.entries(DIFFICULTY_META).map(([value, meta]) => ({
                  value,
                  label: meta.text,
                }))}
              />
            </Form.Item>
          </Flex>
          <Form.Item
            name="types"
            label="题型（可多选）"
            rules={[{ required: true, message: '至少选一种题型' }]}
          >
            <Checkbox.Group options={TYPE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 答题 */}
      <Modal
        open={Boolean(taking)}
        title={taking?.title}
        width={760}
        okText="交卷"
        cancelText="放弃"
        confirmLoading={submitting}
        onCancel={() => setTaking(null)}
        onOk={() => void handleSubmit()}
        destroyOnHidden
      >
        {taking && (
          <Flex vertical gap={16} style={{ maxHeight: '60vh', overflowY: 'auto' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {taking.questions.length} 题
              {taking.types.length ? ` · ${taking.types.map((t) => TYPE_TEXT[t as QuizType] ?? t).join('/')}` : ''}
              （多选必须全对才得分；填空忽略大小写与首尾空格）
            </Text>
            {taking.questions.map((question) => (
              <Card key={question.no} size="small" title={`第 ${question.no} 题 · ${TYPE_TEXT[question.type]}`}>
                <Flex vertical gap={8}>
                  <Text style={{ whiteSpace: 'pre-wrap' }}>{question.stem}</Text>
                  <QuestionInput
                    question={question}
                    value={answers[question.no] ?? []}
                    onChange={(next) => setAnswers((prev) => ({ ...prev, [question.no]: next }))}
                  />
                </Flex>
              </Card>
            ))}
          </Flex>
        )}
      </Modal>

      {/* 成绩 */}
      <Modal
        open={Boolean(result)}
        title={resultTitle}
        width={900}
        footer={
          <Button type="primary" onClick={() => setResult(null)}>
            关闭
          </Button>
        }
        onCancel={() => setResult(null)}
        destroyOnHidden
      >
        {result && (
          <Flex vertical gap={12}>
            <Space size={24} wrap>
              <Progress
                type="circle"
                size={90}
                percent={Math.round(result.score)}
                format={(percent) => `${percent} 分`}
              />
              <Space orientation="vertical" size={2}>
                <Text>
                  答对 {result.correct_count} / {result.question_count} 题
                </Text>
                {result.duration_seconds != null && (
                  <Text type="secondary">用时 {Math.round(result.duration_seconds / 60)} 分钟</Text>
                )}
                <Text type="secondary">{dayjs(result.created_at).format('YYYY-MM-DD HH:mm')}</Text>
              </Space>
            </Space>

            {result.details.length > 0 ? (
              <Table<AttemptDetail>
                rowKey="no"
                size="small"
                columns={detailColumns}
                dataSource={result.details}
                pagination={false}
                scroll={{ x: 780, y: 320 }}
              />
            ) : (
              <Text type="secondary">这份答卷没有逐题明细（历史列表接口不返回明细）</Text>
            )}
          </Flex>
        )}
      </Modal>

      {/* 成绩历史 */}
      <Modal
        open={Boolean(historyQuiz)}
        title={`答卷记录 · ${historyQuiz?.title ?? ''}`}
        width={640}
        footer={null}
        onCancel={() => setHistoryQuiz(null)}
        destroyOnHidden
      >
        <Table<QuizAttemptOut>
          rowKey="id"
          size="small"
          loading={loadingAttempts}
          dataSource={attemptsPage?.items ?? []}
          pagination={false}
          locale={{ emptyText: '还没有答卷' }}
          columns={[
            {
              title: '得分',
              dataIndex: 'score',
              width: 100,
              render: (score: number) => <Text strong>{score.toFixed(0)} 分</Text>,
            },
            {
              title: '正确 / 总题',
              width: 120,
              render: (_, attempt) => `${attempt.correct_count} / ${attempt.question_count}`,
            },
            {
              title: '用时',
              width: 110,
              render: (_, attempt) =>
                attempt.duration_seconds != null
                  ? `${Math.round(attempt.duration_seconds / 60)} 分钟`
                  : '—',
            },
            {
              title: '提交时间',
              width: 170,
              render: (_, attempt) => dayjs(attempt.created_at).format('YYYY-MM-DD HH:mm'),
            },
            {
              title: '',
              width: 110,
              render: (_, attempt) => (
                <Button size="small" type="link" onClick={() => void openAttempt(attempt.id)}>
                  查看明细
                </Button>
              ),
            },
          ]}
        />
      </Modal>

    </Flex>
  )
}
