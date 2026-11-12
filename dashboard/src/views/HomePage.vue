<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { systemApi } from '@/api/system'
import MobilePairingDialog from '@/components/MobilePairingDialog.vue'
import MoriLogo from '@/components/MoriLogo.vue'
import { APP_VERSION } from '@/config'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { formatUptime } from '@/utils/format'

const system = useSystemStore()
const auth = useAuthStore()
const { t, locale } = useI18n()

const mobileDialogOpen = ref(false)
const exporting = ref(false)
const snackbar = ref({ show: false, message: '', color: 'success' })

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
