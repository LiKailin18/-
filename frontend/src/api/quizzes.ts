import type { Page, QuizAttemptOut, QuizBrief, QuizOut } from '../types/api'
import { api } from './client'

/** 测试题接口（契约：docs/api.md §11）—— 生成在 /ai/quizzes，其余在 /quizzes */

/** 见 `api/ai.ts` 的说明：生成类接口用 3 分钟超时，避开默认 15s */
const AI_GENERATE_TIMEOUT = 180_000

export interface QuizGeneratePayload {
  material_id: string
  title?: string | null
  count: number
  types: ('single' | 'multiple' | 'judge' | 'blank')[]
  difficulty: 'easy' | 'medium' | 'hard'
  scope_start?: number
  scope_end?: number | null
}

export async function generateQuiz(payload: QuizGeneratePayload): Promise<QuizOut> {
  const { data } = await api.post<QuizOut>('/ai/quizzes', payload, {
    timeout: AI_GENERATE_TIMEOUT,
  })
  return data
}

export async function listQuizzes(
  page = 1,
  size = 20,
  materialId?: string,
): Promise<Page<QuizBrief>> {
  const { data } = await api.get<Page<QuizBrief>>('/quizzes', {
    params: { page, size, material_id: materialId },
  })
  return data
}

/**
 * 取题目。
 *
 * `withAnswer=false` 时后端把 `answer` / `explanation` 置空 —— 做题时必须用它，
 * 否则答案提前出现在前端内存里（契约 §11 就是这么设计的）。
 */
export async function getQuiz(id: string, withAnswer = false): Promise<QuizOut> {
  const { data } = await api.get<QuizOut>(`/quizzes/${id}`, {
    params: { with_answer: withAnswer },
  })
  return data
}

export async function deleteQuiz(id: string): Promise<void> {
  await api.delete(`/quizzes/${id}`)
}

export async function submitAttempt(
  quizId: string,
  payload: { answers: { no: number; answer: string[] }[]; duration_seconds?: number | null },
): Promise<QuizAttemptOut> {
  const { data } = await api.post<QuizAttemptOut>(`/quizzes/${quizId}/attempts`, payload)
  return data
}

export async function listAttempts(
  quizId: string,
  page = 1,
  size = 20,
): Promise<Page<QuizAttemptOut>> {
  const { data } = await api.get<Page<QuizAttemptOut>>(`/quizzes/${quizId}/attempts`, {
    params: { page, size },
  })
  return data
}

export async function getAttempt(attemptId: string): Promise<QuizAttemptOut> {
  const { data } = await api.get<QuizAttemptOut>(`/attempts/${attemptId}`)
  return data
}
