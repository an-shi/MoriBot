import { http } from './http'
import type { ApiResponse, DiaryEntry } from '@/types/api'

export const diariesApi = {
  async list(params: {
    character_id?: number
    limit?: number
    offset?: number
  }): Promise<DiaryEntry[]> {
    const response = await http.get<ApiResponse<DiaryEntry[]>>('/diaries', { params })
    return response.data.data
  },

  async generate(characterId: number, date?: string): Promise<DiaryEntry> {
    const response = await http.post<ApiResponse<DiaryEntry>>(
      '/diaries/generate',
      { character_id: characterId, date: date || null },
      { timeout: 180000 },
    )
    return response.data.data
  },

  async remove(diaryId: number): Promise<void> {
    await http.delete<ApiResponse<Record<string, never>>>(`/diaries/${diaryId}`)
  },
}
