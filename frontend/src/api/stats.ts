import type {
  RecommendationsOut,
  StatsDailyOut,
  StatsOverviewOut,
  StatsSubjectsOut,
  WeakPointsOut,
} from '../types/api'
import { api } from './client'

/** 统计与个性化推荐（契约：docs/api.md §12） */

/** §12.1 学习概览（功能 11） */
export async function getStatsOverview(days = 7): Promise<StatsOverviewOut> {
  const { data } = await api.get<StatsOverviewOut>('/stats/overview', { params: { days } })
  return data
}

/** §12.1 每日趋势：不传日期则后端默认近 30 天，缺日补零 */
export async function getStatsDaily(dateFrom?: string, dateTo?: string): Promise<StatsDailyOut> {
  const { data } = await api.get<StatsDailyOut>('/stats/daily', {
    params: { date_from: dateFrom, date_to: dateTo },
  })
  return data
}

/** §12.1 科目分布 */
export async function getStatsSubjects(
  dateFrom?: string,
  dateTo?: string,
): Promise<StatsSubjectsOut> {
  const { data } = await api.get<StatsSubjectsOut>('/stats/subjects', {
    params: { date_from: dateFrom, date_to: dateTo },
  })
  return data
}

/** §12.1 薄弱知识点（后端会过滤样本太少的知识点） */
export async function getWeakPoints(days = 30, limit = 5): Promise<WeakPointsOut> {
  const { data } = await api.get<WeakPointsOut>('/stats/weak-points', {
    params: { days, limit },
  })
  return data
}

/** §12.2 个性化推荐（规则层，秒回，不消耗 AI 配额） */
export async function getRecommendations(limit = 5): Promise<RecommendationsOut> {
  const { data } = await api.get<RecommendationsOut>('/recommendations', { params: { limit } })
  return data
}
