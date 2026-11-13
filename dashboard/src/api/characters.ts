import { http } from './http'
import type {
  ApiResponse,
  CharacterAvatarResult,
  CharacterCard,
  CharacterPayload,
  CharacterUpdatePayload,
} from '@/types/api'

export const charactersApi = {
  async list(): Promise<CharacterCard[]> {
    const response = await http.get<ApiResponse<CharacterCard[]>>('/characters')
    return response.data.data
  },

  async create(payload: CharacterPayload): Promise<CharacterCard> {
    const response = await http.post<ApiResponse<CharacterCard>>('/characters', payload)
    return response.data.data
  },

  async update(characterId: number, payload: CharacterUpdatePayload): Promise<CharacterCard> {
    const response = await http.patch<ApiResponse<CharacterCard>>(
      `/characters/${characterId}`,
      payload,
    )
    return response.data.data
  },

  async remove(characterId: number): Promise<void> {
    await http.delete<ApiResponse<Record<string, never>>>(`/characters/${characterId}`)
  },

  async uploadAvatar(dataUrl: string): Promise<CharacterAvatarResult> {
    const response = await http.post<ApiResponse<CharacterAvatarResult>>('/characters/avatar', {
      data_url: dataUrl,
    })
    return response.data.data
  },
}
