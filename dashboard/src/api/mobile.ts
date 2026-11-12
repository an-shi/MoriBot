import { http } from './http'
import type { ApiResponse, MobileDevice, PairingCode } from '@/types/api'

export const mobileApi = {
  async createPairingCode(): Promise<PairingCode> {
    const response = await http.post<ApiResponse<PairingCode>>('/mobile/pairing-code')
    return response.data.data
  },

  async listDevices(): Promise<MobileDevice[]> {
    const response = await http.get<ApiResponse<MobileDevice[]>>('/mobile/devices')
    return response.data.data
  },

  async revokeDevice(deviceId: string): Promise<void> {
    await http.post<ApiResponse<Record<string, never>>>(
      `/mobile/devices/${encodeURIComponent(deviceId)}/revoke`,
    )
  },
}
