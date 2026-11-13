import { http } from './http'
import type {
  ApiResponse,
  ModelHealthRunResult,
  PublicInfo,
  SystemInfo,
  SystemLogsResult,
  SystemSettings,
} from '@/types/api'

export interface BackupDownload {
  blob: Blob
  filename: string
}

function parseFilename(disposition: string | undefined): string {
  if (!disposition) {
    return 'moribot-backup.zip'
  }
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      // Fall through to the plain filename form.
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  return plain || 'moribot-backup.zip'
}

export const systemApi = {
  async publicInfo(): Promise<PublicInfo> {
    const response = await http.get<ApiResponse<PublicInfo>>('/system/public')
    return response.data.data
  },

  async info(): Promise<SystemInfo> {
    const response = await http.get<ApiResponse<SystemInfo>>('/system/info')
    return response.data.data
  },

  async settings(): Promise<SystemSettings> {
    const response = await http.get<ApiResponse<SystemSettings>>('/system/settings')
    return response.data.data
  },

  async updateSettings(payload: {
    health_check: { enabled: boolean; times: string[] }
  }): Promise<SystemSettings> {
    const response = await http.patch<ApiResponse<SystemSettings>>('/system/settings', payload)
    return response.data.data
  },

  async runModelHealth(): Promise<ModelHealthRunResult> {
    const response = await http.post<ApiResponse<ModelHealthRunResult>>(
      '/system/model-health/run',
      undefined,
      { timeout: 300000 },
    )
    return response.data.data
  },

  async logs(params: {
    level?: string
    source?: string
    q?: string
    limit?: number
  }): Promise<SystemLogsResult> {
    const response = await http.get<ApiResponse<SystemLogsResult>>('/system/logs', {
      params,
    })
    return response.data.data
  },

  async downloadLogs(): Promise<BackupDownload> {
    const response = await http.get<Blob>('/system/logs/download', {
      responseType: 'blob',
      timeout: 60000,
    })
    return {
      blob: response.data,
      filename: parseFilename(response.headers['content-disposition'] as string | undefined),
    }
  },

  async exportBackup(): Promise<BackupDownload> {
    const response = await http.get<Blob>('/system/backup/export', {
      responseType: 'blob',
      timeout: 300000,
    })
    return {
      blob: response.data,
      filename: parseFilename(response.headers['content-disposition'] as string | undefined),
    }
  },
}
