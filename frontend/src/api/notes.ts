import type { NoteListItem, NoteOut, Page } from '../types/api'
import { api } from './client'

/** 在线笔记接口（契约：docs/api.md §6） */

export interface ListNotesParams {
  page: number
  size: number
  keyword?: string
  material_id?: string
  tag?: string
}

export interface NotePayload {
  title: string
  content: string
  tags: string[]
  material_id?: string | null
}

export async function listNotes(params: ListNotesParams): Promise<Page<NoteListItem>> {
  const { data } = await api.get<Page<NoteListItem>>('/notes', { params })
  return data
}

export async function getNote(id: string): Promise<NoteOut> {
  const { data } = await api.get<NoteOut>(`/notes/${id}`)
  return data
}

export async function createNote(payload: NotePayload): Promise<NoteOut> {
  const { data } = await api.post<NoteOut>('/notes', payload)
  return data
}

export async function updateNote(id: string, payload: NotePayload): Promise<NoteOut> {
  const { data } = await api.patch<NoteOut>(`/notes/${id}`, payload)
  return data
}

export async function deleteNote(id: string): Promise<void> {
  await api.delete(`/notes/${id}`)
}
