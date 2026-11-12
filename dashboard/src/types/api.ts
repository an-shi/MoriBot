export interface ApiResponse<T> {
  status: 'ok' | 'error'
  message: string | null
  data: T
}

export interface User {
  id: number
  username: string
  display_name: string
  role: string
  last_login_at: string | null
}

export interface TokenData {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface PublicInfo {
  name: string
  version: string
  description: string
}

export interface SystemInfo {
  name: string
  version: string
  running: boolean
  started_at: string | null
  uptime_seconds: number
  providers: number
  platforms: number
  plugins: number
  mobile_online: number
  python_version: string
}

export interface PairingCode {
  code: string
  expires_at: string
  pairing_uri: string
  server_url: string
}

export interface MobileDevice {
  id: string
  name: string
  online: boolean
  created_at: string
  last_seen_at: string | null
  revoked_at: string | null
}

export type ProviderCategory = 'chat' | 'speech' | 'image'

export interface ModelCapabilities {
  input: string[]
  output: string[]
  tools: boolean
  reasoning: boolean
  context_window: number
  source?: string
}

export interface ProviderModelInfo {
  id: string
  name: string
  capabilities: ModelCapabilities
  owned_by: string
}

export interface ProviderModelsResult {
  models: ProviderModelInfo[]
  message: string
  manual_allowed: boolean
}

export interface ModelProvider {
  id: number
  category: ProviderCategory
  name: string
  provider_type: string
  base_url: string
  model: string
  options: Record<string, unknown>
  capabilities: ModelCapabilities
  is_default: boolean
  enabled: boolean
  api_key_set: boolean
  api_key_hint: string
  last_test_ok: boolean | null
  last_test_message: string
  last_tested_at: string | null
  created_at: string
  updated_at: string
}

export interface ProviderTestResult {
  ok: boolean
  message: string
  latency_ms: number
  preview: string
}

export interface ProviderTypeInfo {
  id: string
  name: string
  description: string
  categories: ProviderCategory[]
  default_base_url: string
  api_key_required: boolean
  docs_url: string
}

export interface ProviderPreset {
  id: string
  name: string
  provider_type: string
  categories: ProviderCategory[]
  base_url: string
  models: Partial<Record<ProviderCategory, string[]>>
  docs_url: string
  api_key_required: boolean
  voice: string
}

export interface ProviderCatalog {
  types: ProviderTypeInfo[]
  presets: ProviderPreset[]
}
