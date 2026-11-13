<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { charactersApi } from '@/api/characters'
import { extractErrorMessage } from '@/api/http'
import { providersApi } from '@/api/providers'
import CharacterDialog from '@/components/CharacterDialog.vue'
import type { CharacterCard, ModelProvider, ProviderCategory } from '@/types/api'

const { t } = useI18n()

const characters = ref<CharacterCard[]>([])
const providers = ref<ModelProvider[]>([])
const loading = ref(true)
const errorMessage = ref('')
const dialogOpen = ref(false)
const editingCharacter = ref<CharacterCard | null>(null)
const updatingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const snackbar = ref({ show: false, message: '', color: 'success' })

const enabledCount = computed(
  () => characters.value.filter((character) => character.enabled).length,
)

const categoryIcons: Record<ProviderCategory, string> = {
  chat: 'mdi-robot-outline',
  speech: 'mdi-volume-high',
  image: 'mdi-image-outline',
}

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

async function loadCharacters(): Promise<void> {
  try {
    characters.value = await charactersApi.list()
  } catch (error) {
    errorMessage.value = `${t('characters.loadFailed')}: ${extractErrorMessage(error)}`
  }
}

async function loadProviders(): Promise<void> {
  try {
    providers.value = await providersApi.list()
  } catch (error) {
    errorMessage.value = `${t('characters.loadProvidersFailed')}: ${extractErrorMessage(error)}`
  }
}

async function loadAll(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  await Promise.all([loadCharacters(), loadProviders()])
  loading.value = false
}

function openCreate(): void {
  editingCharacter.value = null
  dialogOpen.value = true
}

function openEdit(character: CharacterCard): void {
  editingCharacter.value = character
  dialogOpen.value = true
}

async function handleSaved(): Promise<void> {
  const wasEditing = editingCharacter.value !== null
  editingCharacter.value = null
  await loadCharacters()
  showSnackbar(
    wasEditing ? t('characters.updated') : t('characters.created'),
    'success',
  )
}

function defaultProvider(category: ProviderCategory): ModelProvider | null {
  return (
    providers.value.find(
      (provider) =>
        provider.category === category && provider.is_default && provider.enabled,
    ) ??
    providers.value.find((provider) => provider.category === category && provider.enabled) ??
    null
  )
}

function selectedProvider(category: ProviderCategory, id: number | null): ModelProvider | null {
  if (id === null) {
    return defaultProvider(category)
  }
  return providers.value.find((provider) => provider.id === id) ?? null
}

function modelLabel(category: ProviderCategory, id: number | null): string {
  const provider = selectedProvider(category, id)
  if (!provider) {
    return id === null
      ? `${t('characters.followDefault')} · ${t('characters.noModel')}`
      : t('characters.missingProvider')
  }
  return id === null
    ? `${t('characters.followDefault')} · ${provider.model}`
    : `${provider.name} · ${provider.model}`
}

function providerMissing(category: ProviderCategory, id: number | null): boolean {
  return id !== null && !selectedProvider(category, id)
}

function avatarInitial(character: CharacterCard): string {
  return character.name.trim().charAt(0).toUpperCase() || '?'
}

async function toggleEnabled(character: CharacterCard, value: boolean | null): Promise<void> {
  if (value === null || value === character.enabled) {
    return
  }
  updatingId.value = character.id
  try {
    const updated = await charactersApi.update(character.id, { enabled: value })
    const index = characters.value.findIndex((item) => item.id === character.id)
    if (index >= 0) {
      characters.value[index] = updated
    }
    showSnackbar(t('characters.updated'), 'success')
  } catch (error) {
    showSnackbar(`${t('characters.saveFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    updatingId.value = null
  }
}

async function removeCharacter(character: CharacterCard): Promise<void> {
  if (!window.confirm(t('characters.deleteConfirm', { name: character.name }))) {
    return
  }
  deletingId.value = character.id
  try {
    await charactersApi.remove(character.id)
    await loadCharacters()
    showSnackbar(t('characters.deleted'), 'success')
  } catch (error) {
    showSnackbar(`${t('characters.deleteFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="characters-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('characters.eyebrow') }}</p>
        <h1>{{ t('characters.title') }}</h1>
        <p class="page-subtitle">{{ t('characters.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <span class="count-chip">
          {{ t('characters.count', { count: characters.length, enabled: enabledCount }) }}
        </span>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">
          {{ t('characters.add') }}
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

    <div v-if="loading" class="loading-state">
      <v-progress-circular indeterminate size="24" width="2" />
      {{ t('characters.loading') }}
    </div>

    <div v-else-if="characters.length === 0" class="empty-state">
      <span class="empty-icon"><v-icon size="26">mdi-account-box-multiple-outline</v-icon></span>
      <div>
        <h3>{{ t('characters.emptyTitle') }}</h3>
        <p>{{ t('characters.emptyDescription') }}</p>
      </div>
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openCreate">
        {{ t('characters.add') }}
      </v-btn>
    </div>

    <div v-else class="character-grid">
      <article
        v-for="character in characters"
        :key="character.id"
        class="character-card"
        :class="{ 'character-card--disabled': !character.enabled }"
      >
        <div class="card-top">
          <div class="avatar">
            <img
              v-if="character.avatar"
              :src="character.avatar"
              :alt="character.name"
              loading="lazy"
            />
            <span v-else>{{ avatarInitial(character) }}</span>
          </div>
          <div class="title-block">
            <div class="title-row">
              <h3>{{ character.name }}</h3>
              <span v-if="!character.enabled" class="disabled-chip">
                {{ t('characters.disabled') }}
              </span>
            </div>
            <p class="description">
              {{ character.description || t('characters.noDescription') }}
            </p>
          </div>
          <v-switch
            :model-value="character.enabled"
            color="primary"
            density="compact"
            hide-details
            class="enable-switch"
            :loading="updatingId === character.id"
            @update:model-value="toggleEnabled(character, $event)"
          />
        </div>

        <div class="model-chips">
          <span
            v-for="category in (['chat', 'speech', 'image'] as ProviderCategory[])"
            :key="category"
            class="model-chip"
            :class="{
              'model-chip--override':
                category === 'chat'
                  ? character.chat_provider_id !== null
                  : category === 'speech'
                    ? character.speech_provider_id !== null
                    : character.image_provider_id !== null,
              'model-chip--missing': providerMissing(
                category,
                category === 'chat'
                  ? character.chat_provider_id
                  : category === 'speech'
                    ? character.speech_provider_id
                    : character.image_provider_id,
              ),
            }"
            :title="
              modelLabel(
                category,
                category === 'chat'
                  ? character.chat_provider_id
                  : category === 'speech'
                    ? character.speech_provider_id
                    : character.image_provider_id,
              )
            "
          >
            <v-icon size="13">{{ categoryIcons[category] }}</v-icon>
            <span>
              {{
                modelLabel(
                  category,
                  category === 'chat'
                    ? character.chat_provider_id
                    : category === 'speech'
                      ? character.speech_provider_id
                      : character.image_provider_id,
                )
              }}
            </span>
          </span>
        </div>

        <footer class="card-actions">
          <v-btn variant="text" size="small" @click="openEdit(character)">
            {{ t('characters.edit') }}
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            color="error"
            :loading="deletingId === character.id"
            @click="removeCharacter(character)"
          >
            {{ t('characters.delete') }}
          </v-btn>
        </footer>
      </article>
    </div>

    <CharacterDialog
      v-model="dialogOpen"
      :character="editingCharacter"
      :providers="providers"
      @saved="handleSaved"
    />

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3400">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<style scoped lang="scss">
.characters-page {
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

.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 34px;
  color: var(--mori-muted);
  font-size: 12px;
}

.empty-state {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 28px;
  padding: 22px;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 18px;
  background: var(--mori-panel);
}

.empty-icon {
  display: grid;
  width: 48px;
  height: 48px;
  flex: none;
  place-items: center;
  border-radius: 14px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
}

.empty-state h3 {
  margin: 0;
  color: var(--mori-text);
  font-size: 15px;
  font-weight: 600;
}

.empty-state p {
  margin: 5px 0 0;
  color: var(--mori-muted);
  font-size: 11.5px;
}

.empty-state .v-btn {
  margin-left: auto;
}

.character-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
  margin-top: 26px;
}

.character-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 18px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
  transition:
    border-color 0.18s ease,
    transform 0.18s ease;
}

.character-card:hover {
  border-color: color-mix(in srgb, var(--mori-mint) 30%, var(--mori-line));
  transform: translateY(-1px);
}

.character-card--disabled {
  opacity: 0.66;
}

.card-top {
  display: flex;
  align-items: flex-start;
  gap: 13px;
}

.avatar {
  display: grid;
  width: 58px;
  height: 58px;
  flex: none;
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--mori-line);
  border-radius: 16px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 21px;
  font-weight: 600;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.title-block {
  min-width: 0;
  flex: 1;
}

.title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
}

.title-row h3 {
  overflow: hidden;
  margin: 2px 0 0;
  color: var(--mori-text);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.disabled-chip {
  padding: 2px 7px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  color: var(--mori-muted);
  font-size: 9px;
}

.description {
  display: -webkit-box;
  overflow: hidden;
  margin: 6px 0 0;
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.6;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.enable-switch {
  flex: none;
  margin: -6px -4px 0 0;
}

.model-chips {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--mori-line);
}

.model-chip {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  padding: 5px 8px;
  border: 1px solid var(--mori-line);
  border-radius: 8px;
  color: var(--mori-muted);
  font-size: 10px;
}

.model-chip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-chip--override {
  border-color: color-mix(in srgb, var(--mori-mint) 30%, var(--mori-line));
  background: var(--mori-mint-soft);
  color: var(--mori-text);
}

.model-chip--missing {
  border-color: color-mix(in srgb, rgb(var(--v-theme-error)) 35%, var(--mori-line));
  color: rgb(var(--v-theme-error));
}

.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 14px;
}

@media (max-width: 760px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .head-actions {
    width: 100%;
    justify-content: space-between;
  }

  .character-grid {
    grid-template-columns: 1fr;
  }

  .empty-state {
    align-items: flex-start;
    flex-direction: column;
  }

  .empty-state .v-btn {
    margin-left: 0;
  }
}
</style>
