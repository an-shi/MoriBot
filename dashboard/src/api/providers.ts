import { http } from './http'
import type {
  ApiResponse,
  ModelCapabilities,
  ModelProvider,
  ProviderCatalog,
  ProviderCategory,
  ProviderModelsResult,
  ProviderTestResult,
} from '@/types/api'

export interface ProviderPayload {
  category: ProviderCategory
  name: string
  provider_type: string
  base_url: string
  api_key: string
  model: string
  options: Record<string, unknown>
  capabilities?: ModelCapabilities
  is_default?: boolean
  enabled?: boolean
}

export type ProviderUpdatePayload = Partial<Omit<ProviderPayload, 'category'>>

export const providersApi = {
  async catalog(): Promise<ProviderCatalog> {
    const response = await http.get<ApiResponse<ProviderCatalog>>('/providers/catalog')
    return response.data.data
  },

  async fetchModels(payload: {
    provider_type: string
    category: ProviderCategory
    base_url: string
    api_key: string
    provider_id?: number
    options: Record<string, unknown>
  }): Promise<ProviderModelsResult> {
    const response = await http.post<ApiResponse<ProviderModelsResult>>(
      '/providers/models',
      payload,
    )
    return response.data.data
  },

  async list(): Promise<ModelProvider[]> {
    const response = await http.get<ApiResponse<ModelProvider[]>>('/providers')
    return response.data.data
  },

  async create(payload: ProviderPayload): Promise<ModelProvider> {
    const response = await http.post<ApiResponse<ModelProvider>>('/providers', payload)
    return response.data.data
  },

  async update(providerId: number, payload: ProviderUpdatePayload): Promise<ModelProvider> {
    const response = await http.patch<ApiResponse<ModelProvider>>(
      `/providers/${providerId}`,
      payload,
    )
    return response.data.data
  },

  async remove(providerId: number): Promise<void> {
    await http.delete<ApiResponse<Record<string, never>>>(`/providers/${providerId}`)
  },

  async setDefault(providerId: number): Promise<ModelProvider> {
    const response = await http.post<ApiResponse<ModelProvider>>(
      `/providers/${providerId}/default`,
    )
    return response.data.data
  },

  async test(providerId: number): Promise<ProviderTestResult> {
    const response = await http.post<ApiResponse<ProviderTestResult>>(
      `/providers/${providerId}/test`,
    )
    return response.data.data
  },
}
