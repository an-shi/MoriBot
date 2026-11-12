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
