<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLocale } from 'vuetify'
import { useRoute } from 'vue-router'

import { useThemeMode } from '@/composables/useThemeMode'

// Calling once at the application root applies the persisted theme before the
// first page renders.
useThemeMode()

const { t, locale } = useI18n()
const vuetifyLocale = useLocale()
const route = useRoute()

watch(
  locale,
  (value) => {
    vuetifyLocale.current.value = value === 'zh-CN' ? 'zhHans' : 'en'
    const titleKey = route.meta.titleKey
    document.title = titleKey ? `${t(titleKey)} · MoriBot` : 'MoriBot'
  },
  { immediate: true },
)
</script>

<template>
  <v-app>
    <router-view />
  </v-app>
</template>
