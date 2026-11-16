import { http } from './http'
import type { ApiResponse } from '@/types/api'

export interface MemorySpace {
  id: string
  kind: 'user' | 'character' | 'conversation' | string
  key: string
  name: string
  description: string
  user_id: string | null
  character_id: string | null
  conversation_id: string | null
  status: string
  memory_count?: number
  writable?: boolean
}

export interface MemoryItem {
  id: string
  space_id: string
  space: MemorySpace | null
  title: string
  content: string
  memory_type: string
  category: string
  source_kind: string
  status: string
  importance: number
  confidence: number
  reinforcement_count: number
  contradiction_count: number
  tags: string[]
  created_at: string
  updated_at: string
  evidence_count?: number
  relation_count?: number
}

export interface MemoryPage {
  items: MemoryItem[]
  total: number
  page: number
  per_page: number
}

export interface MemoryHealth {
  status: string
  service: string
  version: string
  database?: {
    ok?: boolean
    schema_version?: number
    fts5?: boolean
  }
  embedding?: {
    enabled?: boolean
    provider?: string
    model?: string
  }
}

export const memoryApi = {
  async health(): Promise<MemoryHealth> {
    const response = await http.get<MemoryHealth>('/memory/health')
    return response.data
  },

  async spaces(kind = 'character'): Promise<MemorySpace[]> {
    const response = await http.get<ApiResponse<{ items: MemorySpace[] }>>('/memory/spaces', {
      params: { kind },
    })
    return response.data.data.items
  },

  async memories(params: {
    space_id?: string
    q?: string
    page?: number
    per_page?: number
  }): Promise<MemoryPage> {
    const response = await http.get<ApiResponse<MemoryPage>>('/memory/memories', {
      params: {
        ...params,
        mode: 'manage',
        sort_by: 'updated_at',
        sort_order: 'desc',
      },
    })
    return response.data.data
  },

  async remove(memoryId: string): Promise<void> {
    await http.delete<ApiResponse<Record<string, never>>>(`/memory/memories/${memoryId}`)
  },
}
