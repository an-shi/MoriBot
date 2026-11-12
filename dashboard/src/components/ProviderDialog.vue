<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { providersApi, type ProviderPayload, type ProviderUpdatePayload } from '@/api/providers'
import type { ModelProvider, ProviderCategory } from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  category: ProviderCategory
  provider: ModelProvider | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [provider: ModelProvider]
}>()

const { t } = useI18n()

const name = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const model = ref('')
const isDefault = ref(false)
const enabled = ref(true)
const errorMessage = ref('')
const saving = ref(false)

const temperature = ref<string | number>('')
const maxTokens = ref<string | number>('')
const voice = ref('alloy')
const audioFormat = ref('mp3')
const speed = ref<string | number>('')
const imageSize = ref('1024x1024')
const imageQuality = ref('')
const imageCount = ref<string | number>(1)
const responseFormat = ref('')

const dialogOpen = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const isEdit = computed(() => props.provider !== null)
const activeCategory = computed<ProviderCategory>(
  () => props.provider?.category ?? props.category,
)
const categoryLabel = computed(() => t(`providers.categories.${activeCategory.value}.title`))
const modelPlaceholder = computed(() =>
  t(`providers.dialog.modelPlaceholder${activeCategory.value === 'chat' ? 'Chat' : activeCategory.value === 'speech' ? 'Speech' : 'Image'}`),
)

const speechFormats = ['mp3', 'wav', 'opus', 'aac', 'flac']
const imageSizes = ['1024x1024', '1024x1536', '1536x1024', '512x512', '256x256']
const imageQualities = ['auto', 'high', 'medium', 'low', 'standard', 'hd']
const responseFormats = ['', 'b64_json', 'url']

function resetForm(): void {
  const provider = props.provider
  name.value = provider?.name ?? ''
  baseUrl.value = provider?.base_url ?? ''
  apiKey.value = ''
  model.value = provider?.model ?? ''
  isDefault.value = provider?.is_default ?? false
  enabled.value = provider?.enabled ?? true
  errorMessage.value = ''

  const options = (provider?.options ?? {}) as Record<string, unknown>
  temperature.value = (options.temperature as string | number) ?? ''
  maxTokens.value = (options.max_tokens as string | number) ?? ''
  voice.value = String(options.voice ?? 'alloy')
  audioFormat.value = String(options.response_format ?? 'mp3')
  speed.value = (options.speed as string | number) ?? ''
  imageSize.value = String(options.size ?? '1024x1024')
  imageQuality.value = String(options.quality ?? '')
  imageCount.value = (options.n as string | number) ?? 1
  responseFormat.value = String(options.response_format ?? '')
}

watch(
  () => [props.modelValue, props.provider, props.category] as const,
  ([open]) => {
    if (open) {
      resetForm()
    }
  },
  { immediate: true },
)

function numberOrUndefined(value: string | number): number | undefined {
  if (value === '' || value === null || value === undefined) {
    return undefined
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function buildOptions(): Record<string, unknown> {
  const options: Record<string, unknown> = {}
  if (activeCategory.value === 'chat') {
    const temp = numberOrUndefined(temperature.value)
    const tokens = numberOrUndefined(maxTokens.value)
    if (temp !== undefined) options.temperature = temp
    if (tokens !== undefined) options.max_tokens = tokens
  } else if (activeCategory.value === 'speech') {
    options.voice = voice.value.trim() || 'alloy'
    options.response_format = audioFormat.value
    const spd = numberOrUndefined(speed.value)
    if (spd !== undefined) options.speed = spd
  } else {
    options.size = imageSize.value.trim() || '1024x1024'
    const count = numberOrUndefined(imageCount.value)
    if (count !== undefined) options.n = count
    if (imageQuality.value) options.quality = imageQuality.value
    if (responseFormat.value) options.response_format = responseFormat.value
  }
  return options
}

async function save(): Promise<void> {
  if (!name.value.trim() || !baseUrl.value.trim() || !model.value.trim()) {
    errorMessage.value = t('providers.dialog.required')
    return
  }

  saving.value = true
  errorMessage.value = ''
  try {
    let result: ModelProvider
    if (isEdit.value && props.provider) {
      const payload: ProviderUpdatePayload = {
        name: name.value.trim(),
        base_url: baseUrl.value.trim(),
        model: model.value.trim(),
        options: buildOptions(),
        is_default: isDefault.value,
        enabled: enabled.value,
      }
      if (apiKey.value.trim()) {
        payload.api_key = apiKey.value.trim()
      }
      result = await providersApi.update(props.provider.id, payload)
    } else {
      const payload: ProviderPayload = {
        category: activeCategory.value,
        name: name.value.trim(),
        provider_type: 'openai_compatible',
        base_url: baseUrl.value.trim(),
        api_key: apiKey.value.trim(),
        model: model.value.trim(),
        options: buildOptions(),
        is_default: isDefault.value,
        enabled: enabled.value,
      }
      result = await providersApi.create(payload)
    }
    emit('saved', result)
    dialogOpen.value = false
  } catch (error) {
    errorMessage.value = extractErrorMessage(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog v-model="dialogOpen" max-width="680" scrollable>
    <v-card class="provider-dialog">
      <header class="dialog-head">
        <div>
          <p class="mori-eyebrow">{{ categoryLabel }}</p>
          <h2>{{ isEdit ? t('providers.dialog.editTitle') : t('providers.dialog.createTitle') }}</h2>
        </div>
        <v-btn icon variant="text" size="small" @click="dialogOpen = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </header>

      <v-card-text class="dialog-body">
        <v-alert v-if="errorMessage" type="error" variant="tonal" density="compact" class="dialog-error">
          {{ errorMessage }}
        </v-alert>

        <v-form @submit.prevent="save">
          <div class="form-row form-row--two">
            <div class="field">
              <label>{{ t('providers.dialog.name') }}</label>
              <v-text-field
                v-model="name"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="t('providers.dialog.namePlaceholder')"
              />
            </div>
            <div class="field">
              <label>{{ t('providers.dialog.providerType') }}</label>
              <v-text-field
                model-value="OpenAI Compatible"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                readonly
                persistent-hint
                :hint="t('providers.dialog.providerTypeHint')"
              />
            </div>
          </div>

          <div class="field">
            <label>{{ t('providers.dialog.baseUrl') }}</label>
            <v-text-field
              v-model="baseUrl"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
              :placeholder="t('providers.dialog.baseUrlPlaceholder')"
              prepend-inner-icon="mdi-api"
            />
          </div>

          <div class="form-row form-row--two">
            <div class="field">
              <label>{{ t('providers.dialog.apiKey') }}</label>
              <v-text-field
                v-model="apiKey"
                type="password"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="
                  isEdit
                    ? t('providers.dialog.apiKeyEditPlaceholder')
                    : t('providers.dialog.apiKeyPlaceholder')
                "
                prepend-inner-icon="mdi-key-outline"
                autocomplete="new-password"
              />
            </div>
            <div class="field">
              <label>{{ t('providers.dialog.model') }}</label>
              <v-text-field
                v-model="model"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="modelPlaceholder"
                prepend-inner-icon="mdi-cube-outline"
              />
            </div>
          </div>
          <p class="field-hint">{{ t('providers.dialog.apiKeyHint') }}</p>

          <div class="options-panel">
            <p class="options-title">{{ t('providers.dialog.advanced') }}</p>

            <div v-if="activeCategory === 'chat'" class="form-row form-row--two">
              <div class="field">
                <label>{{ t('providers.dialog.temperature') }}</label>
                <v-text-field
                  v-model="temperature"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  placeholder="0.7"
                />
              </div>
              <div class="field">
                <label>{{ t('providers.dialog.maxTokens') }}</label>
                <v-text-field
                  v-model="maxTokens"
                  type="number"
                  min="1"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  placeholder="2048"
                />
              </div>
            </div>

            <div v-else-if="activeCategory === 'speech'" class="form-row form-row--three">
              <div class="field">
                <label>{{ t('providers.dialog.voice') }}</label>
                <v-combobox
                  v-model="voice"
                  :items="['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  :placeholder="t('providers.dialog.voicePlaceholder')"
                />
              </div>
              <div class="field">
                <label>{{ t('providers.dialog.audioFormat') }}</label>
                <v-select
                  v-model="audioFormat"
                  :items="speechFormats"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />
              </div>
              <div class="field">
                <label>{{ t('providers.dialog.speed') }}</label>
                <v-text-field
                  v-model="speed"
                  type="number"
                  step="0.05"
                  min="0.25"
                  max="4"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  placeholder="1.0"
                />
              </div>
            </div>

            <div v-else class="form-row form-row--two">
              <div class="field">
                <label>{{ t('providers.dialog.imageSize') }}</label>
                <v-combobox
                  v-model="imageSize"
                  :items="imageSizes"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  :placeholder="t('providers.dialog.imageSizePlaceholder')"
                />
              </div>
              <div class="field">
                <label>{{ t('providers.dialog.imageQuality') }}</label>
                <v-combobox
                  v-model="imageQuality"
                  :items="imageQualities"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />
              </div>
              <div class="field">
                <label>{{ t('providers.dialog.imageCount') }}</label>
                <v-text-field
                  v-model="imageCount"
                  type="number"
                  min="1"
                  max="4"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />
              </div>
              <div class="field">
                <label>{{ t('providers.dialog.responseFormat') }}</label>
                <v-select
                  v-model="responseFormat"
                  :items="[
                    { title: t('providers.dialog.providerDefault'), value: '' },
                    { title: 'b64_json', value: 'b64_json' },
                    { title: 'url', value: 'url' },
                  ]"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />
              </div>
            </div>
          </div>

          <div class="switch-row">
            <v-checkbox
              v-model="isDefault"
              :label="t('providers.dialog.default')"
              color="primary"
              density="compact"
              hide-details
            />
            <v-checkbox
              v-model="enabled"
              :label="t('providers.dialog.enabled')"
              color="primary"
              density="compact"
              hide-details
            />
          </div>

          <div class="dialog-actions">
            <v-btn variant="text" @click="dialogOpen = false">
              {{ t('providers.dialog.cancel') }}
            </v-btn>
            <v-btn type="submit" color="primary" :loading="saving">
              {{ saving ? t('providers.dialog.saving') : t('providers.dialog.save') }}
            </v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.provider-dialog {
  border: 1px solid var(--mori-line);
  background: var(--mori-panel) !important;
  box-shadow: var(--mori-shadow);
}

.dialog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 26px 28px 0;
}

.dialog-head h2 {
  margin: 9px 0 0;
  color: var(--mori-text);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.035em;
}

.dialog-body {
  padding: 20px 28px 26px !important;
}

.dialog-error {
  margin-bottom: 16px;
  border-radius: 12px;
}

.form-row {
  display: grid;
  gap: 14px;
  margin-bottom: 14px;
}

.form-row--two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-row--three {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.field {
  min-width: 0;
}

.field label {
  display: block;
  margin-bottom: 7px;
  color: var(--mori-text);
  font-size: 12px;
  font-weight: 600;
}

.field :deep(.v-field) {
  border-radius: 12px;
  background: var(--mori-panel-2);
}

.field :deep(.v-field__outline) {
  color: var(--mori-line-strong);
}

.field-hint {
  margin: -4px 0 16px;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.options-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel-2);
}

.options-title {
  margin: 0 0 12px;
  color: var(--mori-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.options-panel .form-row:last-child {
  margin-bottom: 0;
}

.options-panel :deep(.v-field) {
  background: var(--mori-panel);
}

.switch-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 22px;
  margin-top: 16px;
}

.switch-row :deep(.v-label) {
  font-size: 12px;
  opacity: 1;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 22px;
}

@media (max-width: 620px) {
  .dialog-head {
    padding: 22px 20px 0;
  }

  .dialog-body {
    padding: 18px 20px 22px !important;
  }

  .form-row--two,
  .form-row--three {
    grid-template-columns: 1fr;
  }
}
</style>
