import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { authApi } from '@/api/auth'
import type { User } from '@/types/api'
import { clearToken, getToken, setToken } from '@/utils/token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getToken())
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))

  async function login(
    username: string,
    password: string,
    remember = true,
  ): Promise<User> {
    loading.value = true
    try {
      const data = await authApi.login(username, password)
      token.value = data.access_token
      user.value = data.user
      setToken(data.access_token, remember)
      return data.user
    } finally {
      loading.value = false
    }
  }

  async function fetchMe(): Promise<User | null> {
    if (!getToken()) {
      return null
    }
    try {
      user.value = await authApi.me()
      token.value = getToken()
      return user.value
    } catch {
      clearSession()
      return null
    }
  }

  function clearSession(): void {
    token.value = null
    user.value = null
    clearToken()
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // A stale token should never trap the user in the dashboard.
    } finally {
      clearSession()
    }
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    login,
    fetchMe,
    logout,
    clearSession,
  }
})
