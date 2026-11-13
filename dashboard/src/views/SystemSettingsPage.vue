<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { systemApi } from '@/api/system'

const { t } = useI18n()

const loading = ref(true)
const saving = ref(false)
const running = ref(false)
const enabled = ref(false)
const times = ref<string[]>(['09:00'])
const lastRuns = ref<Record<string, string>>({})
const serverTime = ref('')
const timezone = ref('')
const errorMessage = ref('')
const snackbar = ref({ show: false, message: '', color: 'success' })

const lastRunItems = computed(() =>
  Object.entries(lastRuns.value)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([time, date]) => ({ time, date })),
)

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

function addTime(): void {
  if (times.value.length >= 12) {
    return
  }
  times.value.push('09:00')
}

function removeTime(index: number): void {
  times.value.splice(index, 1)
}

async function loadSettings(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const settings = await systemApi.settings()
    enabled.value = settings.health_check.enabled
    times.value = settings.health_check.times.length
      ? [...settings.health_check.times]
      : ['09:00']
    lastRuns.value = settings.health_check.last_runs
    serverTime.value = settings.server_time
    timezone.value = settings.timezone
  } catch (error) {
    errorMessage.value = `${t('settings.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function saveSettings(): Promise<void> {
  if (enabled.value && !times.value.some((time) => time.trim())) {
    showSnackbar(t('settings.noTimeError'), 'error')
    return
  }
  saving.value = true
  errorMessage.value = ''
  try {
    const settings = await systemApi.updateSettings({
      health_check: {
        enabled: enabled.value,
        times: times.value.map((time) => time.trim()).filter(Boolean),
      },
    })
    enabled.value = settings.health_check.enabled
    times.value = settings.health_check.times.length
      ? [...settings.health_check.times]
      : ['09:00']
    lastRuns.value = settings.health_check.last_runs
    serverTime.value = settings.server_time
    timezone.value = settings.timezone
    showSnackbar(t('settings.saved'), 'success')
  } catch (error) {
    showSnackbar(`${t('settings.saveFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    saving.value = false
  }
}

async function runNow(): Promise<void> {
  running.value = true
  try {
    const result = await systemApi.runModelHealth()
    showSnackbar(
      t('settings.runDone', {
        checked: result.checked,
        available: result.available,
        failed: result.failed,
      }),
      result.failed > 0 ? 'error' : 'success',
    )
    await loadSettings()
  } catch (error) {
    showSnackbar(`${t('settings.runFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    running.value = false
  }
}

onMounted(() => {
  void loadSettings()
})
</script>

<template>
  <div class="settings-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('settings.eyebrow') }}</p>
        <h1>{{ t('settings.title') }}</h1>
        <p class="page-subtitle">{{ t('settings.subtitle') }}</p>
      </div>
    </header>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="settings-alert"
    >
      {{ errorMessage }}
    </v-alert>

    <v-progress-linear
      v-if="loading"
      indeterminate
      color="primary"
      class="settings-loader"
    />

    <section class="settings-card">
      <div class="card-head">
        <div class="card-title">
          <span class="card-icon"><v-icon size="20">mdi-heart-pulse</v-icon></span>
          <div>
            <h2>{{ t('settings.healthTitle') }}</h2>
            <p>{{ t('settings.healthDesc') }}</p>
          </div>
        </div>
        <v-switch
          v-model="enabled"
          color="primary"
          density="compact"
          hide-details
          :label="t('settings.enabled')"
        />
      </div>

      <div class="settings-body">
        <div class="field-block">
          <div class="field-head">
            <label>{{ t('settings.times') }}</label>
            <v-btn
              variant="text"
              size="small"
              prepend-icon="mdi-plus"
              :disabled="times.length >= 12"
              @click="addTime"
            >
              {{ t('settings.addTime') }}
            </v-btn>
          </div>
          <div class="time-list">
            <div v-for="(_, index) in times" :key="index" class="time-row">
              <v-text-field
                v-model="times[index]"
                type="time"
                variant="outlined"
                density="comfortable"
                hide-details
                class="time-input"
              />
              <v-btn
                icon
                variant="text"
                size="small"
                color="error"
                :aria-label="t('settings.removeTime')"
                @click="removeTime(index)"
              >
                <v-icon size="18">mdi-trash-can-outline</v-icon>
              </v-btn>
            </div>
          </div>
          <p class="field-hint">
            {{
              t('settings.timesHint', {
                timezone: timezone || t('settings.serverTimezoneUnknown'),
                serverTime: serverTime || '—',
              })
            }}
          </p>
        </div>

        <p class="cost-hint">
          <v-icon size="15">mdi-information-outline</v-icon>
          {{ t('settings.costHint') }}
        </p>

        <div class="actions">
          <v-btn
            variant="tonal"
            color="primary"
            prepend-icon="mdi-play"
            :loading="running"
            :disabled="loading"
            @click="runNow"
          >
            {{ running ? t('settings.running') : t('settings.runNow') }}
          </v-btn>
          <v-spacer />
          <v-btn color="primary" :loading="saving" :disabled="loading" @click="saveSettings">
            {{ saving ? t('settings.saving') : t('settings.save') }}
          </v-btn>
        </div>
      </div>
    </section>

    <section class="settings-card last-runs-card">
      <div class="card-title">
        <span class="card-icon"><v-icon size="20">mdi-history</v-icon></span>
        <div>
          <h2>{{ t('settings.lastRuns') }}</h2>
          <p>{{ t('settings.lastRunsDesc') }}</p>
        </div>
      </div>
      <div v-if="lastRunItems.length" class="last-runs">
        <span v-for="item in lastRunItems" :key="item.time" class="run-chip">
          <v-icon size="14">mdi-clock-outline</v-icon>
          {{ item.time }} · {{ item.date }}
        </span>
      </div>
      <p v-else class="empty-note">{{ t('settings.noLastRuns') }}</p>
    </section>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3400">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  width: 100%;
  max-width: 1120px;
  margin: 0 auto;
  padding: 34px clamp(20px, 3.2vw, 44px) 30px;
  animation: mori-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1);
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

.settings-alert {
  margin-top: 22px;
  border-radius: 14px;
}

.settings-loader {
  margin-top: 16px;
  border-radius: 999px;
}

.settings-card {
  margin-top: 24px;
  padding: 22px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 22px;
}

.card-title {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.card-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: none;
  place-items: center;
  border: 1px solid var(--mori-line);
  border-radius: 12px;
  background: var(--mori-panel-2);
  color: var(--mori-mint);
}

.card-title h2 {
  margin: 1px 0 0;
  color: var(--mori-text);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.card-title p {
  margin: 6px 0 0;
  color: var(--mori-muted);
  font-size: 12px;
  line-height: 1.7;
}

.settings-body {
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid var(--mori-line);
}

.field-block {
  max-width: 620px;
}

.field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}

.field-head label {
  color: var(--mori-text);
  font-size: 12px;
  font-weight: 600;
}

.time-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.time-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.time-input {
  max-width: 220px;
}

.time-input :deep(.v-field) {
  border-radius: 12px;
  background: var(--mori-panel-2);
}

.field-hint {
  margin: 10px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.cost-hint {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 18px 0 0;
  padding: 10px 12px;
  border: 1px solid var(--mori-line);
  border-radius: 12px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 20px;
}

.last-runs-card {
  margin-top: 16px;
}

.last-runs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}

.run-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 11px;
}

.empty-note {
  margin: 16px 0 0;
  color: var(--mori-muted);
  font-size: 11.5px;
}

@media (max-width: 680px) {
  .card-head {
    flex-direction: column;
  }

  .time-input {
    max-width: none;
  }
}
</style>
