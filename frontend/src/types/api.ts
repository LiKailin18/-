/** 后端契约类型（docs/api.md）。M2 起由 openapi-typescript 自动生成，此处先手写。 */

export interface UserOut {
  id: string
  username: string
  email: string
  nickname: string | null
  avatar_url: string | null
  learning_goal: string | null
  daily_target_minutes: number
  role: 'user' | 'admin'
  created_at: string
}

export interface TokenOut {
  access_token: string
  token_type: string
  expires_in: number
  role: 'user' | 'admin'
}

export interface UserUpdateIn {
  email?: string
  nickname?: string | null
  avatar_url?: string | null
  learning_goal?: string | null
  daily_target_minutes?: number
}

export interface PasswordChangeIn {
  old_password: string
  new_password: string
}

/** 分页响应（契约 §1.2） */
export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export type ParseStatus = 'pending' | 'parsing' | 'success' | 'failed' | 'unsupported'

/** 学习资料（契约 §5，不含 extracted_text / file_path） */
export interface MaterialOut {
  id: string
  title: string
  subject: string | null
  tags: string[]
  file_name: string
  file_ext: string
  mime_type: string
  size_bytes: number
  page_count: number | null
  char_count: number | null
  parse_status: ParseStatus
  parse_error: string | null
  created_at: string
}

export interface MaterialTextOut {
  material_id: string
  offset: number
  limit: number
  total_chars: number
  has_more: boolean
  text: string
}

export interface AvatarOut {
  avatar_url: string
}

/** 笔记（契约 §6）：列表项不含正文，只给 excerpt */
export interface NoteListItem {
  id: string
  title: string
  excerpt: string
  tags: string[]
  material_id: string | null
  updated_at: string
}

export interface NoteOut {
  id: string
  title: string
  content: string
  tags: string[]
  material_id: string | null
  created_at: string
  updated_at: string
}

/* ---------------------------------------------------------------- 计划 / 任务 / 记录 */

export type PlanStatus = 'draft' | 'active' | 'done' | 'archived'
export type TaskStatus = 'pending' | 'doing' | 'done' | 'skipped'
export type RecordType = 'reading' | 'video' | 'practice' | 'review' | 'other'

export interface PlanProgress {
  task_total: number
  task_done: number
  progress: number
}

export interface PlanOut {
  id: string
  title: string
  subject: string | null
  goal: string | null
  start_date: string
  end_date: string
  daily_minutes: number
  status: PlanStatus
  material_ids: string[]
  created_at: string
  progress: PlanProgress
}

export interface MaterialBrief {
  id: string
  title: string
  subject: string | null
}

export interface PlanDetailOut extends PlanOut {
  materials: MaterialBrief[]
}

export interface GenerateTasksOut {
  plan_id: string
  created: number
  skipped: number
  dates: string[]
}

export interface TaskOut {
  id: string
  plan_id: string | null
  plan_date: string
  title: string
  description: string | null
  order_no: number
  est_minutes: number
  status: TaskStatus
  completed_at: string | null
  material_id: string | null
}

export interface TaskCompleteOut {
  task: TaskOut
  study_record_id: string | null
}

export interface RecordOut {
  id: string
  task_id: string | null
  material_id: string | null
  type: RecordType
  started_at: string
  duration_minutes: number
  content: string | null
  created_at: string
}

/* ---------------------------------------------------------------- AI 能力（功能 7–10） */

export type SummaryStyle = 'outline' | 'key_points' | 'detailed'

export interface SummaryOut {
  id: string
  material_id: string | null
  style: SummaryStyle
  mode: 'direct' | 'map_reduce'
  summary_md: string
  key_points: string[]
  char_count: number
  segments: number
  model: string
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number | null
  created_at: string
}

export interface SummaryBrief {
  id: string
  material_id: string | null
  style: SummaryStyle
  mode: string
  key_points: string[]
  char_count: number
  created_at: string
}

export interface QuizQuestionOut {
  no: number
  type: 'single' | 'multiple' | 'judge' | 'blank'
  stem: string
  options: string[]
  answer: string[] | null
  explanation: string | null
  difficulty: string
  knowledge: string
  source_hint: string | null
}

export interface QuizOut {
  id: string
  material_id: string | null
  title: string
  question_count: number
  types: string[]
  difficulty: string
  questions: QuizQuestionOut[]
  model: string
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number | null
  created_at: string
}

export interface QuizBrief {
  id: string
  material_id: string | null
  title: string
  question_count: number
  types: string[]
  difficulty: string
  created_at: string
}

export interface AttemptDetail {
  no: number
  your_answer: string[]
  correct_answer: string[]
  is_correct: boolean
  explanation: string | null
}

export interface QuizAttemptOut {
  id: string
  quiz_id: string
  score: number
  correct_count: number
  question_count: number
  duration_seconds: number | null
  created_at: string
  details: AttemptDetail[]
}

export interface AdviceSuggestionOut {
  title: string
  reason: string
  action: string
  priority: 'high' | 'medium' | 'low'
}

export interface AdviceOut {
  id: string
  period_days: number
  focus: 'review' | 'plan' | 'balance'
  summary: string
  suggestions: AdviceSuggestionOut[]
  weak_points: { knowledge: string; attempts: number; correct: number; accuracy: number }[]
  next_7_days: { date: string; minutes: number; focus: string }[]
  stale: boolean
  model: string
  latency_ms: number | null
  created_at: string
}

export interface ChatSessionOut {
  id: string
  title: string
  material_id: string | null
  message_count: number
  last_message_at: string | null
  created_at: string
}

export interface ChatMessageOut {
  id: string
  role: 'user' | 'assistant'
  content: string
  tool_calls: { name: string; args?: unknown }[] | null
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number | null
  created_at: string
}

export interface UsageOut {
  days: number
  today_calls: number
  daily_quota: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  success_rate: number
  items: { date: string; calls: number; total_tokens: number }[]
}

/* ---------------------------------------------------------------- 统计与推荐（功能 11 / 功能 10） */

export interface StatsPeriod {
  from: string
  to: string
  days: number
}

export interface StatsOverviewOut {
  period: StatsPeriod
  total_minutes: number
  active_days: number
  streak_days: number
  daily_avg_minutes: number
  task_total: number
  task_done: number
  task_completion_rate: number
  quiz_attempts: number
  quiz_accuracy: number
  materials: number
  notes: number
  ai_calls: number
}

export interface StatsDailyItem {
  date: string
  minutes: number
  task_total: number
  task_done: number
  quiz_attempts: number
  quiz_accuracy: number
}

export interface StatsDailyOut {
  items: StatsDailyItem[]
}

export interface SubjectStatItem {
  subject: string
  minutes: number
  task_done: number
}

export interface StatsSubjectsOut {
  items: SubjectStatItem[]
}

export interface WeakPointItem {
  knowledge: string
  attempts: number
  correct: number
  accuracy: number
}

export interface WeakPointsOut {
  items: WeakPointItem[]
}

export type RecommendationKind = 'task' | 'review' | 'plan' | 'material' | 'habit'

export interface RecommendationItem {
  kind: RecommendationKind
  priority: number
  title: string
  reason: string
  action: string
  route: string
  ref_id: string | null
}

export interface RecommendationsOut {
  generated_at: string
  items: RecommendationItem[]
}

/* ---------------------------------------------------------------- 功能 13 管理端 */

export type UserRole = 'user' | 'admin'

export interface AdminRangeOut {
  from: string
  to: string
  days: number
}

export interface AdminOverviewOut {
  range: AdminRangeOut
  users: { total: number; active_7d: number; new_7d: number; disabled: number; admins: number }
  content: { materials: number; notes: number; plans: number; quizzes: number }
  activity: { study_minutes: number; task_completion_rate: number }
  ai: { calls: number; total_tokens: number; success_rate: number; today_calls: number }
}

export interface AdminDailyItemOut {
  date: string
  new_users: number
  active_users: number
  study_minutes: number
  ai_calls: number
}

export interface AdminDailyOut {
  items: AdminDailyItemOut[]
}

export interface SceneStatOut {
  scene: string
  calls: number
  total_tokens: number
  success_rate: number
  avg_latency_ms: number
}

export interface TopUserOut {
  user_id: string
  username: string
  calls: number
  total_tokens: number
}

export interface AdminAiStatsOut {
  by_scene: SceneStatOut[]
  top_users: TopUserOut[]
  daily: { date: string; calls: number; total_tokens: number; failed: number }[]
}

export interface AdminUserCountsOut {
  materials: number
  notes: number
  ai_calls_30d: number
  study_minutes_30d: number
}

export interface AdminUserItemOut {
  id: string
  username: string
  email: string
  nickname: string | null
  role: UserRole
  is_active: boolean
  disabled_reason: string | null
  created_at: string
  last_login_at: string | null
  counts: AdminUserCountsOut
}

export interface AdminUserDetailOut extends AdminUserItemOut {
  quiz_accuracy_30d: number
  quiz_attempts_30d: number
  ai_tokens_30d: number
}

export interface AdminUserPage {
  items: AdminUserItemOut[]
  total: number
  page: number
  size: number
}

export interface ResetPasswordOut {
  temporary_password: string
  note: string
}

export interface AdminMaterialItemOut {
  id: string
  title: string
  subject: string | null
  file_ext: string
  size_bytes: number
  parse_status: string
  char_count: number | null
  created_at: string
  owner: { id: string; username: string }
}

export interface AdminMaterialPage {
  items: AdminMaterialItemOut[]
  total: number
  page: number
  size: number
}

export interface AdminNoteItemOut {
  id: string
  title: string
  excerpt: string
  tags: string[]
  material_id: string | null
  created_at: string
  updated_at: string
  owner: { id: string; username: string }
}

export interface AdminNotePage {
  items: AdminNoteItemOut[]
  total: number
  page: number
  size: number
}

export interface AdminQuizItemOut {
  id: string
  title: string
  question_count: number
  types: string[]
  difficulty: string
  material_id: string | null
  created_at: string
  owner: { id: string; username: string }
}

export interface AdminQuizPage {
  items: AdminQuizItemOut[]
  total: number
  page: number
  size: number
}

export interface AiUsageItemOut {
  id: string
  user: { id: string; username: string }
  scene: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  steps: number
  latency_ms: number | null
  ok: boolean
  error_code: string | null
  created_at: string
}

export interface AiUsagePage {
  items: AiUsageItemOut[]
  total: number
  page: number
  size: number
}

export interface SettingItemOut {
  key: string
  value: unknown
  value_type: 'int' | 'bool' | 'string' | 'json'
  description: string
  editable: boolean
  updated_at: string | null
  updated_by_username: string | null
}

export interface AuditLogOut {
  id: string
  admin: { id: string; username: string } | null
  action: string
  target_type: string
  target_id: string | null
  detail: Record<string, unknown>
  ip: string | null
  created_at: string
}

export interface AuditLogPage {
  items: AuditLogOut[]
  total: number
  page: number
  size: number
}
