<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/api/http'
import { providersApi } from '@/api/providers'
import ProviderDialog from '@/components/ProviderDialog.vue'
import type { ModelProvider, ProviderCategory } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const { t, locale } = useI18n()

const providers = ref<ModelProvider[]>([])
const loading = ref(false)
const errorMessage = ref('')
const dialogOpen = ref(false)
const dialogCategory = ref<ProviderCategory>('chat')
const editingProvider = ref<ModelProvider | null>(null)
const testingId = ref<number | null>(null)
const defaultingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const snackbar = ref({ show: false, message: '', color: 'success' })

const categoryOrder: ProviderCategory[] = ['chat', 'speech', 'image']
const categoryIcons: Record<ProviderCategory, string> = {
  chat: 'mdi-robot-outline',
  speech: 'mdi-volume-high',
  image: 'mdi-image-outline',
}

const groups = computed(() =>
  categoryOrder.map((category) => ({
    category,
    icon: categoryIcons[category],
    items: providers.value.filter((provider) => provider.category === category),
  })),
)

async function loadProviders(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    providers.value = await providersApi.list()
  } catch (error) {
    errorMessage.value = `${t('providers.loadFailed')}: ${extractErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

function openCreate(category: ProviderCategory): void {
  editingProvider.value = null
  dialogCategory.value = category
  dialogOpen.value = true
}

function openEdit(provider: ModelProvider): void {
  editingProvider.value = provider
  dialogCategory.value = provider.category
  dialogOpen.value = true
}

function showSnackbar(message: string, color: 'success' | 'error'): void {
  snackbar.value = { show: true, message, color }
}

async function handleSaved(): Promise<void> {
  const wasEditing = editingProvider.value !== null
  editingProvider.value = null
  await loadProviders()
  showSnackbar(wasEditing ? t('providers.updated') : t('providers.created'), 'success')
}

async function testProvider(provider: ModelProvider): Promise<void> {
  testingId.value = provider.id
  try {
    const result = await providersApi.test(provider.id)
    showSnackbar(result.message, result.ok ? 'success' : 'error')
    await loadProviders()
  } catch (error) {
    showSnackbar(`${t('providers.testRequestFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    testingId.value = null
  }
}

async function setDefault(provider: ModelProvider): Promise<void> {
  defaultingId.value = provider.id
  try {
    await providersApi.setDefault(provider.id)
    await loadProviders()
    showSnackbar(t('providers.defaultSet'), 'success')
  } catch (error) {
    showSnackbar(`${t('providers.saveFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    defaultingId.value = null
  }
}

async function removeProvider(provider: ModelProvider): Promise<void> {
  if (!window.confirm(t('providers.deleteConfirm', { name: provider.name }))) {
    return
  }
  deletingId.value = provider.id
  try {
    await providersApi.remove(provider.id)
    await loadProviders()
    showSnackbar(t('providers.deleted'), 'success')
  } catch (error) {
    showSnackbar(`${t('providers.deleteFailed')}: ${extractErrorMessage(error)}`, 'error')
  } finally {
    deletingId.value = null
  }
}

function testState(provider: ModelProvider): string {
  if (provider.last_test_ok === null) {
    return t('providers.neverTested')
  }
  return provider.last_test_ok ? t('providers.testOk') : t('providers.testFailed')
}

onMounted(() => {
  void loadProviders()
})
</script>

<template>
  <div class="providers-page">
    <header class="page-head">
      <div>
        <p class="mori-eyebrow">{{ t('providers.eyebrow') }}</p>
        <h1>{{ t('providers.title') }}</h1>
        <p class="page-subtitle">{{ t('providers.subtitle') }}</p>
      </div>
      <span class="count-chip">{{ t('providers.configuredCount', { count: providers.length }) }}</span>
    </header>

    <v-alert
      v-if="errorMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="page-alert"
      closable
      @click:close="errorMessage = ''"
    >
      {{ errorMessage }}
    </v-alert>

    <section v-for="group in groups" :key="group.category" class="provider-section">
      <div class="section-head">
        <div class="section-title">
          <span class="section-icon"><v-icon size="19">{{ group.icon }}</v-icon></span>
          <div>
            <h2>{{ t(`providers.categories.${group.category}.title`) }}</h2>
            <p>{{ t(`providers.categories.${group.category}.desc`) }}</p>
          </div>
          <v-chip size="x-small" variant="tonal">{{ group.items.length }}</v-chip>
        </div>
        <v-btn
          variant="tonal"
          color="primary"
          size="small"
          prepend-icon="mdi-plus"
          @click="openCreate(group.category)"
        >
          {{ t('providers.add') }}
        </v-btn>
      </div>

      <div v-if="group.items.length" class="provider-grid">
        <article
          v-for="provider in group.items"
          :key="provider.id"
          class="provider-card"
          :class="{ 'provider-card--disabled': !provider.enabled }"
        >
          <header class="card-head">
            <div class="card-title">
              <h3>{{ provider.name }}</h3>
              <div class="card-badges">
                <v-chip v-if="provider.is_default" size="x-small" color="primary" variant="flat">
                  {{ t('providers.default') }}
                </v-chip>
                <v-chip v-if="!provider.enabled" size="x-small" variant="tonal">
                  {{ t('providers.disabled') }}
                </v-chip>
              </div>
            </div>
            <span class="card-type">OpenAI Compatible</span>
          </header>

          <dl class="meta-grid">
            <div>
              <dt>{{ t('providers.card.model') }}</dt>
              <dd>{{ provider.model }}</dd>
            </div>
            <div>
              <dt>{{ t('providers.card.key') }}</dt>
              <dd>{{ provider.api_key_set ? provider.api_key_hint || t('providers.keySet') : t('providers.keyMissing') }}</dd>
            </div>
            <div class="meta-wide">
              <dt>{{ t('providers.card.endpoint') }}</dt>
              <dd class="mono">{{ provider.base_url }}</dd>
            </div>
            <div class="meta-wide">
              <dt>{{ t('providers.card.lastTest') }}</dt>
              <dd>
                {{ testState(provider) }}
                <span v-if="provider.last_tested_at" class="meta-muted">
                  · {{ formatDateTime(provider.last_tested_at, locale, t('providers.neverTested')) }}
                </span>
              </dd>
            </div>
          </dl>

          <p v-if="provider.last_test_message" class="test-message">
            {{ provider.last_test_message }}
          </p>

          <footer class="card-actions">
            <v-btn
              variant="text"
              size="small"
              prepend-icon="mdi-connection"
              :loading="testingId === provider.id"
              @click="testProvider(provider)"
            >
              {{ t('providers.test') }}
            </v-btn>
            <v-btn
              v-if="!provider.is_default"
              variant="text"
              size="small"
              prepend-icon="mdi-star-outline"
              :loading="defaultingId === provider.id"
              @click="setDefault(provider)"
            >
              {{ t('providers.setDefault') }}
            </v-btn>
            <v-spacer />
            <v-btn variant="text" size="small" @click="openEdit(provider)">
              {{ t('providers.edit') }}
            </v-btn>
            <v-btn
              variant="text"
              size="small"
              color="error"
              :loading="deletingId === provider.id"
              @click="removeProvider(provider)"
            >
              {{ t('providers.delete') }}
            </v-btn>
          </footer>
        </article>
      </div>

      <div v-else class="provider-empty">
        <span class="empty-icon"><v-icon size="24">{{ group.icon }}</v-icon></span>
        <div>
          <h3>
            {{
              t('providers.emptyTitle', {
                name: t(`providers.categories.${group.category}.title`),
              })
            }}
          </h3>
          <p>{{ t('providers.emptyDescription') }}</p>
        </div>
        <v-btn
          variant="tonal"
          color="primary"
          size="small"
          prepend-icon="mdi-plus"
          @click="openCreate(group.category)"
        >
          {{ t('providers.add') }}
        </v-btn>
      </div>
    </section>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top" :timeout="3400">
      {{ snackbar.message }}
    </v-snackbar>

    <ProviderDialog
      v-model="dialogOpen"
      :category="dialogCategory"
      :provider="editingProvider"
      @saved="handleSaved"
    />
  </div>
</template>

<style scoped lang="scss">
.providers-page {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 34px clamp(20px, 3.2vw, 44px) 40px;
  animation: mori-rise 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.page-head h1 {
  margin: 10px 0 0;
  color: var(--mori-text);
  font-size: clamp(28px, 3.2vw, 38px);
  font-weight: 600;
  letter-spacing: -0.045em;
}

.page-subtitle {
  max-width: 760px;
  margin: 12px 0 0;
  color: var(--mori-muted);
  font-size: 13.5px;
  line-height: 1.7;
}

.count-chip {
  flex: none;
  margin-bottom: 4px;
  padding: 6px 11px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  color: var(--mori-muted);
  font-size: 10.5px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.page-alert {
  margin-top: 22px;
  border-radius: 12px;
}

.provider-section {
  margin-top: 30px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 14px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.section-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: none;
  place-items: center;
  border: 1px solid var(--mori-line);
  border-radius: 12px;
  background: var(--mori-panel-2);
  color: var(--mori-mint);
}

.section-title h2 {
  margin: 0;
  color: var(--mori-text);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.015em;
}

.section-title p {
  margin: 3px 0 0;
  color: var(--mori-muted);
  font-size: 11.5px;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
  gap: 14px;
}

.provider-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 18px;
  border: 1px solid var(--mori-line);
  border-radius: 18px;
  background:
    radial-gradient(circle at 100% 0, var(--mori-mint-soft), transparent 46%),
    var(--mori-panel);
  transition:
    border-color 0.18s ease,
    transform 0.18s ease;
}

.provider-card:hover {
  border-color: color-mix(in srgb, var(--mori-mint) 32%, transparent);
  transform: translateY(-1px);
}

.provider-card--disabled {
  opacity: 0.62;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.card-title h3 {
  overflow: hidden;
  margin: 0;
  color: var(--mori-text);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-badges {
  display: flex;
  gap: 5px;
}

.card-type {
  flex: none;
  color: var(--mori-muted);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 20px;
  margin: 18px 0 0;
}

.meta-grid div {
  min-width: 0;
}

.meta-wide {
  grid-column: span 2;
}

.meta-grid dt {
  margin: 0 0 4px;
  color: var(--mori-muted);
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.meta-grid dd {
  overflow: hidden;
  margin: 0;
  color: var(--mori-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 10.5px !important;
}

.meta-muted {
  color: var(--mori-muted);
}

.test-message {
  margin: 12px 0 0;
  padding: 8px 10px;
  border-radius: 9px;
  background: var(--mori-panel-2);
  color: var(--mori-muted);
  font-size: 10.5px;
  line-height: 1.5;
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid var(--mori-line);
}

.card-actions :deep(.v-btn) {
  font-size: 10.5px;
  text-transform: none;
}

.provider-empty {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 16px;
  background: var(--mori-panel);
}

.empty-icon {
  display: grid;
  width: 42px;
  height: 42px;
  flex: none;
  place-items: center;
  border-radius: 12px;
  background: var(--mori-mint-soft);
  color: var(--mori-mint);
}

.provider-empty h3 {
  margin: 0;
  color: var(--mori-text);
  font-size: 13px;
  font-weight: 600;
}

.provider-empty p {
  margin: 4px 0 0;
  color: var(--mori-muted);
  font-size: 11px;
}

.provider-empty :deep(.v-btn) {
  margin-left: auto;
}

@media (max-width: 760px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .section-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .provider-empty {
    align-items: flex-start;
    flex-direction: column;
  }

  .provider-empty :deep(.v-btn) {
    margin-left: 0;
  }
}

@media (max-width: 520px) {
  .providers-page {
    padding-top: 24px;
  }

  .meta-grid {
    grid-template-columns: 1fr;
  }

  .meta-wide {
    grid-column: span 1;
  }
}
</style>
