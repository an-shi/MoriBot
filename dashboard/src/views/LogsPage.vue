<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { systemApi } from '@/api/system'
import type { SystemLogEntry } from '@/types/api'

const { t, locale } = useI18n()

const entries = ref<SystemLogEntry[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const level = ref('all')
const source = ref('all')
const query = ref('')
const autoRefresh = ref(true)
let refreshTimer: number | undefined

const levelItems = computed(() => [
  { title: t('logs.levelAll'), value: 'all' },
  { title: 'DEBUG', value: 'DEBUG' },
  { title: 'INFO', value: 'INFO' },
  { title: 'WARNING', value: 'WARNING' },
  { title: 'ERROR', value: 'ERROR' },
])

const sourceItems = computed(() => [
  { title: t('logs.sourceAll'), value: 'all' },
  { title: t('logs.sourceApp'), value: 'app' },
  { title: t('logs.sourceHttp'), value: 'http' },
])

const timeFormatter = computed(
  () =>
    new Intl.DateTimeFormat(locale.value, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }),
)

function formatTime(value: number): string {
  const date = new Date(value * 1000)
  return Number.isNaN(date.getTime()) ? '—' : timeFormatter.value.format(date)
}

function sourceLabel(value: string): string {
  return value === 'http' ? t('logs.sourceHttp') : t('logs.sourceApp')
}

async function loadLogs(silent = false): Promise<void> {
  if (!silent) {
    loading.value = true
  }
  errorMessage.value = ''
  try {
    const result = await systemApi.logs({
      level: level.value === 'all' ? undefined : level.value,
      source: source.value === 'all' ? undefined : source.value,
      q: query.value.trim() || undefined,
      limit: 300,
    })
    entries.value = result.entries
    total.value = result.total
  } catch (error) {
    errorMessage.value = `${t('logs.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

async function downloadLogs(): Promise<void> {
  try {
    const { blob, filename } = await systemApi.downloadLogs()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = `${t('logs.loadFailed')}: ${extractErrorMessage(error)}`
  }
}

watch([level, source], () => {
  void loadLogs()
})

onMounted(() => {
  void loadLogs()
  refreshTimer = window.setInterval(() => {
    if (autoRefresh.value && document.visibilityState === 'visible') {
      void loadLogs(true)
    }
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer !== undefined) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<template>
  <div class="logs-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('logs.eyebrow') }}</p>
        <h1>{{ t('logs.title') }}</h1>
        <p class="page-subtitle">{{ t('logs.subtitle') }}</p>
      </div>
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-download-outline"
        @click="downloadLogs"
      >
        {{ t('logs.download') }}
      </v-btn>
    </header>

    <section class="log-toolbar">
      <v-select
        v-model="level"
        :items="levelItems"
        :label="t('logs.level')"
        variant="outlined"
        density="compact"
        hide-details
        class="toolbar-select"
      />
      <v-select
        v-model="source"
        :items="sourceItems"
        :label="t('logs.source')"
        variant="outlined"
        density="compact"
        hide-details
        class="toolbar-select"
      />
      <v-text-field
        v-model="query"
        :placeholder="t('logs.searchPlaceholder')"
        variant="outlined"
        density="compact"
        hide-details
        prepend-inner-icon="mdi-magnify"
        clearable
        class="search-field"
        @keyup.enter="loadLogs()"
        @click:clear="loadLogs()"
      />
      <v-btn
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="loadLogs()"
      >
        {{ t('logs.refresh') }}
      </v-btn>
      <v-switch
        v-model="autoRefresh"
        color="primary"
        density="compact"
        hide-details
        :label="t('logs.autoRefresh')"
      />
    </section>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="logs-alert"
    >
      {{ errorMessage }}
    </v-alert>

    <div class="log-panel">
      <div class="log-panel-head">
        <span>{{ t('logs.count', { shown: entries.length, total }) }}</span>
        <span class="live-dot" :class="{ 'live-dot--on': autoRefresh }" />
      </div>

      <div class="log-columns">
        <span>{{ t('logs.tableTime') }}</span>
        <span>{{ t('logs.tableLevel') }}</span>
        <span>{{ t('logs.tableSource') }}</span>
        <span>{{ t('logs.tableModule') }}</span>
        <span>{{ t('logs.tableMessage') }}</span>
      </div>

      <div v-if="loading && entries.length === 0" class="log-empty">
        <v-progress-circular indeterminate size="20" width="2" />
      </div>

      <div v-else-if="entries.length === 0" class="log-empty">
        {{ t('logs.empty') }}
      </div>

      <div v-else class="log-rows">
        <div
          v-for="(entry, index) in entries"
          :key="`${entry.time}-${index}`"
          class="log-row"
        >
          <span class="log-time">{{ formatTime(entry.time) }}</span>
          <span class="log-level" :class="`log-level--${entry.level.toLowerCase()}`">
            {{ entry.level }}
          </span>
          <span class="log-source" :class="`log-source--${entry.source}`">
            {{ sourceLabel(entry.source) }}
          </span>
          <span class="log-module" :title="`${entry.module}:${entry.line}`">
            {{ entry.module || '—' }}<template v-if="entry.line">:{{ entry.line }}</template>
          </span>
          <span class="log-message">{{ entry.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.logs-page {
  width: 100%;
  max-width: 1480px;
  margin: 0 auto;
  padding: 34px clamp(20px, 3.2vw, 44px) 30px;
  animation: mori-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.page-head h1 {
  margin: 12px 0 0;
  color: var(--mori-text);
  font-size: clamp(28px, 3.2vw, 38px);
  font-weight: 600;
  letter-spacing: -0.045em;
}

.page-subtitle {
  margin: 12px 0 0;
  color: var(--mori-muted);
  font-size: 13.5px;
  line-height: 1.7;
}

.log-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
  padding: 12px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel);
}

.toolbar-select {
  max-width: 150px;
}

.search-field {
  min-width: 220px;
  flex: 1;
}

.log-toolbar :deep(.v-field) {
  border-radius: 10px;
  background: var(--mori-panel-2);
}

.logs-alert {
  margin-top: 14px;
  border-radius: 12px;
}

.log-panel {
  margin-top: 16px;
  overflow: hidden;
  border: 1px solid var(--mori-line);
  border-radius: 16px;
  background: var(--mori-panel);
}

.log-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--mori-line);
  color: var(--mori-muted);
  font-size: 10.5px;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--mori-muted);
}

.live-dot--on {
  background: var(--mori-mint);
  animation: mori-pulse 2.4s ease-in-out infinite;
}

.log-columns,
.log-row {
  display: grid;
  grid-template-columns: 134px 78px 70px 190px minmax(240px, 1fr);
  gap: 10px;
  align-items: start;
  padding: 8px 14px;
}

.log-columns {
  border-bottom: 1px solid var(--mori-line);
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.log-rows {
  max-height: calc(100vh - 360px);
  overflow-y: auto;
}

.log-row {
  border-bottom: 1px solid color-mix(in srgb, var(--mori-line) 60%, transparent);
  font-family: var(--mori-font-mono, ui-monospace, SFMono-Regular, Consolas, monospace);
  font-size: 10.5px;
  line-height: 1.55;
}

.log-row:last-child {
  border-bottom: 0;
}

.log-row:hover {
  background: var(--mori-panel-2);
}

.log-time {
  color: var(--mori-muted);
  white-space: nowrap;
}

.log-level {
  width: fit-content;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.log-level--debug {
  opacity: 0.7;
}

.log-level--info,
.log-level--success {
  color: var(--mori-mint);
  background: var(--mori-mint-soft);
}

.log-level--warning {
  color: #d49b3f;
  background: rgb(212 155 63 / 12%);
}

.log-level--error,
.log-level--critical {
  color: rgb(var(--v-theme-error));
  background: color-mix(in srgb, rgb(var(--v-theme-error)) 12%, transparent);
}

.log-source {
  color: var(--mori-muted);
  white-space: nowrap;
}

.log-source--http {
  color: var(--mori-mint);
}

.log-module {
  overflow: hidden;
  color: var(--mori-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-message {
  color: var(--mori-text);
  overflow-wrap: anywhere;
}

.log-empty {
  display: flex;
  min-height: 130px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--mori-muted);
  font-size: 11.5px;
}

@media (max-width: 900px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .log-columns {
    display: none;
  }

  .log-row {
    grid-template-columns: 1fr auto;
    gap: 4px 10px;
  }

  .log-time {
    grid-column: 1;
  }

  .log-level {
    grid-column: 2;
    grid-row: 1;
  }

  .log-source,
  .log-module {
    grid-column: 1 / -1;
  }

  .log-message {
    grid-column: 1 / -1;
  }
}
</style>
