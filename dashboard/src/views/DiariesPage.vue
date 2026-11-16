<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { charactersApi } from '@/api/characters'
import { diariesApi } from '@/api/diaries'
import { extractErrorMessage } from '@/api/http'
import type { CharacterCard, DiaryEntry } from '@/types/api'

const { t } = useI18n()

const diaries = ref<DiaryEntry[]>([])
const characters = ref<CharacterCard[]>([])
const filterCharacter = ref<number | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const snackbar = ref({ show: false, message: '', color: 'success' })
const selectedDiary = ref<DiaryEntry | null>(null)
const generatingId = ref<number | null>(null)
const generateOpen = ref(false)
const generateCharacterId = ref<number | null>(null)
const generateDate = ref('')
const generating = ref(false)

const characterOptions = computed(() => {
  const items: Array<{
    title: string
    value: number | null
    props?: { disabled: boolean }
  }> = [{ title: t('diaries.allCharacters'), value: null }]
  if (characters.value.length === 0) {
    items.push({
      title: t('diaries.noCharacters'),
      value: 0,
      props: { disabled: true },
    })
  }
  items.push(
    ...characters.value.map((character) => ({
      title: character.enabled
        ? character.name
        : `${character.name} · ${t('characters.disabled')}`,
      value: character.id as number | null,
    })),
  )
  return items
})
const filteredCharacters = computed(() => characters.value.filter((item) => item.enabled))
const canGenerate = computed(
  () => generateCharacterId.value !== null && Boolean(generateDate.value),
)

function today(): string {
  const now = new Date()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

async function loadCharacters(): Promise<void> {
  try {
    characters.value = await charactersApi.list()
  } catch {
    characters.value = []
  }
}

async function loadDiaries(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    diaries.value = await diariesApi.list({
      character_id: filterCharacter.value ?? undefined,
      limit: 200,
    })
  } catch (error) {
    errorMessage.value = `${t('diaries.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function loadAll(): Promise<void> {
  await Promise.all([loadCharacters(), loadDiaries()])
}

function openGenerate(): void {
  if (filteredCharacters.value.length === 0) {
    showSnackbar(t('diaries.noCharacters'), 'error')
    return
  }
  generateCharacterId.value = filterCharacter.value ?? filteredCharacters.value[0].id
  generateDate.value = today()
  generateOpen.value = true
}

async function generateNow(): Promise<void> {
  if (!canGenerate.value || generateCharacterId.value === null) {
    return
  }
  generating.value = true
  try {
    await diariesApi.generate(generateCharacterId.value, generateDate.value)
    generateOpen.value = false
    await loadDiaries()
    showSnackbar(t('diaries.generated'), 'success')
  } catch (error) {
    showSnackbar(`${t('diaries.generateFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    generating.value = false
  }
}

async function regenerate(diary: DiaryEntry): Promise<void> {
  generatingId.value = diary.id
  try {
    await diariesApi.generate(diary.character_id, diary.date)
    await loadDiaries()
    showSnackbar(t('diaries.generated'), 'success')
  } catch (error) {
    showSnackbar(`${t('diaries.generateFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    generatingId.value = null
  }
}

async function removeDiary(diary: DiaryEntry): Promise<void> {
  if (!window.confirm(t('diaries.deleteConfirm', { name: diary.character_name }))) {
    return
  }
  try {
    await diariesApi.remove(diary.id)
    if (selectedDiary.value?.id === diary.id) {
      selectedDiary.value = null
    }
    await loadDiaries()
    showSnackbar(t('diaries.deleted'), 'success')
  } catch (error) {
    showSnackbar(`${t('diaries.deleteFailed')}: ${extractErrorMessage(error)}`, 'error')
  }
}

function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || '?'
}

watch(filterCharacter, () => {
  void loadDiaries()
})

onMounted(() => {
  void loadAll()
})
</script>

<template>
  <div class="diaries-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('diaries.eyebrow') }}</p>
        <h1>{{ t('diaries.title') }}</h1>
        <p class="page-subtitle">{{ t('diaries.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <v-select
          v-model="filterCharacter"
          :items="characterOptions"
          density="compact"
          variant="outlined"
          hide-details
          class="character-filter"
          :aria-label="t('diaries.filterCharacter')"
        />
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="loadAll">
          {{ t('diaries.refresh') }}
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-notebook-plus-outline" @click="openGenerate">
          {{ t('diaries.generate') }}
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
      {{ t('diaries.loading') }}
    </div>

    <div v-else-if="diaries.length === 0" class="empty-state">
      <span class="empty-icon"><v-icon size="26">mdi-notebook-outline</v-icon></span>
      <div>
        <h3>{{ t('diaries.emptyTitle') }}</h3>
        <p>{{ t('diaries.emptyDescription') }}</p>
      </div>
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-notebook-plus-outline" @click="openGenerate">
        {{ t('diaries.generate') }}
      </v-btn>
    </div>

    <div v-else class="diary-grid">
      <article v-for="diary in diaries" :key="diary.id" class="diary-card">
        <header class="diary-head">
          <div class="avatar">
            <img
              v-if="diary.character_avatar"
              :src="diary.character_avatar"
              :alt="diary.character_name"
              loading="lazy"
            />
            <span v-else>{{ initial(diary.character_name) }}</span>
          </div>
          <div class="diary-title">
            <strong>{{ diary.character_name }}</strong>
            <span>{{ diary.date }}</span>
          </div>
          <v-chip size="x-small" variant="tonal" color="primary">
            {{ diary.model || t('diaries.noModel') }}
          </v-chip>
        </header>

        <p class="diary-content">{{ diary.content }}</p>

        <footer class="diary-actions">
          <span class="diary-meta">
            {{ t('diaries.sourceMessages', { count: diary.source_message_count }) }}
          </span>
          <v-spacer />
          <v-btn variant="text" size="small" @click="selectedDiary = diary">
            {{ t('diaries.view') }}
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            :loading="generatingId === diary.id"
            @click="regenerate(diary)"
          >
            {{ t('diaries.regenerate') }}
          </v-btn>
          <v-btn variant="text" size="small" color="error" @click="removeDiary(diary)">
            {{ t('diaries.delete') }}
          </v-btn>
        </footer>
      </article>
    </div>

    <v-dialog :model-value="selectedDiary !== null" max-width="720" scrollable @update:model-value="selectedDiary = null">
      <v-card v-if="selectedDiary" class="diary-dialog">
        <header class="diary-dialog-head">
          <div>
            <p class="mori-eyebrow">{{ t('diaries.eyebrow') }}</p>
            <h2>{{ selectedDiary.character_name }} · {{ selectedDiary.date }}</h2>
          </div>
          <v-btn icon variant="text" size="small" @click="selectedDiary = null">
            <v-icon>mdi-close</v-icon>
            <v-tooltip activator="parent" location="bottom">{{ t('diaries.close') }}</v-tooltip>
          </v-btn>
        </header>
        <v-card-text class="diary-dialog-body">
          <p class="diary-full-content">{{ selectedDiary.content }}</p>
          <p class="diary-dialog-meta">
            {{ t('diaries.sourceMessages', { count: selectedDiary.source_message_count }) }}
          </p>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="generateOpen" max-width="480">
      <v-card class="generate-dialog">
        <v-card-title>{{ t('diaries.generateTitle') }}</v-card-title>
        <v-card-text>
          <v-select
            v-model="generateCharacterId"
            :items="filteredCharacters.map((item) => ({ title: item.name, value: item.id }))"
            :label="t('diaries.character')"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model="generateDate"
            type="date"
            :label="t('diaries.date')"
            variant="outlined"
            density="comfortable"
          />
          <p class="generate-hint">{{ t('diaries.generateHint') }}</p>
        </v-card-text>
        <v-card-actions>
          <v-btn variant="text" @click="generateOpen = false">{{ t('diaries.cancel') }}</v-btn>
          <v-spacer />
          <v-btn color="primary" :loading="generating" :disabled="!canGenerate" @click="generateNow">
            {{ t('diaries.generate') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3400">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<style scoped lang="scss">
.diaries-page {
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

.character-filter {
  width: 190px;
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
  font-size: 14px;
  font-weight: 600;
}

.empty-state p {
  margin: 5px 0 0;
  color: var(--mori-muted);
  font-size: 12px;
}

.empty-state .v-btn {
  margin-left: auto;
}

.diary-grid {
  display: grid;
  margin-top: 24px;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.diary-card {
  display: flex;
  min-height: 230px;
  flex-direction: column;
  padding: 20px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
  box-shadow: 0 1px 0 rgb(255 255 255 / 35%) inset;
}

.diary-head {
  display: flex;
  align-items: center;
  gap: 11px;
}

.avatar {
  display: grid;
  width: 42px;
  height: 42px;
  flex: none;
  place-items: center;
  overflow: hidden;
  border-radius: 50%;
  background: var(--mori-mint-soft);
  color: var(--mori-mint);
  font-weight: 700;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.diary-title {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.diary-title strong {
  overflow: hidden;
  color: var(--mori-text);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diary-title span {
  color: var(--mori-muted);
  font-size: 11px;
}

.diary-content {
  display: -webkit-box;
  overflow: hidden;
  flex: 1;
  margin: 16px 0;
  color: var(--mori-text);
  font-size: 13px;
  line-height: 1.8;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
  white-space: pre-wrap;
}

.diary-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  border-top: 1px solid var(--mori-line);
  padding-top: 8px;
}

.diary-meta {
  color: var(--mori-muted);
  font-size: 10.5px;
}

.diary-dialog {
  border: 1px solid var(--mori-line);
  background: var(--mori-panel) !important;
  box-shadow: var(--mori-shadow);
}

.diary-dialog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 26px 0;
}

.diary-dialog-head h2 {
  margin: 9px 0 0;
  color: var(--mori-text);
  font-size: 23px;
  font-weight: 600;
  letter-spacing: -0.035em;
}

.diary-dialog-body {
  padding: 20px 26px 26px !important;
}

.diary-full-content {
  margin: 0;
  color: var(--mori-text);
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
}

.diary-dialog-meta {
  margin: 18px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
}

.generate-dialog {
  background: var(--mori-panel) !important;
}

.generate-hint {
  margin: 8px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
  line-height: 1.6;
}

@media (max-width: 820px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .head-actions {
    width: 100%;
    flex-wrap: wrap;
    padding-bottom: 0;
  }

  .character-filter {
    width: 100%;
  }

  .diary-grid {
    grid-template-columns: 1fr;
  }

  .empty-state {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .empty-state .v-btn {
    margin-left: 0;
  }
}
</style>
