<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { mobileApi } from '@/api/mobile'
import type { MobileDevice, PairingCode } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const { t, locale } = useI18n()

const devices = ref<MobileDevice[]>([])
const pairing = ref<PairingCode | null>(null)
const loadingDevices = ref(false)
const generating = ref(false)
const revokingId = ref('')
const errorMessage = ref('')
const copiedTarget = ref<'code' | 'uri' | null>(null)
const now = ref(Date.now())

let ticker: number | undefined
let poller: number | undefined
let copiedTimer: number | undefined

const dialogOpen = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const activeDevices = computed(() => devices.value.filter((device) => !device.revoked_at))

function parseUtc(value: string): number {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(normalized).getTime()
}

const expiresAt = computed(() =>
  pairing.value ? parseUtc(pairing.value.expires_at) : 0,
)
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

async function loadDevices(): Promise<void> {
  loadingDevices.value = true
  errorMessage.value = ''
  try {
    devices.value = await mobileApi.listDevices()
  } catch (error) {
    errorMessage.value = `${t('mobile.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loadingDevices.value = false
  }
}

async function generateCode(): Promise<void> {
  generating.value = true
  errorMessage.value = ''
  try {
    pairing.value = await mobileApi.createPairingCode()
    now.value = Date.now()
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
    await loadDevices()
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

function startTimers(): void {
  stopTimers()
  now.value = Date.now()
  ticker = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
  poller = window.setInterval(() => {
    if (!loadingDevices.value) {
      void loadDevices()
    }
  }, 5000)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      void loadDevices()
      startTimers()
    } else {
      stopTimers()
      copiedTarget.value = null
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  stopTimers()
  if (copiedTimer) {
    window.clearTimeout(copiedTimer)
  }
})
</script>

<template>
  <v-dialog v-model="dialogOpen" max-width="620" scrollable>
    <v-card class="mobile-dialog">
      <header class="dialog-head">
        <div class="dialog-head-copy">
          <p class="mori-eyebrow">MORIMOBILE</p>
          <h2>{{ t('mobile.title') }}</h2>
          <p>{{ t('mobile.subtitle') }}</p>
        </div>
        <v-btn icon variant="text" size="small" @click="dialogOpen = false">
          <v-icon>mdi-close</v-icon>
          <v-tooltip activator="parent" location="bottom">{{ t('mobile.close') }}</v-tooltip>
        </v-btn>
      </header>

      <v-card-text class="dialog-body">
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          density="compact"
          class="dialog-alert"
        >
          {{ errorMessage }}
        </v-alert>

        <section class="pairing-card">
          <div v-if="pairing" class="pairing-content">
            <div class="pairing-topline">
              <span class="pairing-label">{{ t('mobile.codeLabel') }}</span>
              <v-chip
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
            </div>

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
            <v-icon size="30" color="primary">mdi-cellphone-link</v-icon>
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
          <p v-if="pairing" class="pairing-hint">
            {{ t('mobile.serverHint', { server: pairing.server_url }) }}
          </p>
        </section>

        <section class="devices-section">
          <div class="devices-head">
            <h3>{{ t('mobile.devices') }}</h3>
            <v-btn
              variant="text"
              size="small"
              prepend-icon="mdi-refresh"
              :loading="loadingDevices"
              @click="loadDevices"
            >
              {{ t('mobile.refresh') }}
            </v-btn>
          </div>

          <div v-if="activeDevices.length === 0 && !loadingDevices" class="devices-empty">
            <v-icon size="22">mdi-cellphone-off</v-icon>
            <span>{{ t('mobile.noDevices') }}</span>
          </div>

          <div v-else class="device-list">
            <div v-for="device in activeDevices" :key="device.id" class="device-row">
              <span class="device-icon">
                <v-icon size="18">mdi-cellphone</v-icon>
              </span>
              <div class="device-copy">
                <strong>{{ device.name }}</strong>
                <small>
                  {{
                    device.last_seen_at
                      ? t('mobile.lastSeen', {
                          time: formatDateTime(device.last_seen_at, locale, t('mobile.neverSeen')),
                        })
                      : t('mobile.neverSeen')
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
        </section>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.mobile-dialog {
  border: 1px solid var(--mori-line);
  background: var(--mori-panel) !important;
  box-shadow: var(--mori-shadow);
}

.dialog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 28px 28px 0;
}

.dialog-head-copy h2 {
  margin: 10px 0 0;
  color: var(--mori-text);
  font-size: 25px;
  font-weight: 600;
  letter-spacing: -0.035em;
}

.dialog-head-copy p:not(.mori-eyebrow) {
  margin: 9px 0 0;
  color: var(--mori-muted);
  font-size: 12.5px;
  line-height: 1.7;
}

.dialog-body {
  padding: 22px 28px 28px !important;
}

.dialog-alert {
  margin-bottom: 16px;
  border-radius: 12px;
  font-size: 12.5px;
}

.pairing-card {
  padding: 18px;
  border: 1px solid var(--mori-line);
  border-radius: 16px;
  background:
    radial-gradient(circle at 100% 0, var(--mori-mint-soft), transparent 55%),
    var(--mori-panel-2);
}

.pairing-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.pairing-label {
  color: var(--mori-muted);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.pairing-code-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.pairing-code {
  color: var(--mori-text);
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: clamp(26px, 4vw, 36px);
  font-weight: 700;
  letter-spacing: 0.12em;
}

.pairing-uri {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
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
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 20px 0 14px;
}

.pairing-hint {
  margin: 14px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.65;
}

.devices-section {
  margin-top: 24px;
}

.devices-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.devices-head h3 {
  margin: 0;
  color: var(--mori-text);
  font-size: 14px;
  font-weight: 600;
}

.devices-empty {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 18px 0;
  color: var(--mori-muted);
  font-size: 12px;
}

.device-list {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}

.device-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border: 1px solid var(--mori-line);
  border-radius: 12px;
  background: var(--mori-panel-2);
}

.device-icon {
  display: grid;
  width: 32px;
  height: 32px;
  flex: none;
  place-items: center;
  border-radius: 9px;
  background: var(--mori-mint-soft);
  color: var(--mori-mint);
}

.device-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.device-copy strong {
  overflow: hidden;
  color: var(--mori-text);
  font-size: 12.5px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-copy small {
  color: var(--mori-muted);
  font-size: 10.5px;
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

@media (max-width: 560px) {
  .dialog-head {
    padding: 22px 20px 0;
  }

  .dialog-body {
    padding: 18px 20px 22px !important;
  }

  .device-status {
    display: none;
  }

  .pairing-uri span {
    display: none;
  }
}
</style>
