<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { providersApi } from '@/api/providers'
import { systemApi } from '@/api/system'
import MobilePairingDialog from '@/components/MobilePairingDialog.vue'
import MoriLogo from '@/components/MoriLogo.vue'
import { APP_VERSION } from '@/config'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import type { ModelProvider, ProviderCategory } from '@/types/api'
import { formatDateTime, formatUptime } from '@/utils/format'

const system = useSystemStore()
const auth = useAuthStore()
const { t, locale } = useI18n()

const mobileDialogOpen = ref(false)
const exporting = ref(false)
const snackbar = ref({ show: false, message: '', color: 'success' })

const providers = ref<ModelProvider[]>([])
const providersLoading = ref(true)
const providersError = ref('')
let refreshTimer: number | undefined

const categoryIcons: Record<ProviderCategory, string> = {
  chat: 'mdi-robot-outline',
  speech: 'mdi-volume-high',
  image: 'mdi-image-outline',
}

const healthSummary = computed(() => {
  const total = providers.value.length
  const available = providers.value.filter((provider) => provider.last_test_ok === true).length
  const failed = providers.value.filter((provider) => provider.last_test_ok === false).length
  return { total, available, failed, untested: total - available - failed }
})

function healthState(provider: ModelProvider): 'available' | 'unavailable' | 'untested' {
  if (provider.last_test_ok === null) {
    return 'untested'
  }
  return provider.last_test_ok ? 'available' : 'unavailable'
}

function healthLabel(provider: ModelProvider): string {
  return t(`home.health.${healthState(provider)}`)
}

function healthTime(provider: ModelProvider): string {
  if (!provider.last_tested_at) {
    return t('home.health.neverChecked')
  }
  return t('home.health.checkedAt', {
    time: formatDateTime(provider.last_tested_at, locale.value, t('home.health.neverChecked')),
  })
}

async function loadProviders(silent = false): Promise<void> {
  if (!silent) {
    providersLoading.value = true
  }
  providersError.value = ''
  try {
    providers.value = await providersApi.list()
  } catch (error) {
    providersError.value = `${t('home.health.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    if (!silent) {
      providersLoading.value = false
    }
  }
}

const displayName = computed(
  () => auth.user?.display_name || auth.user?.username || t('layout.roleAdmin'),
)
const version = computed(() => system.info?.version || APP_VERSION)
const uptime = computed(() =>
  formatUptime(system.info?.uptime_seconds, locale.value, t('units.justStarted')),
)
const coreRunning = computed(() => Boolean(system.info?.running))

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

async function exportData(): Promise<void> {
  exporting.value = true
  try {
    const { blob, filename } = await systemApi.exportBackup()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    showSnackbar(t('home.exportSuccess'), 'success')
  } catch (error) {
    showSnackbar(`${t('home.exportFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  void loadProviders()
  refreshTimer = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      void loadProviders(true)
    }
  }, 60000)
})

onUnmounted(() => {
  if (refreshTimer !== undefined) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<template>
  <div class="home-page">
    <header class="page-head">
      <div class="head-copy">
        <p class="mori-eyebrow">{{ t('home.overview') }}</p>
        <h1>{{ t('home.greeting', { name: displayName }) }}</h1>
        <p class="head-subtitle">{{ t('home.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <button class="docs-link" type="button" @click="mobileDialogOpen = true">
          <v-icon size="15">mdi-cellphone-link</v-icon>
          {{ t('home.mobilePairing') }}
        </button>
        <button class="docs-link" type="button" :disabled="exporting" @click="exportData">
          <v-icon size="15">mdi-download-outline</v-icon>
          {{ exporting ? t('home.exporting') : t('home.exportData') }}
        </button>
        <a class="docs-link" href="/api/docs" target="_blank" rel="noopener">
          <v-icon size="15">mdi-api</v-icon>
          {{ t('home.apiDocs') }}
          <v-icon size="13">mdi-open-in-new</v-icon>
        </a>
        <span class="status-chip" :class="{ 'status-chip--live': coreRunning }">
          <i />
          {{ coreRunning ? t('home.running') : t('home.waiting') }}
        </span>
      </div>
    </header>

    <section class="runtime-strip" :aria-label="t('home.runtimeOverview')">
      <div class="runtime-item">
        <span class="runtime-label">{{ t('home.version') }}</span>
        <strong>v{{ version }}</strong>
      </div>
      <div class="runtime-item">
        <span class="runtime-label">{{ t('home.uptime') }}</span>
        <strong>{{ uptime }}</strong>
      </div>
      <div class="runtime-item">
        <span class="runtime-label">{{ t('home.providers') }}</span>
        <strong>{{ system.info?.providers ?? 0 }}</strong>
      </div>
      <div class="runtime-item">
        <span class="runtime-label">{{ t('home.mobileOnline') }}</span>
        <strong>{{ system.info?.mobile_online ?? 0 }}</strong>
      </div>
    </section>

    <section class="model-health" :aria-label="t('home.modelHealth')">
      <header class="health-head">
        <div>
          <p class="mori-eyebrow">MODEL HEALTH</p>
          <h2>{{ t('home.modelHealth') }}</h2>
          <p class="health-subtitle">{{ t('home.modelHealthDesc') }}</p>
        </div>
        <div class="health-actions">
          <span class="health-summary">
            {{
              t('home.health.summary', {
                total: healthSummary.total,
                available: healthSummary.available,
                failed: healthSummary.failed,
                untested: healthSummary.untested,
              })
            }}
          </span>
          <v-btn
            variant="text"
            size="small"
            prepend-icon="mdi-refresh"
            :loading="providersLoading"
            @click="loadProviders()"
          >
            {{ t('home.health.refresh') }}
          </v-btn>
        </div>
      </header>

      <v-alert
        v-if="providersError"
        type="error"
        variant="tonal"
        density="compact"
        class="health-alert"
      >
        {{ providersError }}
      </v-alert>

      <div v-if="!providersLoading && providers.length === 0" class="health-empty">
        <span class="health-empty-icon"><v-icon size="22">mdi-heart-pulse</v-icon></span>
        <div>
          <h3>{{ t('home.health.noProviders') }}</h3>
          <p>{{ t('home.health.noProvidersDesc') }}</p>
        </div>
        <router-link to="/providers" class="health-link">
          {{ t('home.health.manageProviders') }}
          <v-icon size="14">mdi-arrow-right</v-icon>
        </router-link>
      </div>

      <div v-else-if="providers.length" class="health-grid">
        <article
          v-for="provider in providers"
          :key="provider.id"
          class="health-card"
          :class="`health-card--${healthState(provider)}`"
        >
          <header class="health-card-head">
            <span class="health-category">
              <v-icon size="16">{{ categoryIcons[provider.category] }}</v-icon>
              {{ t(`providers.categories.${provider.category}.title`) }}
            </span>
            <span class="health-state">
              <i />
              {{ healthLabel(provider) }}
            </span>
          </header>
          <h3>{{ provider.name }}</h3>
          <p class="health-model">{{ provider.model }}</p>
          <p v-if="provider.last_test_message" class="health-message">
            {{ provider.last_test_message }}
          </p>
          <footer class="health-card-foot">
            <span>{{ healthTime(provider) }}</span>
            <v-icon v-if="provider.is_default" size="14">mdi-star</v-icon>
          </footer>
        </article>
      </div>
      <div v-else class="health-loading">
        <v-progress-circular indeterminate size="20" width="2" />
        {{ t('home.health.loading') }}
      </div>
    </section>

    <section class="canvas">
      <div class="canvas-grid" aria-hidden="true" />
      <span class="corner corner--tl" aria-hidden="true" />
      <span class="corner corner--tr" aria-hidden="true" />
      <span class="corner corner--bl" aria-hidden="true" />
      <span class="corner corner--br" aria-hidden="true" />

      <div class="canvas-empty">
        <div class="empty-mark">
          <MoriLogo :size="68" />
        </div>
        <p class="mori-eyebrow">{{ t('home.workspaceReady') }}</p>
        <h2>{{ t('home.readyTitle') }}</h2>
        <p class="empty-description">{{ t('home.readyDescription') }}</p>
        <div class="empty-actions">
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" disabled>
            {{ t('home.addModule') }}
          </v-btn>
          <span class="empty-note">{{ t('home.moreModules') }}</span>
        </div>
      </div>
    </section>

    <footer class="page-footer">
      <span>{{ t('home.footer') }}</span>
      <span class="footer-meta">
        <v-icon size="13">mdi-database-outline</v-icon>
        {{ t('home.sqlite') }}
      </span>
    </footer>

    <MobilePairingDialog v-model="mobileDialogOpen" />
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3200">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<style scoped lang="scss">
.home-page {
  width: 100%;
  max-width: 1440px;
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

.head-copy h1 {
  margin: 12px 0 0;
  color: var(--mori-text);
  font-size: clamp(28px, 3.2vw, 38px);
  font-weight: 600;
  letter-spacing: -0.045em;
  line-height: 1.1;
}

.head-subtitle {
  margin: 12px 0 0;
  color: var(--mori-muted);
  font-size: 13.5px;
  line-height: 1.7;
}

.head-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding-bottom: 4px;
}

.docs-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--mori-line);
  border-radius: 10px;
  background: transparent;
  color: var(--mori-muted);
  cursor: pointer;
  font: inherit;
  font-size: 11.5px;
  transition:
    color 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease;
}

.docs-link:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--mori-mint) 40%, transparent);
  background: var(--mori-mint-soft);
  color: var(--mori-text);
}

.docs-link:disabled {
  cursor: wait;
  opacity: 0.65;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 13px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  color: var(--mori-muted);
  font-size: 11.5px;
  white-space: nowrap;
}

.status-chip i {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--mori-muted);
}

.status-chip--live {
  border-color: color-mix(in srgb, var(--mori-mint) 32%, transparent);
  background: var(--mori-mint-soft);
  color: var(--mori-text);
}

.status-chip--live i {
  background: var(--mori-mint);
  animation: mori-pulse 2.4s ease-in-out infinite;
}

.runtime-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  margin: 30px 0 22px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
}

.runtime-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  padding: 18px 22px;
  border-right: 1px solid var(--mori-line);
}

.runtime-item:last-child {
  border-right: 0;
}

.runtime-label {
  color: var(--mori-muted);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.runtime-item strong {
  color: var(--mori-text);
  font-size: clamp(17px, 1.7vw, 21px);
  font-weight: 600;
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-health {
  margin-bottom: 22px;
  padding: 20px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
}

.health-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 22px;
}

.health-head h2 {
  margin: 9px 0 0;
  color: var(--mori-text);
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.03em;
}

.health-subtitle {
  margin: 6px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
  line-height: 1.6;
}

.health-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.health-summary {
  padding: 6px 10px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  color: var(--mori-muted);
  font-size: 10.5px;
  white-space: nowrap;
}

.health-alert {
  margin-top: 14px;
  border-radius: 12px;
}

.health-empty {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding: 16px;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 14px;
}

.health-empty-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: none;
  place-items: center;
  border-radius: 11px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
}

.health-empty h3 {
  margin: 0;
  color: var(--mori-text);
  font-size: 12.5px;
  font-weight: 600;
}

.health-empty p {
  margin: 4px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
}

.health-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  color: var(--mori-mint);
  font-size: 11px;
  text-decoration: none;
  white-space: nowrap;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.health-card {
  position: relative;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel-2);
}

.health-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.health-category {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--mori-muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.health-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--mori-muted);
  font-size: 10px;
  white-space: nowrap;
}

.health-state i {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--mori-muted);
}

.health-card--available .health-state {
  color: var(--mori-mint);
}

.health-card--available .health-state i {
  background: var(--mori-mint);
}

.health-card--unavailable .health-state {
  color: rgb(var(--v-theme-error));
}

.health-card--unavailable .health-state i {
  background: rgb(var(--v-theme-error));
}

.health-card h3 {
  margin: 12px 0 0;
  overflow: hidden;
  color: var(--mori-text);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health-model {
  margin: 4px 0 0;
  overflow: hidden;
  color: var(--mori-muted);
  font-family: var(--mori-font-mono, monospace);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health-message {
  display: -webkit-box;
  overflow: hidden;
  margin: 8px 0 0;
  color: var(--mori-muted);
  font-size: 10px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.health-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 10px;
  color: var(--mori-muted);
  font-size: 9.5px;
}

.health-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  color: var(--mori-muted);
  font-size: 11px;
}

.canvas {
  position: relative;
  display: grid;
  min-height: 460px;
  place-items: center;
  overflow: hidden;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 24px;
  background:
    radial-gradient(circle at 50% 42%, var(--mori-mint-soft), transparent 36%),
    var(--mori-panel);
}

.canvas-grid {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(to right, var(--mori-line) 1px, transparent 1px),
    linear-gradient(to bottom, var(--mori-line) 1px, transparent 1px);
  background-size: 44px 44px;
  opacity: 0.55;
  mask-image: radial-gradient(circle at center, #000 6%, transparent 68%);
  pointer-events: none;
}

.canvas-empty {
  position: relative;
  z-index: 1;
  display: flex;
  max-width: 470px;
  flex-direction: column;
  align-items: center;
  padding: 42px 24px;
  text-align: center;
}

.empty-mark {
  display: grid;
  width: 94px;
  height: 94px;
  margin-bottom: 24px;
  place-items: center;
  border: 1px solid var(--mori-line);
  border-radius: 28px;
  background: var(--mori-panel-2);
  box-shadow: 0 18px 44px var(--mori-glow);
}

.canvas-empty h2 {
  margin: 12px 0 0;
  color: var(--mori-text);
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.035em;
}

.empty-description {
  margin: 13px 0 0;
  color: var(--mori-muted);
  font-size: 13px;
  line-height: 1.8;
}

.empty-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 26px;
}

.empty-note {
  color: var(--mori-muted);
  font-size: 11px;
  letter-spacing: 0.02em;
}

.corner {
  position: absolute;
  width: 22px;
  height: 22px;
  border-color: color-mix(in srgb, var(--mori-mint) 55%, transparent);
  border-style: solid;
  opacity: 0.8;
}

.corner--tl {
  top: 16px;
  left: 16px;
  border-width: 1px 0 0 1px;
  border-radius: 6px 0 0;
}

.corner--tr {
  top: 16px;
  right: 16px;
  border-width: 1px 1px 0 0;
  border-radius: 0 6px 0 0;
}

.corner--bl {
  bottom: 16px;
  left: 16px;
  border-width: 0 0 1px 1px;
  border-radius: 0 0 0 6px;
}

.corner--br {
  right: 16px;
  bottom: 16px;
  border-width: 0 1px 1px 0;
  border-radius: 0 0 6px;
}

.page-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 20px;
  color: var(--mori-muted);
  font-size: 10.5px;
  letter-spacing: 0.02em;
}

.footer-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 820px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .head-actions {
    width: 100%;
    justify-content: space-between;
    padding-bottom: 0;
  }

  .runtime-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .runtime-item:nth-child(2) {
    border-right: 0;
  }

  .runtime-item:nth-child(-n + 2) {
    border-bottom: 1px solid var(--mori-line);
  }

  .health-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .health-actions {
    width: 100%;
    justify-content: space-between;
  }

  .canvas {
    min-height: 410px;
  }
}

@media (max-width: 520px) {
  .home-page {
    padding-top: 24px;
  }

  .canvas {
    min-height: 360px;
    border-radius: 18px;
  }

  .canvas-empty {
    padding: 34px 18px;
  }

  .empty-actions {
    flex-direction: column;
    gap: 10px;
  }

  .page-footer {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
