import { ref } from 'vue'
import { defineStore } from 'pinia'

import { systemApi } from '@/api/system'
import type { PublicInfo, SystemInfo } from '@/types/api'

export const useSystemStore = defineStore('system', () => {
  const publicInfo = ref<PublicInfo | null>(null)
  const info = ref<SystemInfo | null>(null)
  const loading = ref(false)

  async function fetchPublicInfo(): Promise<PublicInfo | null> {
    try {
      publicInfo.value = await systemApi.publicInfo()
      return publicInfo.value
    } catch {
      return null
    }
  }

  async function fetchInfo(): Promise<SystemInfo | null> {
    loading.value = true
    try {
      info.value = await systemApi.info()
      return info.value
    } catch {
      return null
    } finally {
      loading.value = false
    }
  }

  return { publicInfo, info, loading, fetchPublicInfo, fetchInfo }
})
