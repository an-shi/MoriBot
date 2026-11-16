<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { mobileApi } from '@/api/mobile'
import type { MobileDevice, PairingCode } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()

const devices = ref<MobileDevice[]>([])
const pairing = ref<PairingCode | null>(null)
const loadingDevices = ref(true)
const generating = ref(false)
const revokingId = ref('')
const errorMessage = ref('')
const copiedTarget = ref<'code' | 'uri' | null>(null)
const now = ref(Date.now())
const snackbar = ref({ show: false, message: '', color: 'success' })

let ticker: number | undefined
let poller: number | undefined
let copiedTimer: number | undefined

const activeDevices = computed(() => devices.value.filter((device) => !device.revoked_at))
const revokedDevices = computed(() => devices.value.filter((device) => device.revoked_at))
const onlineCount = computed(
  () => activeDevices.value.filter((device) => device.online).length,
)
const serverUrl = computed(() => pairing.value?.server_url || window.location.origin)

const expiresAt = computed(() => (pairing.value ? parseUtc(pairing.value.expires_at) : 0))
const remainingSeconds = computed(() =>
  Math.max(0, Math.floor((expiresAt.value - now.value) / 1000)),
)
const pairingExpired = computed(
  () => pairing.value !== null && remainingSeconds.value <= 0,
)
const remainingLabel = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60)
  const seconds = remainingSeconds.value % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
})

function parseUtc(value: string): number {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(normalized).getTime()
}

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

async function loadDevices(silent = false): Promise<void> {
  if (!silent) {
    loadingDevices.value = true
  }
  errorMessage.value = ''
  try {
    devices.value = await mobileApi.listDevices()
  } catch (error) {
    errorMessage.value = `${t('mobile.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loadingDevices.value = false
  }
}

async function refresh(): Promise<void> {
  await loadDevices()
  if (!errorMessage.value) {
    showSnackbar(t('mobile.refreshSuccess'), 'success')
  }
}

async function generateCode(): Promise<void> {
  generating.value = true
  errorMessage.value = ''
  try {
    pairing.value = await mobileApi.createPairingCode()
    now.value = Date.now()
    showSnackbar(t('mobile.generateSuccess'), 'success')
  } catch (error) {
    errorMessage.value = `${t('mobile.generateFailed')}: ${extractErrorMessage(error)}`
  } finally {
    generating.value = false
  }
}

async function revokeDevice(device: MobileDevice): Promise<void> {
  if (!window.confirm(t('mobile.revokeConfirm'))) {
    return
  }
  revokingId.value = device.id
  errorMessage.value = ''
  try {
    await mobileApi.revokeDevice(device.id)
    await loadDevices(true)
    showSnackbar(t('mobile.revokedSuccess'), 'success')
  } catch (error) {
    errorMessage.value = `${t('mobile.revokeFailed')}: ${extractErrorMessage(error)}`
  } finally {
    revokingId.value = ''
  }
}

async function copyValue(target: 'code' | 'uri', value: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    copiedTarget.value = target
    if (copiedTimer) {
      window.clearTimeout(copiedTimer)
    }
    copiedTimer = window.setTimeout(() => {
      copiedTarget.value = null
    }, 1600)
  } catch {
    errorMessage.value = t('mobile.copyFailed')
  }
}

function startTimers(): void {
  stopTimers()
  now.value = Date.now()
  ticker = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
  poller = window.setInterval(() => {
    if (document.visibilityState === 'visible') {
      void loadDevices(true)
    }
  }, 5000)
}

function stopTimers(): void {
  if (ticker) {
    window.clearInterval(ticker)
    ticker = undefined
  }
  if (poller) {
    window.clearInterval(poller)
    poller = undefined
  }
}

function deviceLastSeen(device: MobileDevice): string {
  return device.last_seen_at
    ? t('mobile.lastSeen', {
        time: formatDateTime(device.last_seen_at, locale.value, t('mobile.neverSeen')),
      })
    : t('mobile.neverSeen')
}

onMounted(() => {
  void loadDevices()
  startTimers()
})

onBeforeUnmount(() => {
  stopTimers()
  if (copiedTimer) {
    window.clearTimeout(copiedTimer)
  }
})
</script>

<template>
  <div class="mobile-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('mobile.eyebrow') }}</p>
        <h1>{{ t('mobile.title') }}</h1>
        <p class="page-subtitle">{{ t('mobile.pageSubtitle') }}</p>
      </div>
      <div class="head-actions">
        <span class="count-chip">
          {{ t('mobile.summary', { online: onlineCount, total: activeDevices.length }) }}
        </span>
        <v-btn
          variant="text"
          prepend-icon="mdi-refresh"
          :loading="loadingDevices"
          @click="refresh"
        >
          {{ t('mobile.refresh') }}
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-qrcode"
          :loading="generating"
          @click="generateCode"
        >
          {{ pairing ? t('mobile.regenerate') : t('mobile.generate') }}
        </v-btn>
      </div>
    </header>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="page-alert"
    >
      {{ errorMessage }}
    </v-alert>

    <div class="mobile-grid">
      <section class="panel-card pairing-panel">
        <header class="panel-head">
          <div>
            <p class="mori-eyebrow">{{ t('mobile.pairingTitle') }}</p>
            <h2>{{ t('mobile.codeLabel') }}</h2>
          </div>
          <v-chip
            v-if="pairing"
            size="x-small"
            variant="tonal"
            :color="pairingExpired ? 'error' : 'primary'"
          >
            {{
              pairingExpired
                ? t('mobile.expired')
                : t('mobile.expiresIn', { time: remainingLabel })
            }}
          </v-chip>
        </header>

        <div v-if="pairing" class="pairing-content">
          <div class="pairing-code-row">
            <code class="pairing-code">{{ pairing.code }}</code>
            <v-btn
              icon
              variant="tonal"
              size="small"
              color="primary"
              @click="copyValue('code', pairing.code)"
            >
              <v-icon size="16">
                {{ copiedTarget === 'code' ? 'mdi-check' : 'mdi-content-copy' }}
              </v-icon>
              <v-tooltip activator="parent" location="bottom">
                {{ copiedTarget === 'code' ? t('mobile.copied') : t('mobile.copy') }}
              </v-tooltip>
            </v-btn>
          </div>

          <div class="pairing-uri">
            <span>{{ t('mobile.pairingLink') }}</span>
            <code>{{ pairing.pairing_uri }}</code>
            <v-btn
              icon
              variant="text"
              size="x-small"
              @click="copyValue('uri', pairing.pairing_uri)"
            >
              <v-icon size="14">
                {{ copiedTarget === 'uri' ? 'mdi-check' : 'mdi-content-copy' }}
              </v-icon>
              <v-tooltip activator="parent" location="bottom">
                {{ copiedTarget === 'uri' ? t('mobile.copied') : t('mobile.copy') }}
              </v-tooltip>
            </v-btn>
          </div>

          <div class="pairing-actions">
            <v-btn
              variant="tonal"
              color="primary"
              size="small"
              prepend-icon="mdi-refresh"
              :loading="generating"
              @click="generateCode"
            >
              {{ t('mobile.regenerate') }}
            </v-btn>
          </div>
        </div>

        <div v-else class="pairing-empty">
          <span class="pairing-empty-icon">
            <v-icon size="28">mdi-cellphone-link</v-icon>
          </span>
          <div>
            <h3>{{ t('mobile.pairingEmptyTitle') }}</h3>
            <p>{{ t('mobile.pairingEmptyDescription') }}</p>
          </div>
          <v-btn
            color="primary"
            prepend-icon="mdi-qrcode"
            :loading="generating"
            @click="generateCode"
          >
            {{ t('mobile.generate') }}
          </v-btn>
        </div>

        <p class="pairing-hint">{{ t('mobile.securityNote') }}</p>
        <p class="pairing-hint">
          {{ t('mobile.serverHint', { server: serverUrl }) }}
        </p>
      </section>

      <section class="panel-card info-panel">
        <p class="mori-eyebrow">{{ t('nav.platforms') }}</p>
        <h2>{{ t('mobile.serverTitle') }}</h2>

        <div class="info-list">
          <div class="info-row">
            <span>{{ t('mobile.serverUrl') }}</span>
            <strong>{{ serverUrl }}</strong>
          </div>
          <div class="info-row">
            <span>{{ t('mobile.onlineCount') }}</span>
            <strong>{{ onlineCount }} / {{ activeDevices.length }}</strong>
          </div>
        </div>

        <h3 class="guide-title">{{ t('mobile.guideTitle') }}</h3>
        <ol class="guide-list">
          <li>{{ t('mobile.guideStep1') }}</li>
          <li>{{ t('mobile.guideStep2') }}</li>
          <li>{{ t('mobile.guideStep3') }}</li>
        </ol>
      </section>
    </div>

    <section class="panel-card devices-panel">
      <header class="devices-head">
        <div>
          <p class="mori-eyebrow">{{ t('mobile.devices') }}</p>
          <h2>{{ t('mobile.devicesTitle') }}</h2>
          <p>{{ t('mobile.devicesSubtitle') }}</p>
        </div>
        <v-btn
          variant="text"
          prepend-icon="mdi-refresh"
          :loading="loadingDevices"
          @click="refresh"
        >
          {{ t('mobile.refresh') }}
        </v-btn>
      </header>

      <div v-if="loadingDevices && activeDevices.length === 0" class="devices-loading">
        <v-progress-circular indeterminate size="20" width="2" />
        {{ t('mobile.loadingDevices') }}
      </div>

      <div v-else-if="activeDevices.length === 0" class="devices-empty">
        <span class="devices-empty-icon"><v-icon size="24">mdi-cellphone-off</v-icon></span>
        <div>
          <strong>{{ t('mobile.noDevices') }}</strong>
          <p>{{ t('mobile.noDevicesDescription') }}</p>
        </div>
      </div>

      <div v-else class="device-list">
        <div v-for="device in activeDevices" :key="device.id" class="device-row">
          <span class="device-icon">
            <v-icon size="18">mdi-cellphone</v-icon>
          </span>
          <div class="device-copy">
            <strong>{{ device.name }}</strong>
            <small>
              {{ deviceLastSeen(device) }} ·
              {{
                t('mobile.deviceCreated', {
                  time: formatDateTime(device.created_at, locale, '-'),
                })
              }}
            </small>
          </div>
          <span class="device-status" :class="{ 'device-status--online': device.online }">
            <i />
            {{ device.online ? t('mobile.online') : t('mobile.offline') }}
          </span>
          <v-btn
            variant="text"
            size="small"
            color="error"
            :loading="revokingId === device.id"
            @click="revokeDevice(device)"
          >
            {{ t('mobile.revoke') }}
          </v-btn>
        </div>
      </div>

      <template v-if="revokedDevices.length > 0">
        <h3 class="revoked-title">{{ t('mobile.revokedDevices') }}</h3>
        <div class="device-list device-list--revoked">
          <div v-for="device in revokedDevices" :key="device.id" class="device-row">
            <span class="device-icon">
              <v-icon size="18">mdi-cellphone-remove</v-icon>
            </span>
            <div class="device-copy">
              <strong>{{ device.name }}</strong>
              <small>
                {{
                  t('mobile.revokedAt', {
                    time: formatDateTime(device.revoked_at, locale, '-'),
                  })
                }}
              </small>
            </div>
            <span class="device-status">{{ t('mobile.offline') }}</span>
          </div>
        </div>
      </template>
    </section>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3200">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<style scoped lang="scss">
.mobile-page {
  width: 100%;
  max-width: 1360px;
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

.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 4px;
}

.count-chip {
  padding: 6px 11px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  color: var(--mori-muted);
  font-size: 11px;
  white-space: nowrap;
}

.page-alert {
  margin-top: 20px;
  border-radius: 12px;
}

.mobile-grid {
  display: grid;
  margin-top: 22px;
  grid-template-columns: minmax(0, 1.35fr) minmax(300px, 0.8fr);
  gap: 18px;
}

.panel-card {
  padding: 24px;
  border: 1px solid var(--mori-line);
  border-radius: 20px;
  background: var(--mori-panel);
  box-shadow: 0 1px 0 rgb(255 255 255 / 35%) inset;
}

.panel-head,
.devices-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-head h2,
.devices-head h2,
.info-panel h2 {
  margin: 8px 0 0;
  color: var(--mori-text);
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.035em;
}

.devices-head p:not(.mori-eyebrow) {
  max-width: 620px;
  margin: 8px 0 0;
  color: var(--mori-muted);
  font-size: 12.5px;
  line-height: 1.65;
}

.pairing-content {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid var(--mori-line);
  border-radius: 16px;
  background:
    radial-gradient(circle at 100% 0, var(--mori-mint-soft), transparent 55%),
    var(--mori-panel-2);
}

.pairing-code-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pairing-code {
  color: var(--mori-text);
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: clamp(28px, 4vw, 42px);
  font-weight: 700;
  letter-spacing: 0.14em;
}

.pairing-uri {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  color: var(--mori-muted);
  font-size: 11px;
}

.pairing-uri span {
  flex: none;
}

.pairing-uri code {
  overflow: hidden;
  flex: 1;
  color: var(--mori-text);
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pairing-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.pairing-empty {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 18px;
  padding: 20px;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 16px;
  background: var(--mori-panel-2);
}

.pairing-empty-icon {
  display: grid;
  width: 52px;
  height: 52px;
  flex: none;
  place-items: center;
  border-radius: 15px;
  background: var(--mori-mint-soft);
  color: var(--mori-mint);
}

.pairing-empty h3 {
  margin: 0;
  color: var(--mori-text);
  font-size: 14px;
  font-weight: 600;
}

.pairing-empty p {
  max-width: 520px;
  margin: 6px 0 0;
  color: var(--mori-muted);
  font-size: 11.5px;
  line-height: 1.65;
}

.pairing-empty .v-btn {
  margin-left: auto;
  flex: none;
}

.pairing-hint {
  margin: 14px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.65;
}

.info-panel {
  background:
    radial-gradient(circle at 100% 0, var(--mori-mint-soft), transparent 62%),
    var(--mori-panel);
}

.info-list {
  display: grid;
  gap: 2px;
  margin-top: 20px;
  padding: 14px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel-2);
}

.info-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  padding: 7px 0;
  color: var(--mori-muted);
  font-size: 11px;
}

.info-row strong {
  overflow: hidden;
  max-width: 70%;
  color: var(--mori-text);
  font-size: 11.5px;
  font-weight: 600;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guide-list {
  margin: 10px 0 0;
  padding-left: 20px;
  color: var(--mori-muted);
  font-size: 12px;
  line-height: 1.75;
}

.guide-title {
  margin: 20px 0 0;
  color: var(--mori-text);
  font-size: 13px;
  font-weight: 600;
}

.guide-list li + li {
  margin-top: 8px;
}

.devices-panel {
  margin-top: 18px;
}

.devices-loading,
.devices-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 18px;
  color: var(--mori-muted);
  font-size: 12px;
}

.devices-empty {
  padding: 18px;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 16px;
  background: var(--mori-panel-2);
}

.devices-empty-icon {
  display: grid;
  width: 42px;
  height: 42px;
  flex: none;
  place-items: center;
  border-radius: 12px;
  background: var(--mori-panel);
  color: var(--mori-muted);
}

.devices-empty strong {
  color: var(--mori-text);
  font-size: 12.5px;
}

.devices-empty p {
  margin: 4px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
}

.device-list {
  display: grid;
  gap: 7px;
  margin-top: 16px;
}

.device-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel-2);
}

.device-icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex: none;
  place-items: center;
  border-radius: 10px;
  background: var(--mori-mint-soft);
  color: var(--mori-mint);
}

.device-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.device-copy strong {
  overflow: hidden;
  color: var(--mori-text);
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-copy small {
  overflow: hidden;
  color: var(--mori-muted);
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--mori-muted);
  font-size: 10px;
  white-space: nowrap;
}

.device-status i {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--mori-muted);
}

.device-status--online {
  color: var(--mori-mint);
}

.device-status--online i {
  background: var(--mori-mint);
  animation: mori-pulse 2.4s ease-in-out infinite;
}

.revoked-title {
  margin: 24px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.device-list--revoked {
  opacity: 0.68;
}

@media (max-width: 960px) {
  .mobile-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .head-actions {
    width: 100%;
    flex-wrap: wrap;
    padding-bottom: 0;
  }

  .head-actions .count-chip {
    margin-right: auto;
  }

  .pairing-empty {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .pairing-empty .v-btn {
    margin-left: 0;
  }

  .device-status {
    display: none;
  }

  .pairing-uri span {
    display: none;
  }
}
</style>
