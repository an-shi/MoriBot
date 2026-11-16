<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { memoryApi, type MemoryHealth, type MemoryItem, type MemorySpace } from '@/api/memory'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()

const health = ref<MemoryHealth | null>(null)
const spaces = ref<MemorySpace[]>([])
const selectedSpaceId = ref('')
const memories = ref<MemoryItem[]>([])
const search = ref('')
const loading = ref(true)
const loadingMemories = ref(false)
const removingId = ref('')
const errorMessage = ref('')
const snackbar = ref({ show: false, message: '', color: 'success' })

const selectedSpace = computed(
  () => spaces.value.find((space) => space.id === selectedSpaceId.value) ?? null,
)
const totalMemories = computed(() =>
  spaces.value.reduce((total, space) => total + (space.memory_count ?? 0), 0),
)
const engineLabel = computed(() => {
  if (!health.value) {
    return t('memory.unavailable')
  }
  return health.value.version || t('memory.running')
})

const categoryLabels: Record<string, string> = {
  identity: 'memory.categoryIdentity',
  fact: 'memory.categoryFact',
  preference: 'memory.categoryPreference',
  relationship: 'memory.categoryRelationship',
  event: 'memory.categoryEvent',
  goal: 'memory.categoryGoal',
  plan: 'memory.categoryPlan',
  skill: 'memory.categorySkill',
  opinion: 'memory.categoryOpinion',
  habit: 'memory.categoryHabit',
  context: 'memory.categoryContext',
  summary: 'memory.categorySummary',
  other: 'memory.categoryOther',
}

const sourceLabels: Record<string, string> = {
  user_explicit: 'memory.sourceUserExplicit',
  ai_inference: 'memory.sourceAiInference',
  behavior_observation: 'memory.sourceBehaviorObservation',
  model_summary: 'memory.sourceModelSummary',
}

function categoryLabel(value: string): string {
  const key = categoryLabels[value]
  return key ? t(key) : value
}

function sourceLabel(value: string): string {
  const key = sourceLabels[value]
  return key ? t(key) : value
}

function spaceInitial(space: MemorySpace): string {
  const label = (space.name || space.key || '?').split('·').pop()?.trim() || '?'
  return label.charAt(0).toUpperCase()
}

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

async function loadSpaces(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const [engineHealth, characterSpaces] = await Promise.all([
      memoryApi.health().catch(() => null),
      memoryApi.spaces('character'),
    ])
    health.value = engineHealth
    spaces.value = characterSpaces
    if (!spaces.value.some((space) => space.id === selectedSpaceId.value)) {
      selectedSpaceId.value = spaces.value[0]?.id ?? ''
    }
    await loadMemories()
  } catch (error) {
    errorMessage.value = `${t('memory.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function loadMemories(): Promise<void> {
  if (!selectedSpaceId.value) {
    memories.value = []
    return
  }
  loadingMemories.value = true
  try {
    const page = await memoryApi.memories({
      space_id: selectedSpaceId.value,
      q: search.value.trim() || undefined,
      per_page: 200,
    })
    memories.value = page.items
  } catch (error) {
    errorMessage.value = `${t('memory.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loadingMemories.value = false
  }
}

function selectSpace(space: MemorySpace): void {
  if (selectedSpaceId.value === space.id) {
    return
  }
  selectedSpaceId.value = space.id
  search.value = ''
  void loadMemories()
}

async function removeMemory(memory: MemoryItem): Promise<void> {
  if (!window.confirm(t('memory.deleteConfirm'))) {
    return
  }
  removingId.value = memory.id
  try {
    await memoryApi.remove(memory.id)
    memories.value = memories.value.filter((item) => item.id !== memory.id)
    const space = spaces.value.find((item) => item.id === memory.space_id)
    if (space && typeof space.memory_count === 'number') {
      space.memory_count = Math.max(0, space.memory_count - 1)
    }
    showSnackbar(t('memory.deleted'), 'success')
  } catch (error) {
    showSnackbar(`${t('memory.deleteFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    removingId.value = ''
  }
}

onMounted(() => {
  void loadSpaces()
})
</script>

<template>
  <div class="memory-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('memory.eyebrow') }}</p>
        <h1>{{ t('memory.title') }}</h1>
        <p class="page-subtitle">{{ t('memory.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <v-chip
          size="small"
          variant="tonal"
          :color="health ? 'success' : 'warning'"
          prepend-icon="mdi-memory"
        >
          {{ t('memory.engine') }} · {{ engineLabel }}
        </v-chip>
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="loadSpaces">
          {{ t('memory.refresh') }}
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

    <div class="summary-row">
      <div class="summary-card">
        <span class="summary-icon"><v-icon size="20">mdi-account-box-multiple-outline</v-icon></span>
        <div>
          <strong>{{ spaces.length }}</strong>
          <span>{{ t('memory.characterSpaces') }}</span>
        </div>
      </div>
      <div class="summary-card">
        <span class="summary-icon"><v-icon size="20">mdi-database-outline</v-icon></span>
        <div>
          <strong>{{ totalMemories }}</strong>
          <span>{{ t('memory.totalMemories') }}</span>
        </div>
      </div>
      <div class="summary-card">
        <span class="summary-icon"><v-icon size="20">mdi-shield-lock-outline</v-icon></span>
        <div>
          <strong>{{ t('memory.isolated') }}</strong>
          <span>{{ t('memory.isolatedHint') }}</span>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <v-progress-circular indeterminate size="24" width="2" />
      {{ t('memory.loading') }}
    </div>

    <div v-else-if="spaces.length === 0" class="empty-state">
      <span class="empty-icon"><v-icon size="26">mdi-memory</v-icon></span>
      <div>
        <h3>{{ t('memory.emptySpacesTitle') }}</h3>
        <p>{{ t('memory.emptySpacesDescription') }}</p>
      </div>
    </div>

    <div v-else class="memory-layout">
      <aside class="space-list">
        <button
          v-for="space in spaces"
          :key="space.id"
          type="button"
          class="space-item"
          :class="{ active: space.id === selectedSpaceId }"
          @click="selectSpace(space)"
        >
          <span class="space-avatar">{{ spaceInitial(space) }}</span>
          <span class="space-meta">
            <strong>{{ space.name || space.key }}</strong>
            <small>{{ t('memory.memoryCount', { count: space.memory_count ?? 0 }) }}</small>
          </span>
          <v-icon size="16">mdi-chevron-right</v-icon>
        </button>
      </aside>

      <section class="memory-panel">
        <div class="panel-head">
          <div>
            <h2>{{ selectedSpace?.name || t('memory.selectSpace') }}</h2>
            <p>
              {{
                t('memory.memoryCount', {
                  count: selectedSpace?.memory_count ?? memories.length,
                })
              }}
            </p>
          </div>
          <div class="search-box">
            <v-text-field
              v-model="search"
              density="compact"
              variant="outlined"
              hide-details
              prepend-inner-icon="mdi-magnify"
              :placeholder="t('memory.searchPlaceholder')"
              @keyup.enter="loadMemories"
            />
            <v-btn variant="tonal" :loading="loadingMemories" @click="loadMemories">
              {{ t('memory.search') }}
            </v-btn>
          </div>
        </div>

        <div v-if="loadingMemories" class="loading-state compact">
          <v-progress-circular indeterminate size="20" width="2" />
          {{ t('memory.loading') }}
        </div>

        <div v-else-if="memories.length === 0" class="empty-memories">
          <v-icon size="28">mdi-text-box-search-outline</v-icon>
          <h3>{{ t('memory.emptyTitle') }}</h3>
          <p>{{ t('memory.emptyDescription') }}</p>
        </div>

        <div v-else class="memory-grid">
          <article v-for="memory in memories" :key="memory.id" class="memory-card">
            <header>
              <div class="memory-heading">
                <strong>{{ memory.title || memory.content.slice(0, 40) }}</strong>
                <div class="memory-tags">
                  <v-chip size="x-small" variant="tonal" color="primary">
                    {{ categoryLabel(memory.category) }}
                  </v-chip>
                  <v-chip size="x-small" variant="text">
                    {{ sourceLabel(memory.source_kind) }}
                  </v-chip>
                  <v-chip v-if="memory.status !== 'active'" size="x-small" variant="tonal" color="warning">
                    {{ memory.status }}
                  </v-chip>
                </div>
              </div>
              <v-btn
                icon
                variant="text"
                size="small"
                color="error"
                :loading="removingId === memory.id"
                :aria-label="t('memory.delete')"
                @click="removeMemory(memory)"
              >
                <v-icon size="17">mdi-trash-can-outline</v-icon>
              </v-btn>
            </header>

            <p class="memory-content">{{ memory.content }}</p>

            <footer>
              <span class="importance">
                <v-icon size="14">mdi-star-outline</v-icon>
                {{ t('memory.importance') }}
                {{ Math.round(memory.importance * 100) }}%
              </span>
              <span v-if="memory.reinforcement_count > 1" class="meta">
                {{ t('memory.reinforced', { count: memory.reinforcement_count }) }}
              </span>
              <v-spacer />
              <span class="meta">{{ formatDateTime(memory.updated_at, locale, '') }}</span>
            </footer>
          </article>
        </div>
      </section>
    </div>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3400">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<style scoped lang="scss">
.memory-page {
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
  gap: 8px;
  padding-bottom: 4px;
}

.page-alert {
  margin-top: 20px;
  border-radius: 12px;
}

.summary-row {
  display: grid;
  margin-top: 22px;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 17px;
  border: 1px solid var(--mori-line);
  border-radius: 16px;
  background: var(--mori-panel);
}

.summary-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: none;
  place-items: center;
  border-radius: 12px;
  background: var(--mori-panel-2);
  color: var(--mori-mint);
}

.summary-card div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.summary-card strong {
  color: var(--mori-text);
  font-size: 15px;
  font-weight: 600;
}

.summary-card span:last-child {
  color: var(--mori-muted);
  font-size: 11px;
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 34px;
  color: var(--mori-muted);
  font-size: 12px;
}

.loading-state.compact {
  margin-top: 18px;
}

.empty-state {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 24px;
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
  line-height: 1.6;
}

.memory-layout {
  display: grid;
  margin-top: 20px;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
}

.space-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  align-self: start;
  padding: 8px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
}

.space-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease;
}

.space-item:hover {
  background: var(--mori-panel-2);
}

.space-item.active {
  border-color: var(--mori-line-strong);
  background: var(--mori-panel-2);
}

.space-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: var(--mori-mint-soft);
  color: var(--mori-mint);
  font-size: 13px;
  font-weight: 700;
}

.space-meta {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.space-meta strong {
  overflow: hidden;
  color: var(--mori-text);
  font-size: 12.5px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-meta small {
  color: var(--mori-muted);
  font-size: 10.5px;
}

.memory-panel {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background: var(--mori-panel);
}

.panel-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}

.panel-head h2 {
  margin: 0;
  color: var(--mori-text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.03em;
}

.panel-head p {
  margin: 5px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
}

.search-box {
  display: flex;
  width: min(420px, 100%);
  align-items: center;
  gap: 8px;
}

.empty-memories {
  display: flex;
  min-height: 220px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: var(--mori-muted);
  text-align: center;
}

.empty-memories h3 {
  margin: 6px 0 0;
  color: var(--mori-text);
  font-size: 14px;
  font-weight: 600;
}

.empty-memories p {
  margin: 0;
  font-size: 12px;
}

.memory-grid {
  display: grid;
  margin-top: 18px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.memory-card {
  display: flex;
  min-height: 190px;
  flex-direction: column;
  padding: 15px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background: var(--mori-panel-2);
}

.memory-card header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.memory-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 7px;
}

.memory-heading strong {
  color: var(--mori-text);
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.5;
}

.memory-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.memory-content {
  flex: 1;
  margin: 12px 0;
  color: var(--mori-text);
  font-size: 12.5px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-card footer {
  display: flex;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--mori-line);
  padding-top: 9px;
}

.importance,
.meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--mori-muted);
  font-size: 10px;
}

@media (max-width: 900px) {
  .memory-layout {
    grid-template-columns: 1fr;
  }

  .space-list {
    max-height: 220px;
    overflow-y: auto;
  }

  .page-head,
  .panel-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .head-actions {
    width: 100%;
    flex-wrap: wrap;
    padding-bottom: 0;
  }

  .search-box {
    width: 100%;
  }
}
</style>
