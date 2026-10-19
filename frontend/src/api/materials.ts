import type { MaterialOut, MaterialTextOut, Page } from '../types/api'
import { api } from './client'

/** 学习资料接口（契约：docs/api.md §5） */

export interface ListMaterialsParams {
  page: number
  size: number
  keyword?: string
  subject?: string
  parse_status?: string
}

export async function listMaterials(params: ListMaterialsParams): Promise<Page<MaterialOut>> {
  const { data } = await api.get<Page<MaterialOut>>('/materials', { params })
  return data
}

export async function getMaterial(id: string): Promise<MaterialOut> {
  const { data } = await api.get<MaterialOut>(`/materials/${id}`)
  return data
}

/** 上传：FormData 的 Content-Type（含 boundary）由浏览器/axios 自动生成，不要手写 */
export async function uploadMaterial(
  file: File,
  extra: { title?: string; subject?: string; tags?: string } = {},
): Promise<MaterialOut> {
  const form = new FormData()
  form.append('file', file)
  if (extra.title) form.append('title', extra.title)
  if (extra.subject) form.append('subject', extra.subject)
  if (extra.tags) form.append('tags', extra.tags)

  const { data } = await api.post<MaterialOut>('/materials', form)
  return data
}

export async function updateMaterial(
  id: string,
  payload: { title?: string; subject?: string | null; tags?: string[] },
): Promise<MaterialOut> {
  const { data } = await api.patch<MaterialOut>(`/materials/${id}`, payload)
  return data
}

export async function deleteMaterial(id: string): Promise<void> {
  await api.delete(`/materials/${id}`)
}

export async function reparseMaterial(id: string): Promise<MaterialOut> {
  const { data } = await api.post<MaterialOut>(`/materials/${id}/reparse`)
  return data
}

export async function readMaterialText(
  id: string,
  offset = 0,
  limit = 4000,
): Promise<MaterialTextOut> {
  const { data } = await api.get<MaterialTextOut>(`/materials/${id}/text`, {
    params: { offset, limit },
  })
  return data
}

/** 下载必须带令牌，所以不能直接用 <a href>；这里取 blob 再触发保存 */
export async function downloadMaterial(id: string, fileName: string): Promise<void> {
  const { data } = await api.get<Blob>(`/materials/${id}/download`, { responseType: 'blob' })
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
