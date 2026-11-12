import axios from 'axios'

import { getLocale, i18n } from '@/i18n'
import { clearToken, getToken } from '@/utils/token'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 20000,
  headers: {
    'Content-Type': 'application/json',
  },
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers['Accept-Language'] = getLocale()
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const url = String(error?.config?.url || '')
    const isLoginRequest = url.includes('/auth/login')

    if (status === 401 && !isLoginRequest) {
      clearToken()
      if (!window.location.pathname.startsWith('/login')) {
        const redirect = encodeURIComponent(
          `${window.location.pathname}${window.location.search}`,
        )
        window.location.replace(`/login?redirect=${redirect}`)
      }
    }

    return Promise.reject(error)
  },
)

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const message = error.response?.data?.message
    if (typeof message === 'string' && message.trim()) {
      return message
    }
    if (error.code === 'ECONNABORTED') {
      return i18n.global.t('errors.timeout')
    }
    if (!error.response) {
      return i18n.global.t('errors.offline')
    }
    return error.message || i18n.global.t('errors.requestFailed')
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error || i18n.global.t('errors.requestFailed'))
}
