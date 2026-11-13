<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { charactersApi } from '@/api/characters'
import { extractErrorMessage } from '@/api/http'
import type {
  CharacterCard,
  CharacterPayload,
  CharacterUpdatePayload,
  ModelProvider,
  ProviderCategory,
} from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  character: CharacterCard | null
  providers: ModelProvider[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [character: CharacterCard]
}>()

const { t } = useI18n()

const name = ref('')
const avatar = ref('')
const description = ref('')
const persona = ref('')
const chatProviderId = ref(0)
const speechProviderId = ref(0)
const imageProviderId = ref(0)
const enabled = ref(true)
const errorMessage = ref('')
const saving = ref(false)
const avatarUploading = ref(false)
const avatarInput = ref<HTMLInputElement | null>(null)
const previewOpen = ref(false)

const dialogOpen = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const isEdit = computed(() => props.character !== null)
const avatarInitial = computed(() => name.value.trim().charAt(0).toUpperCase() || '?')

function providerOptions(category: ProviderCategory) {
  const items = [
    { title: t('characters.followDefault'), value: 0 },
    ...props.providers
      .filter((provider) => provider.category === category)
      .map((provider) => ({
        title: `${provider.name} · ${provider.model}${
          provider.is_default ? ` · ${t('characters.systemDefault')}` : ''
        }${provider.enabled ? '' : ` · ${t('characters.disabled')}`}`,
        value: provider.id,
      })),
  ]
  return items
}

function hasProviders(category: ProviderCategory): boolean {
  return props.providers.some((provider) => provider.category === category)
}

function resetForm(): void {
  const character = props.character
  name.value = character?.name ?? ''
  avatar.value = character?.avatar ?? ''
  description.value = character?.description ?? ''
  persona.value = character?.persona ?? ''
  chatProviderId.value = character?.chat_provider_id ?? 0
  speechProviderId.value = character?.speech_provider_id ?? 0
  imageProviderId.value = character?.image_provider_id ?? 0
  enabled.value = character?.enabled ?? true
  errorMessage.value = ''
  avatarUploading.value = false
  previewOpen.value = false
}

watch(
  () => [props.modelValue, props.character] as const,
  ([open]) => {
    if (open) {
      resetForm()
    }
  },
  { immediate: true },
)

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

async function handleAvatarFiles(value: File | File[] | null): Promise<void> {
  const file = Array.isArray(value) ? value[0] : value
  if (!file) {
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    errorMessage.value = t('characters.avatarTooLarge')
    return
  }
  avatarUploading.value = true
  errorMessage.value = ''
  try {
    const dataUrl = await readFileAsDataUrl(file)
    const result = await charactersApi.uploadAvatar(dataUrl)
    avatar.value = result.url
  } catch (error) {
    errorMessage.value = `${t('characters.avatarUploadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    avatarUploading.value = false
  }
}

function triggerAvatarUpload(): void {
  avatarInput.value?.click()
}

async function onAvatarFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  await handleAvatarFiles(file)
}

async function save(): Promise<void> {
  if (!name.value.trim()) {
    errorMessage.value = t('characters.nameRequired')
    return
  }
  saving.value = true
  errorMessage.value = ''
  const payload: CharacterPayload = {
    name: name.value.trim(),
    avatar: avatar.value.trim(),
    description: description.value.trim(),
    persona: persona.value,
    chat_provider_id: chatProviderId.value || null,
    speech_provider_id: speechProviderId.value || null,
    image_provider_id: imageProviderId.value || null,
    enabled: enabled.value,
  }
  try {
    let result: CharacterCard
    if (isEdit.value && props.character) {
      result = await charactersApi.update(
        props.character.id,
        payload as CharacterUpdatePayload,
      )
    } else {
      result = await charactersApi.create(payload)
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
  <v-dialog v-model="dialogOpen" max-width="780" scrollable>
    <v-card class="character-dialog">
      <header class="dialog-head">
        <div>
          <p class="mori-eyebrow">{{ t('characters.eyebrow') }}</p>
          <h2>{{ isEdit ? t('characters.editTitle') : t('characters.createTitle') }}</h2>
        </div>
        <v-btn icon variant="text" size="small" @click="dialogOpen = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </header>

      <v-card-text class="dialog-body">
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          density="compact"
          class="dialog-error"
        >
          {{ errorMessage }}
        </v-alert>

        <div class="avatar-editor">
          <div class="avatar-preview" :class="{ 'avatar-preview--empty': !avatar }">
            <img v-if="avatar" :src="avatar" :alt="name || t('characters.avatar')" />
            <span v-else>{{ avatarInitial }}</span>
            <div class="avatar-actions">
              <v-btn
                icon
                size="x-small"
                variant="flat"
                color="white"
                :loading="avatarUploading"
                :aria-label="t('characters.avatarUpload')"
                @click.stop="triggerAvatarUpload"
              >
                <v-icon size="16">mdi-upload</v-icon>
                <v-tooltip activator="parent" location="top">
                  {{ t('characters.avatarUpload') }}
                </v-tooltip>
              </v-btn>
              <v-btn
                icon
                size="x-small"
                variant="flat"
                color="white"
                :disabled="!avatar"
                :aria-label="t('characters.avatarPreview')"
                @click.stop="previewOpen = true"
              >
                <v-icon size="16">mdi-eye</v-icon>
                <v-tooltip activator="parent" location="top">
                  {{ t('characters.avatarPreview') }}
                </v-tooltip>
              </v-btn>
            </div>
            <input
              ref="avatarInput"
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              class="avatar-input"
              @change="onAvatarFileChange"
            />
          </div>
          <div class="avatar-fields">
            <label>{{ t('characters.avatar') }}</label>
            <p class="avatar-state">
              {{ avatar ? name || t('characters.avatar') : t('characters.avatarEmpty') }}
            </p>
            <p class="field-hint">{{ t('characters.avatarHoverHint') }}</p>
            <p class="field-hint">{{ t('characters.avatarHint') }}</p>
          </div>
        </div>

        <div class="form-row form-row--two">
          <div class="field">
            <label>{{ t('characters.name') }}</label>
            <v-text-field
              v-model="name"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
              :placeholder="t('characters.namePlaceholder')"
              prepend-inner-icon="mdi-account-outline"
            />
          </div>
          <div class="field switch-field">
            <v-switch
              v-model="enabled"
              color="primary"
              density="compact"
              hide-details
              :label="t('characters.enabled')"
            />
          </div>
        </div>

        <div class="field">
          <label>{{ t('characters.description') }}</label>
          <v-text-field
            v-model="description"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
            :placeholder="t('characters.descriptionPlaceholder')"
          />
        </div>

        <div class="field">
          <label>{{ t('characters.persona') }}</label>
          <v-textarea
            v-model="persona"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
            rows="8"
            :placeholder="t('characters.personaPlaceholder')"
          />
          <p class="field-hint">{{ t('characters.personaHint') }}</p>
        </div>

        <div class="model-panel">
          <div class="model-panel-head">
            <p class="options-title">{{ t('characters.modelSettings') }}</p>
            <p class="model-hint">{{ t('characters.modelHint') }}</p>
          </div>
          <div class="form-row form-row--three">
            <div class="field">
              <label>{{ t('characters.chatModel') }}</label>
              <v-select
                v-model="chatProviderId"
                :items="providerOptions('chat')"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
              />
              <p v-if="!hasProviders('chat')" class="field-hint">
                {{ t('characters.noProviders') }}
              </p>
            </div>
            <div class="field">
              <label>{{ t('characters.speechModel') }}</label>
              <v-select
                v-model="speechProviderId"
                :items="providerOptions('speech')"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
              />
              <p v-if="!hasProviders('speech')" class="field-hint">
                {{ t('characters.noProviders') }}
              </p>
            </div>
            <div class="field">
              <label>{{ t('characters.imageModel') }}</label>
              <v-select
                v-model="imageProviderId"
                :items="providerOptions('image')"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
              />
              <p v-if="!hasProviders('image')" class="field-hint">
                {{ t('characters.noProviders') }}
              </p>
            </div>
          </div>
        </div>

        <div class="dialog-actions">
          <v-btn variant="text" @click="dialogOpen = false">
            {{ t('characters.cancel') }}
          </v-btn>
          <v-btn color="primary" :loading="saving" @click="save">
            {{ saving ? t('characters.saving') : t('characters.save') }}
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>

  <v-dialog v-model="previewOpen" max-width="620">
    <v-card v-if="avatar" class="avatar-preview-dialog">
      <img :src="avatar" :alt="name || t('characters.avatar')" />
      <v-btn
        icon
        variant="flat"
        size="small"
        class="preview-close"
        :aria-label="t('characters.cancel')"
        @click="previewOpen = false"
      >
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </v-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.character-dialog {
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

.avatar-editor {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  margin-bottom: 18px;
}

.avatar-preview {
  position: relative;
  display: grid;
  width: 92px;
  height: 92px;
  flex: none;
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--mori-line);
  border-radius: 20px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 30px;
  font-weight: 600;
}

.avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-input {
  display: none;
}

.avatar-actions {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  background: rgb(0 0 0 / 42%);
  opacity: 0;
  transition: opacity 0.16s ease;
}

.avatar-preview:hover .avatar-actions,
.avatar-preview:focus-within .avatar-actions {
  opacity: 1;
}

.avatar-fields {
  min-width: 0;
  flex: 1;
}

.avatar-state {
  margin: 2px 0 0;
  color: var(--mori-text);
  font-size: 12px;
  font-weight: 600;
}

.avatar-fields label,
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
  margin-bottom: 14px;
}

.switch-field {
  display: flex;
  align-items: flex-end;
  padding-bottom: 4px;
}

.field-hint {
  margin: 6px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.model-panel {
  margin: 4px 0 18px;
  padding: 16px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel-2);
}

.model-panel-head {
  margin-bottom: 14px;
}

.model-panel .options-title {
  margin: 0;
  color: var(--mori-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.model-hint {
  margin: 7px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
}

.model-panel .form-row {
  margin-bottom: 0;
}

.model-panel .field {
  margin-bottom: 0;
}

.model-panel :deep(.v-field) {
  background: var(--mori-panel);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

.avatar-preview-dialog {
  position: relative;
  padding: 10px;
  background: var(--mori-panel) !important;
}

.avatar-preview-dialog img {
  display: block;
  width: 100%;
  max-height: 72vh;
  border-radius: 12px;
  object-fit: contain;
}

.preview-close {
  position: absolute;
  top: 18px;
  right: 18px;
}

@media (hover: none) {
  .avatar-actions {
    align-items: flex-end;
    justify-content: flex-end;
    padding: 6px;
    background: transparent;
    opacity: 1;
  }

  .avatar-actions :deep(.v-btn) {
    background: rgb(0 0 0 / 55%) !important;
  }
}

@media (max-width: 680px) {
  .dialog-head {
    padding: 22px 20px 0;
  }

  .dialog-body {
    padding: 18px 20px 22px !important;
  }

  .avatar-editor {
    flex-direction: column;
  }

  .form-row--two,
  .form-row--three {
    grid-template-columns: 1fr;
  }
}
</style>
