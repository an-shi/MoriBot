<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { setLocale, SUPPORTED_LOCALES, type AppLocale } from '@/i18n'

const { t, locale } = useI18n()

const options: Array<{ value: AppLocale; labelKey: string }> = SUPPORTED_LOCALES.map(
  (value) => ({
    value,
    labelKey: value === 'zh-CN' ? 'common.language.zh' : 'common.language.en',
  }),
)

function select(value: AppLocale): void {
  setLocale(value)
}
</script>

<template>
  <v-menu location="bottom end" :offset="8" transition="fade-transition">
    <template #activator="{ props }">
      <v-btn
        v-bind="props"
        icon
        variant="text"
        size="small"
        class="language-button"
        :aria-label="t('common.language.label')"
      >
        <v-icon size="18">mdi-translate</v-icon>
        <v-tooltip activator="parent" location="bottom">
          {{ t('common.language.label') }}
        </v-tooltip>
      </v-btn>
    </template>

    <v-list class="language-menu" density="compact">
      <v-list-item
        v-for="option in options"
        :key="option.value"
        :active="locale === option.value"
        class="language-item"
        @click="select(option.value)"
      >
        <v-list-item-title>{{ t(option.labelKey) }}</v-list-item-title>
        <template v-if="locale === option.value" #append>
          <v-icon size="16" color="primary">mdi-check</v-icon>
        </template>
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<style scoped>
.language-button {
  color: var(--mori-muted) !important;
}

.language-menu {
  min-width: 150px;
  border: 1px solid var(--mori-line);
  background: var(--mori-panel) !important;
  box-shadow: var(--mori-shadow);
}

.language-item :deep(.v-list-item-title) {
  font-size: 12.5px;
}
</style>
