<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import MoriLogo from '@/components/MoriLogo.vue'

const router = useRouter()
const { t } = useI18n()

function goHome(): void {
  void router.replace('/')
}

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
  } else {
    goHome()
  }
}
</script>

<template>
  <div class="not-found">
    <div class="not-found__card">
      <MoriLogo :size="52" show-text />
      <p class="mori-eyebrow">{{ t('notFound.kicker') }}</p>
      <h1>{{ t('notFound.title') }}</h1>
      <p>{{ t('notFound.description') }}</p>
      <div class="actions">
        <v-btn color="primary" @click="goHome">{{ t('notFound.home') }}</v-btn>
        <v-btn variant="text" @click="goBack">{{ t('notFound.back') }}</v-btn>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.not-found {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at 50% 20%, var(--mori-glow), transparent 50%),
    var(--mori-bg);
}

.not-found__card {
  display: flex;
  max-width: 460px;
  flex-direction: column;
  align-items: center;
  padding: 48px 36px;
  border: 1px solid var(--mori-line);
  border-radius: 28px;
  background: var(--mori-panel);
  text-align: center;
  box-shadow: var(--mori-shadow);
}

.not-found__card .mori-eyebrow {
  margin-top: 34px;
}

.not-found__card h1 {
  margin: 14px 0 0;
  color: var(--mori-text);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.04em;
}

.not-found__card p:not(.mori-eyebrow) {
  margin: 12px 0 0;
  color: var(--mori-muted);
  font-size: 13px;
  line-height: 1.75;
}

.actions {
  display: flex;
  gap: 10px;
  margin-top: 28px;
}
</style>
