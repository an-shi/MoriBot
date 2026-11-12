<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { providersApi, type ProviderPayload, type ProviderUpdatePayload } from '@/api/providers'
import type {
  ModelCapabilities,
  ModelProvider,
  ProviderCatalog,
  ProviderCategory,
  ProviderModelInfo,
  ProviderPreset,
  ProviderTypeInfo,
} from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  category: ProviderCategory
  provider: ModelProvider | null
  catalog: ProviderCatalog
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [provider: ModelProvider]
}>()

const { t } = useI18n()

const fallbackTypes: ProviderTypeInfo[] = [
  {
    id: 'openai_compatible',
    name: 'OpenAI Compatible',
    description: '',
    categories: ['chat', 'speech', 'image'],
    default_base_url: '',
    api_key_required: true,
    docs_url: '',
  },
  {
    id: 'azure_openai',
    name: 'Azure OpenAI',
    description: '',
    categories: ['chat', 'speech', 'image'],
    default_base_url: 'https://your-resource.openai.azure.com',
    api_key_required: true,
    docs_url: '',
  },
  {
    id: 'anthropic',
    name: 'Anthropic Claude',
    description: '',
    categories: ['chat'],
    default_base_url: 'https://api.anthropic.com/v1',
    api_key_required: true,
    docs_url: '',
  },
  {
    id: 'google_gemini',
    name: 'Google Gemini',
    description: '',
    categories: ['chat', 'image'],
    default_base_url: 'https://generativelanguage.googleapis.com/v1beta',
    api_key_required: true,
    docs_url: '',
  },
  {
    id: 'elevenlabs',
    name: 'ElevenLabs',
    description: '',
    categories: ['speech'],
    default_base_url: 'https://api.elevenlabs.io/v1',
    api_key_required: true,
    docs_url: '',
  },
  {
    id: 'minimax',
    name: 'MiniMax',
    description: '',
    categories: ['chat', 'speech', 'image'],
    default_base_url: 'https://api.minimax.io/v1',
    api_key_required: true,
    docs_url: '',
  },
]

const name = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const showApiKey = ref(false)
const model = ref('')
const providerType = ref('openai_compatible')
const presetId = ref('')
const apiVersion = ref('2024-10-21')
const groupId = ref('')
const isDefault = ref(false)
const enabled = ref(true)
const errorMessage = ref('')
const modelsNeedKey = ref(false)
const saving = ref(false)
const capabilities = ref<ModelCapabilities | null>(null)
const modelOptions = ref<ProviderModelInfo[]>([])
const modelsLoading = ref(false)
const modelsMessage = ref('')
const parameterPreset = ref('balanced')

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
const providerTypes = computed(() =>
  (props.catalog.types.length ? props.catalog.types : fallbackTypes).filter((item) =>
    item.categories.includes(activeCategory.value),
  ),
)
const presetsForCategory = computed(() =>
  props.catalog.presets.filter((preset) => preset.categories.includes(activeCategory.value)),
)
const presetItems = computed(() => [
  { id: '', name: t('providers.dialog.custom') },
  ...presetsForCategory.value.map((preset) => ({ id: preset.id, name: preset.name })),
])
const selectedPreset = computed<ProviderPreset | null>(
  () => presetsForCategory.value.find((preset) => preset.id === presetId.value) ?? null,
)
const selectedType = computed<ProviderTypeInfo | null>(
  () => providerTypes.value.find((item) => item.id === providerType.value) ?? null,
)
const apiKeyRequired = computed(
  () => selectedPreset.value?.api_key_required ?? selectedType.value?.api_key_required ?? true,
)
const modelPlaceholder = computed(() => {
  const presetModels = selectedPreset.value?.models[activeCategory.value]
  if (presetModels?.length) {
    return presetModels[0]
  }
  return t(
    `providers.dialog.modelPlaceholder${
      activeCategory.value === 'chat'
        ? 'Chat'
        : activeCategory.value === 'speech'
          ? 'Speech'
          : 'Image'
    }`,
  )
})

const parameterPresetItems = computed(() => [
  { title: t('providers.dialog.presetBalanced'), value: 'balanced' },
  { title: t('providers.dialog.presetPrecise'), value: 'precise' },
  { title: t('providers.dialog.presetCreative'), value: 'creative' },
  { title: t('providers.dialog.presetCustom'), value: 'custom' },
])

const capabilityLabels = computed(() => {
  const current = capabilities.value
  if (!current) {
    return []
  }
  const labels: string[] = []
  if (current.input.includes('image')) labels.push(t('providers.capabilities.imageInput'))
  if (current.input.includes('audio')) labels.push(t('providers.capabilities.audioInput'))
  if (current.tools) labels.push(t('providers.capabilities.tools'))
  if (current.reasoning) labels.push(t('providers.capabilities.reasoning'))
  if (current.context_window > 0) {
    const size =
      current.context_window >= 1_000_000
        ? `${Math.round(current.context_window / 1_000_000)}M`
        : `${Math.round(current.context_window / 1000)}K`
    labels.push(t('providers.capabilities.context', { size }))
  }
  return labels
})

const speechFormats = ['mp3', 'wav', 'opus', 'aac', 'flac']
const imageSizes = ['1024x1024', '1024x1536', '1536x1024', '512x512', '256x256']
const imageQualities = ['auto', 'high', 'medium', 'low', 'standard', 'hd']
const responseFormats = ['', 'b64_json', 'url']

function applyPreset(id: string): void {
  presetId.value = id
  const preset = presetsForCategory.value.find((item) => item.id === id)
  if (!preset) {
    return
  }
  providerType.value = preset.provider_type
  baseUrl.value = preset.base_url
  if (!name.value.trim()) {
    name.value = preset.name
  }
  // Model names must come from the vendor's model list, not from a preset.
  model.value = ''
  modelOptions.value = []
  capabilities.value = null
  modelsMessage.value = ''
  modelsNeedKey.value = false
  errorMessage.value = ''
  if (activeCategory.value === 'speech') {
    voice.value =
      preset.voice ||
      (preset.provider_type === 'elevenlabs' ? '21m00Tcm4TlvDq8ikWAM' : 'alloy')
  }
}

function applyType(id: string): void {
  providerType.value = id
  const spec = providerTypes.value.find((item) => item.id === id)
  if (spec?.default_base_url && !baseUrl.value.trim()) {
    baseUrl.value = spec.default_base_url
  }
  if (id === 'elevenlabs' && (!voice.value || voice.value === 'alloy')) {
    voice.value = '21m00Tcm4TlvDq8ikWAM'
  }
  model.value = ''
  modelOptions.value = []
  capabilities.value = null
  modelsMessage.value = ''
  modelsNeedKey.value = false
  errorMessage.value = ''
}

function applyParameterPreset(value: string): void {
  parameterPreset.value = value
  if (value === 'balanced') {
    temperature.value = 0.7
    maxTokens.value = 2048
  } else if (value === 'precise') {
    temperature.value = 0.2
    maxTokens.value = 1024
  } else if (value === 'creative') {
    temperature.value = 1.0
    maxTokens.value = 4096
  }
}

function applyModelCapabilities(value: unknown): void {
  const modelId = textValue(value)
  const option = modelOptions.value.find((item) => item.id === modelId)
  capabilities.value = option?.capabilities ?? null
}

function onModelChange(value: unknown): void {
  const modelId = textValue(value)
  model.value = modelId
  applyModelCapabilities(modelId)
}

async function fetchModels(): Promise<void> {
  if (!baseUrl.value.trim()) {
    errorMessage.value = t('providers.dialog.required')
    return
  }
  const hasStoredKey = Boolean(props.provider?.api_key_set)
  if (apiKeyRequired.value && !apiKey.value.trim() && !hasStoredKey) {
    modelsNeedKey.value = true
    modelsMessage.value = ''
    errorMessage.value = ''
    return
  }
  modelsNeedKey.value = false
  modelsLoading.value = true
  modelsMessage.value = ''
  errorMessage.value = ''
  try {
    const result = await providersApi.fetchModels({
      provider_type: providerType.value,
      category: activeCategory.value,
      base_url: baseUrl.value.trim(),
      api_key: apiKey.value.trim(),
      provider_id: props.provider?.id,
      options: buildOptions(),
    })
    modelOptions.value = result.models
    modelsMessage.value =
      result.message ||
      t('providers.dialog.modelsFetched', { count: result.models.length })
    if (!model.value && result.models.length) {
      const preferred = selectedPreset.value?.models[activeCategory.value] ?? []
      const next =
        result.models.find((item) => preferred.includes(item.id)) ?? result.models[0]
      model.value = next.id
      applyModelCapabilities(model.value)
    } else if (model.value) {
      applyModelCapabilities(model.value)
    }
  } catch (error) {
    modelsMessage.value = `${t('providers.dialog.fetchModels')}: ${extractErrorMessage(error)}`
    modelOptions.value = []
  } finally {
    modelsLoading.value = false
  }
}

function resetForm(): void {
  const provider = props.provider
  name.value = provider?.name ?? ''
  baseUrl.value = provider?.base_url ?? ''
  apiKey.value = ''
  showApiKey.value = false
  model.value = provider?.model ?? ''
  providerType.value = provider?.provider_type ?? 'openai_compatible'
  isDefault.value = provider?.is_default ?? false
  enabled.value = provider?.enabled ?? true
  errorMessage.value = ''
  modelsNeedKey.value = false

  const options = (provider?.options ?? {}) as Record<string, unknown>
  apiVersion.value = String(options.api_version ?? '2024-10-21')
  groupId.value = String(options.group_id ?? '')
  temperature.value = (options.temperature as string | number) ?? (provider ? '' : 0.7)
  maxTokens.value = (options.max_tokens as string | number) ?? (provider ? '' : 2048)
  voice.value = String(
    options.voice ??
      (providerType.value === 'elevenlabs' ? '21m00Tcm4TlvDq8ikWAM' : 'alloy'),
  )
  audioFormat.value = String(options.response_format ?? 'mp3')
  speed.value = (options.speed as string | number) ?? (provider ? '' : 1.0)
  imageSize.value = String(options.size ?? '1024x1024')
  imageQuality.value = String(options.quality ?? '')
  imageCount.value = (options.n as string | number) ?? 1
  responseFormat.value = String(options.response_format ?? '')

  capabilities.value = provider?.capabilities ?? null
  modelOptions.value = provider?.model
    ? [
        {
          id: provider.model,
          name: provider.model,
          capabilities: provider.capabilities,
          owned_by: '',
        },
      ]
    : []
  modelsMessage.value = ''

  const temp = Number(temperature.value)
  const tokens = Number(maxTokens.value)
  if (temp === 0.7 && tokens === 2048) {
    parameterPreset.value = 'balanced'
  } else if (temp === 0.2 && tokens === 1024) {
    parameterPreset.value = 'precise'
  } else if (temp === 1.0 && tokens === 4096) {
    parameterPreset.value = 'creative'
  } else {
    parameterPreset.value = 'custom'
  }

  const matchedPreset = presetsForCategory.value.find(
    (preset) =>
      preset.provider_type === providerType.value &&
      preset.base_url === baseUrl.value,
  )
  presetId.value = matchedPreset?.id ?? ''
}

watch(
  () => [props.modelValue, props.provider, props.category, props.catalog] as const,
  ([open]) => {
    if (open) {
      resetForm()
    }
  },
  { immediate: true },
)

watch(apiKey, (value) => {
  if (modelsNeedKey.value && value.trim()) {
    modelsNeedKey.value = false
    errorMessage.value = ''
  }
})

function numberOrUndefined(value: string | number): number | undefined {
  if (value === '' || value === null || value === undefined) {
    return undefined
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function textValue(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }
  if (typeof value === 'number') {
    return String(value)
  }
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>
    return String(item.id ?? item.value ?? item.title ?? '')
  }
  return ''
}

function buildOptions(): Record<string, unknown> {
  const options: Record<string, unknown> = {}
  if (providerType.value === 'azure_openai') {
    options.api_version = apiVersion.value.trim() || '2024-10-21'
  }
  if (providerType.value === 'minimax' && groupId.value.trim()) {
    options.group_id = groupId.value.trim()
  }
  if (activeCategory.value === 'chat') {
    const temp = numberOrUndefined(temperature.value)
    const tokens = numberOrUndefined(maxTokens.value)
    if (temp !== undefined) options.temperature = temp
    if (tokens !== undefined) options.max_tokens = tokens
  } else if (activeCategory.value === 'speech') {
    options.voice = textValue(voice.value).trim() || 'alloy'
    options.response_format = audioFormat.value
    const spd = numberOrUndefined(speed.value)
    if (spd !== undefined) options.speed = spd
  } else {
    options.size = textValue(imageSize.value).trim() || '1024x1024'
    const count = numberOrUndefined(imageCount.value)
    if (count !== undefined) options.n = count
    if (textValue(imageQuality.value)) options.quality = textValue(imageQuality.value)
    if (responseFormat.value) options.response_format = responseFormat.value
  }
  return options
}

async function save(): Promise<void> {
  const nameValue = textValue(name.value).trim()
  const baseUrlValue = textValue(baseUrl.value).trim()
  const modelValue = textValue(model.value).trim()
  if (!nameValue || !baseUrlValue || !modelValue) {
    errorMessage.value = t('providers.dialog.required')
    return
  }

  saving.value = true
  errorMessage.value = ''
  try {
    let result: ModelProvider
    if (isEdit.value && props.provider) {
      const payload: ProviderUpdatePayload = {
        name: nameValue,
        provider_type: providerType.value,
        base_url: baseUrlValue,
        model: modelValue,
        options: buildOptions(),
        capabilities: capabilities.value ?? undefined,
        is_default: isDefault.value,
        enabled: enabled.value,
      }
      const apiKeyValue = textValue(apiKey.value).trim()
      if (apiKeyValue) {
        payload.api_key = apiKeyValue
      }
      result = await providersApi.update(props.provider.id, payload)
    } else {
      const payload: ProviderPayload = {
        category: activeCategory.value,
        name: nameValue,
        provider_type: providerType.value,
        base_url: baseUrlValue,
        api_key: textValue(apiKey.value).trim(),
        model: modelValue,
        options: buildOptions(),
        capabilities: capabilities.value ?? undefined,
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

        <v-form autocomplete="off" @submit.prevent="save">
          <div class="form-row form-row--two">
            <div class="field">
              <label>{{ t('providers.dialog.preset') }}</label>
              <v-select
                v-model="presetId"
                :items="presetItems"
                item-title="name"
                item-value="id"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="t('providers.dialog.presetPlaceholder')"
                @update:model-value="applyPreset"
              />
            </div>
            <div class="field">
              <label>{{ t('providers.dialog.name') }}</label>
              <v-text-field
                v-model="name"
                name="provider-name"
                autocomplete="off"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="t('providers.dialog.namePlaceholder')"
              />
            </div>
          </div>

          <div class="form-row form-row--two">
            <div class="field">
              <label>{{ t('providers.dialog.providerType') }}</label>
              <v-select
                v-model="providerType"
                :items="providerTypes"
                item-title="name"
                item-value="id"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                @update:model-value="applyType"
              />
            </div>
            <div class="field">
              <label>{{ t('providers.dialog.baseUrl') }}</label>
              <v-text-field
                v-model="baseUrl"
                name="provider-base-url"
                autocomplete="off"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="t('providers.dialog.baseUrlPlaceholder')"
                prepend-inner-icon="mdi-api"
              />
            </div>
          </div>
          <p class="field-hint">{{ t('providers.dialog.providerTypeHint') }}</p>

          <div v-if="providerType === 'azure_openai'" class="field">
            <label>{{ t('providers.dialog.apiVersion') }}</label>
            <v-text-field
              v-model="apiVersion"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
              :placeholder="t('providers.dialog.apiVersionHint')"
            />
          </div>

          <div v-if="providerType === 'minimax'" class="field">
            <label>{{ t('providers.dialog.groupId') }}</label>
            <v-text-field
              v-model="groupId"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
              :placeholder="t('providers.dialog.groupIdPlaceholder')"
            />
          </div>
          <p v-if="providerType === 'minimax'" class="field-hint group-id-hint">
            {{ t('providers.dialog.groupIdHint') }}
          </p>

          <div class="form-row form-row--two">
            <div class="field">
              <label>{{ t('providers.dialog.apiKey') }}</label>
              <v-text-field
                v-model="apiKey"
                type="text"
                name="provider-api-key"
                autocomplete="off"
                class="api-key-field"
                :class="{ 'api-key-field--visible': showApiKey }"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="
                  isEdit
                    ? t('providers.dialog.apiKeyEditPlaceholder')
                    : t('providers.dialog.apiKeyPlaceholder')
                "
                prepend-inner-icon="mdi-key-outline"
              >
                <template #append-inner>
                  <v-btn
                    icon
                    variant="text"
                    size="x-small"
                    type="button"
                    :aria-label="
                      showApiKey
                        ? t('providers.dialog.hideApiKey')
                        : t('providers.dialog.showApiKey')
                    "
                    @click.stop="showApiKey = !showApiKey"
                  >
                    <v-icon size="17">
                      {{ showApiKey ? 'mdi-eye-off' : 'mdi-eye' }}
                    </v-icon>
                  </v-btn>
                </template>
              </v-text-field>
            </div>
            <div class="field">
              <label>{{ t('providers.dialog.model') }}</label>
              <v-combobox
                v-model="model"
                name="provider-model"
                autocomplete="off"
                :items="modelOptions"
                item-title="id"
                item-value="id"
                :return-object="false"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                :placeholder="modelPlaceholder"
                prepend-inner-icon="mdi-cube-outline"
                :loading="modelsLoading"
                @update:model-value="onModelChange"
              >
                <template #append>
                  <v-btn
                    icon
                    variant="text"
                    size="x-small"
                    :loading="modelsLoading"
                    :aria-label="t('providers.dialog.fetchModels')"
                    @click.stop="fetchModels"
                  >
                    <v-icon size="17">mdi-refresh</v-icon>
                    <v-tooltip activator="parent" location="top">
                      {{ t('providers.dialog.fetchModels') }}
                    </v-tooltip>
                  </v-btn>
                </template>
              </v-combobox>
            </div>
          </div>
          <div class="field-hints">
            <p class="field-hint">{{ t('providers.dialog.apiKeyHint') }}</p>
            <p class="field-hint" :class="{ 'field-hint--warning': modelsNeedKey }">
              {{
                modelsNeedKey
                  ? t('providers.dialog.modelsNeedApiKey')
                  : modelsMessage || t('providers.dialog.fetchModelsHint')
              }}
            </p>
          </div>
          <div v-if="capabilityLabels.length" class="capability-chips">
            <span class="capability-label">{{ t('providers.dialog.capabilities') }}</span>
            <v-chip v-for="label in capabilityLabels" :key="label" size="x-small" variant="tonal">
              {{ label }}
            </v-chip>
          </div>

          <div class="options-panel">
            <p class="options-title">{{ t('providers.dialog.advanced') }}</p>

            <div v-if="activeCategory === 'chat'" class="form-row form-row--two">
              <div class="field">
                <label>{{ t('providers.dialog.parameterPreset') }}</label>
                <v-select
                  v-model="parameterPreset"
                  :items="parameterPresetItems"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  @update:model-value="applyParameterPreset"
                />
              </div>
            </div>
            <p v-if="activeCategory === 'chat'" class="field-hint options-hint">
              {{ t('providers.dialog.chatHint') }}
            </p>

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
                  @update:model-value="parameterPreset = 'custom'"
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
                  @update:model-value="parameterPreset = 'custom'"
                />
              </div>
            </div>

            <div v-else-if="activeCategory === 'speech'" class="form-row form-row--three">
              <div class="field">
                <label>{{ t('providers.dialog.voice') }}</label>
                <v-combobox
                  v-model="voice"
                  :items="['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']"
                  :return-object="false"
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
            <p v-if="activeCategory === 'speech'" class="field-hint options-hint">
              {{ t('providers.dialog.speechHint') }}
            </p>

            <div v-if="activeCategory === 'image'" class="form-row form-row--two">
              <div class="field">
                <label>{{ t('providers.dialog.imageSize') }}</label>
                <v-combobox
                  v-model="imageSize"
                  :items="imageSizes"
                  :return-object="false"
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
                  :return-object="false"
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
            <p v-if="activeCategory === 'image'" class="field-hint options-hint">
              {{ t('providers.dialog.imageHint') }}
            </p>
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

.api-key-field :deep(input) {
  -webkit-text-security: disc;
}

.api-key-field--visible :deep(input) {
  -webkit-text-security: none;
}

.field-hint {
  margin: -4px 0 16px;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.field-hints {
  margin: 2px 0 14px;
}

.field-hints .field-hint {
  margin: 0 0 4px;
}

.group-id-hint {
  margin: 8px 0 16px;
}

.field-hint--warning {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}

.capability-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 16px;
}

.capability-label {
  color: var(--mori-muted);
  font-size: 10.5px;
  font-weight: 600;
}

.options-hint {
  margin: 4px 0 12px;
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
