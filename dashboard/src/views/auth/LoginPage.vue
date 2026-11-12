<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { extractErrorMessage } from '@/api/http'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import MoriLogo from '@/components/MoriLogo.vue'
import { useThemeMode } from '@/composables/useThemeMode'
import { APP_NAME, APP_VERSION } from '@/config'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'

const username = ref('')
const password = ref('')
const remember = ref(true)
const showPassword = ref(false)
const errorMessage = ref('')
const submitting = ref(false)

const auth = useAuthStore()
const system = useSystemStore()
const router = useRouter()
const route = useRoute()
const { isDark, toggle: toggleTheme } = useThemeMode()
const { t } = useI18n()

const brandName = computed(() => system.publicInfo?.name || APP_NAME)
const brandDescription = computed(() => t('login.description'))
const version = computed(() => system.publicInfo?.version || APP_VERSION)

onMounted(() => {
  void system.fetchPublicInfo()
})

async function submit(): Promise<void> {
  const normalizedUsername = username.value.trim()
  if (!normalizedUsername || !password.value) {
    errorMessage.value = t('login.requiredFields')
    return
  }

  submitting.value = true
  errorMessage.value = ''

  try {
    await auth.login(normalizedUsername, password.value, remember.value)
    const redirect = route.query.redirect
    const target =
      typeof redirect === 'string' &&
      redirect.startsWith('/') &&
      !redirect.startsWith('//')
        ? redirect
        : '/'
    await router.replace(target)
  } catch (error) {
    errorMessage.value = extractErrorMessage(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-aurora" aria-hidden="true">
      <span class="orb orb-a" />
      <span class="orb orb-b" />
      <span class="orb orb-c" />
    </div>

    <div class="login-shell">
      <section class="brand-panel">
        <div class="brand-grid" aria-hidden="true" />
        <div class="brand-orbit orbit-a" aria-hidden="true" />
        <div class="brand-orbit orbit-b" aria-hidden="true" />
        <svg class="brand-art" viewBox="0 0 420 420" fill="none" aria-hidden="true">
          <path
            d="M352 64C258 78 190 133 166 222c-12 45-38 78-80 96 96 10 189-17 247-80 42-46 52-105 19-174Z"
            stroke="currentColor"
            stroke-width="1.2"
          />
          <path
            d="M338 86C286 151 224 203 122 285"
            stroke="currentColor"
            stroke-width="1.2"
            stroke-linecap="round"
          />
          <path
            d="M244 190c32 2 58-4 82-18M206 238c-2 26-10 46-24 62"
            stroke="currentColor"
            stroke-width="1.2"
            stroke-linecap="round"
          />
        </svg>

        <header class="brand-top">
          <MoriLogo :size="42" show-text />
          <span class="brand-version">v{{ version }}</span>
        </header>

        <div class="brand-copy">
          <p class="brand-kicker">{{ t('login.kicker') }}</p>
          <h1>
            {{ t('login.titleLine1') }}<br />
            <span>{{ t('login.titleLine2') }}</span>
          </h1>
          <p class="brand-description">{{ brandDescription }}</p>
        </div>

        <ul class="brand-points">
          <li>
            <span class="point-icon"><v-icon size="18">mdi-cube-outline</v-icon></span>
            <span class="point-copy">
              <strong>{{ t('login.pointModular.title') }}</strong>
              <small>{{ t('login.pointModular.desc') }}</small>
            </span>
          </li>
          <li>
            <span class="point-icon"><v-icon size="18">mdi-connection</v-icon></span>
            <span class="point-copy">
              <strong>{{ t('login.pointPlatforms.title') }}</strong>
              <small>{{ t('login.pointPlatforms.desc') }}</small>
            </span>
          </li>
          <li>
            <span class="point-icon"><v-icon size="18">mdi-puzzle-outline</v-icon></span>
            <span class="point-copy">
              <strong>{{ t('login.pointPlugins.title') }}</strong>
              <small>{{ t('login.pointPlugins.desc') }}</small>
            </span>
          </li>
        </ul>

        <footer class="brand-footer">
          <span>{{ t('login.footer', { name: brandName, year: new Date().getFullYear() }) }}</span>
          <span class="brand-status"><i /> {{ t('login.coreService') }}</span>
        </footer>
      </section>

      <section class="form-panel">
        <div class="form-toolbar">
          <span class="toolbar-caption">{{ t('login.secureAccess') }}</span>
          <div class="toolbar-actions">
            <LanguageSwitcher />
            <v-btn
              icon
              variant="text"
              size="small"
              class="theme-button"
              :aria-label="isDark ? t('common.theme.switchToLight') : t('common.theme.switchToDark')"
              @click="toggleTheme"
            >
              <v-icon size="18">
                {{ isDark ? 'mdi-weather-sunny' : 'mdi-weather-night' }}
              </v-icon>
              <v-tooltip activator="parent" location="bottom">
                {{ isDark ? t('common.theme.light') : t('common.theme.dark') }}
              </v-tooltip>
            </v-btn>
          </div>
        </div>

        <div class="form-wrap">
          <div class="form-brand">
            <MoriLogo :size="46" />
            <div class="form-brand-copy">
              <strong>{{ brandName }}</strong>
              <span>AI Assistant Control Plane</span>
            </div>
          </div>

          <p class="form-eyebrow">{{ t('login.welcome') }}</p>
          <h2>{{ t('login.heading') }}</h2>
          <p class="form-subtitle">{{ t('login.subtitle') }}</p>

          <v-form class="login-form" @submit.prevent="submit">
            <div class="field-group">
              <label for="login-username">{{ t('login.username') }}</label>
              <v-text-field
                id="login-username"
                v-model="username"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                autocomplete="username"
                :placeholder="t('login.usernamePlaceholder')"
                prepend-inner-icon="mdi-account-outline"
                :disabled="submitting"
              />
            </div>

            <div class="field-group">
              <label for="login-password">{{ t('login.password') }}</label>
              <v-text-field
                id="login-password"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                variant="outlined"
                density="comfortable"
                hide-details="auto"
                autocomplete="current-password"
                :placeholder="t('login.passwordPlaceholder')"
                prepend-inner-icon="mdi-lock-outline"
                :append-inner-icon="
                  showPassword ? 'mdi-eye-off-outline' : 'mdi-eye-outline'
                "
                :disabled="submitting"
                @click:append-inner="showPassword = !showPassword"
              />
            </div>

            <div class="form-options">
              <v-checkbox
                v-model="remember"
                :label="t('login.remember')"
                color="primary"
                density="compact"
                hide-details
                :disabled="submitting"
              />
              <span class="options-hint">{{ t('login.tokenHint') }}</span>
            </div>

            <v-alert
              v-if="errorMessage"
              :model-value="Boolean(errorMessage)"
              type="error"
              variant="tonal"
              density="compact"
              class="login-alert"
              closable
              @click:close="errorMessage = ''"
            >
              {{ errorMessage }}
            </v-alert>

            <v-btn
              class="submit-button"
              type="submit"
              color="primary"
              size="large"
              block
              :loading="submitting"
              append-icon="mdi-arrow-right"
            >
              {{ t('login.submit') }}
            </v-btn>
          </v-form>

          <div class="first-run-hint">
            <v-icon size="16">mdi-key-outline</v-icon>
            <span>
              {{ t('login.firstRunPrefix') }}<code>{{ t('login.firstRunFile') }}</code>{{ t('login.firstRunSuffix') }}
            </span>
          </div>
        </div>

        <footer class="form-footer">
          <span>{{ t('login.footerProduct') }}</span>
          <span>v{{ version }}</span>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
.login-page {
  position: relative;
  display: grid;
  min-height: 100vh;
  place-items: center;
  overflow: hidden;
  padding: 28px;
  background:
    radial-gradient(circle at 50% 20%, var(--mori-glow), transparent 46%),
    var(--mori-bg);
}

.login-aurora {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(90px);
  opacity: 0.55;
  animation: mori-float 16s ease-in-out infinite;
}

.orb-a {
  top: -14%;
  left: 18%;
  width: 520px;
  height: 520px;
  background: rgba(50, 170, 124, 0.28);
}

.orb-b {
  right: -8%;
  bottom: -18%;
  width: 620px;
  height: 620px;
  background: rgba(46, 122, 96, 0.24);
  animation-delay: -6s;
}

.orb-c {
  top: 36%;
  left: 40%;
  width: 340px;
  height: 340px;
  background: rgba(123, 227, 179, 0.12);
  animation-delay: -11s;
}

.login-shell {
  position: relative;
  z-index: 1;
  display: grid;
  width: min(1180px, 100%);
  min-height: min(780px, calc(100vh - 56px));
  grid-template-columns: 1.05fr 0.95fr;
  overflow: hidden;
  border: 1px solid var(--mori-line);
  border-radius: 32px;
  background: var(--mori-panel);
  box-shadow: var(--mori-shadow);
  animation: mori-rise 0.65s cubic-bezier(0.22, 1, 0.36, 1);
}

.brand-panel {
  --brand-text: #eafaf2;
  --brand-muted: rgba(226, 245, 236, 0.62);
  --brand-line: rgba(190, 240, 218, 0.14);
  --mori-logo-bg: rgba(255, 255, 255, 0.05);
  --mori-logo-border: rgba(205, 255, 231, 0.22);
  --mori-logo-leaf: #8ff0c4;
  --mori-logo-vein: #0a1d15;

  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 44px 48px;
  color: var(--brand-text);
  background:
    radial-gradient(circle at 84% 14%, rgba(123, 227, 179, 0.22), transparent 38%),
    radial-gradient(circle at 12% 88%, rgba(74, 192, 149, 0.16), transparent 42%),
    linear-gradient(148deg, #0c2118 0%, #08150f 54%, #060e0a 100%);
}

.brand-panel::after {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(
    to right,
    rgba(255, 255, 255, 0.035) 1px,
    transparent 1px
  );
  background-size: 74px 100%;
  content: '';
  mask-image: linear-gradient(to bottom, transparent, #000 30%, #000 80%, transparent);
  pointer-events: none;
}

.brand-grid {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(to right, rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 64px 64px;
  mask-image: radial-gradient(circle at 70% 30%, #000, transparent 72%);
  pointer-events: none;
}

.brand-top {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-top :deep(.mori-logo__text) {
  color: var(--brand-text);
}

.brand-version {
  padding: 5px 10px;
  border: 1px solid var(--brand-line);
  border-radius: 999px;
  color: var(--brand-muted);
  font-size: 11px;
  letter-spacing: 0.12em;
}

.brand-copy {
  position: relative;
  z-index: 1;
  margin-top: clamp(44px, 8vh, 92px);
  max-width: 480px;
}

.brand-kicker {
  margin: 0 0 20px;
  color: #8ff0c4;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.24em;
}

.brand-copy h1 {
  margin: 0;
  font-size: clamp(46px, 5vw, 68px);
  font-weight: 600;
  letter-spacing: -0.055em;
  line-height: 1.04;
}

.brand-copy h1 span {
  color: #8ff0c4;
}

.brand-description {
  max-width: 420px;
  margin: 24px 0 0;
  color: var(--brand-muted);
  font-size: 14.5px;
  line-height: 1.85;
}

.brand-points {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 12px;
  margin: clamp(28px, 5vh, 52px) 0 0;
  padding: 0;
  list-style: none;
}

.brand-points li {
  display: flex;
  align-items: center;
  gap: 14px;
}

.point-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: none;
  place-items: center;
  border: 1px solid var(--brand-line);
  border-radius: 12px;
  color: #8ff0c4;
  background: rgba(255, 255, 255, 0.035);
}

.point-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.point-copy strong {
  font-size: 13.5px;
  font-weight: 600;
}

.point-copy small {
  color: var(--brand-muted);
  font-size: 12px;
}

.brand-footer {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: auto;
  padding-top: 32px;
  color: var(--brand-muted);
  font-size: 11.5px;
  letter-spacing: 0.04em;
}

.brand-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.brand-status i {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #7be3b3;
  animation: mori-pulse 2.4s ease-in-out infinite;
}

.brand-art {
  position: absolute;
  right: -70px;
  bottom: -60px;
  width: 430px;
  color: rgba(143, 240, 196, 0.16);
  pointer-events: none;
}

.brand-orbit {
  position: absolute;
  border: 1px solid rgba(143, 240, 196, 0.09);
  border-radius: 999px;
  pointer-events: none;
}

.orbit-a {
  top: -180px;
  right: -140px;
  width: 460px;
  height: 460px;
}

.orbit-b {
  top: -120px;
  right: -80px;
  width: 340px;
  height: 340px;
}

.form-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 48px 24px;
  background: var(--mori-panel);
}

.form-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toolbar-caption {
  color: var(--mori-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.2em;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.theme-button {
  color: var(--mori-muted) !important;
}

.form-wrap {
  width: min(382px, 100%);
  margin: auto;
  padding: 26px 0;
  animation: mori-rise 0.7s 0.08s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.form-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: clamp(34px, 6vh, 56px);
}

.form-brand-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-brand-copy strong {
  color: var(--mori-text);
  font-size: 19px;
  letter-spacing: -0.02em;
}

.form-brand-copy span {
  color: var(--mori-muted);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.form-eyebrow {
  margin: 0 0 10px;
  color: var(--mori-mint);
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.22em;
}

.form-wrap h2 {
  margin: 0;
  color: var(--mori-text);
  font-size: clamp(34px, 3.6vw, 42px);
  font-weight: 600;
  letter-spacing: -0.045em;
  line-height: 1.1;
}

.form-subtitle {
  margin: 12px 0 30px;
  color: var(--mori-muted);
  font-size: 13.5px;
  line-height: 1.7;
}

.login-form {
  display: grid;
  gap: 2px;
}

.field-group {
  margin-bottom: 16px;
}

.field-group label {
  display: block;
  margin-bottom: 8px;
  color: var(--mori-text);
  font-size: 12.5px;
  font-weight: 600;
}

.login-form :deep(.v-field) {
  border-radius: 14px;
  background: var(--mori-panel-2);
  font-size: 14px;
  transition:
    box-shadow 0.2s ease,
    background 0.2s ease;
}

.login-form :deep(.v-field__outline) {
  --v-field-border-opacity: 0.6;
  color: var(--mori-line-strong);
}

.login-form :deep(.v-field--focused) {
  background: var(--mori-panel);
  box-shadow: 0 0 0 4px var(--mori-mint-soft);
}

.login-form :deep(.v-field--focused .v-field__outline) {
  color: var(--mori-mint);
}

.login-form :deep(.v-field__prepend-inner) {
  padding-right: 10px;
  color: var(--mori-muted);
}

.login-form :deep(.v-field__append-inner) {
  color: var(--mori-muted);
}

.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 2px 0 18px;
}

.form-options :deep(.v-label) {
  color: var(--mori-muted);
  font-size: 12.5px;
  opacity: 1;
}

.form-options :deep(.v-selection-control) {
  min-height: 28px;
}

.options-hint {
  color: var(--mori-muted);
  font-size: 11.5px;
}

.login-alert {
  margin-bottom: 16px;
  border-radius: 12px;
  font-size: 12.5px;
}

.submit-button {
  height: 52px !important;
  border-radius: 14px !important;
  font-size: 14px !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em !important;
  box-shadow: 0 12px 28px var(--mori-glow) !important;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease !important;
}

.submit-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 34px var(--mori-glow) !important;
}

.first-run-hint {
  display: flex;
  gap: 9px;
  margin-top: 22px;
  padding: 13px 15px;
  border: 1px dashed var(--mori-line-strong);
  border-radius: 12px;
  color: var(--mori-muted);
  font-size: 11.5px;
  line-height: 1.65;
}

.first-run-hint :deep(.v-icon) {
  margin-top: 1px;
  flex: none;
  color: var(--mori-mint);
}

.first-run-hint code {
  color: var(--mori-text);
  font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, monospace;
  font-size: 10.5px;
}

.form-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 18px;
  border-top: 1px solid var(--mori-line);
  color: var(--mori-muted);
  font-size: 11px;
  letter-spacing: 0.03em;
}

@media (max-height: 820px) and (min-width: 961px) {
  .brand-panel {
    padding: 34px 44px;
  }

  .brand-copy {
    margin-top: clamp(28px, 4.5vh, 48px);
  }

  .brand-copy h1 {
    font-size: clamp(42px, 4.4vw, 56px);
  }

  .brand-description {
    margin-top: 18px;
  }

  .brand-points {
    margin-top: 24px;
    gap: 8px;
  }

  .brand-footer {
    padding-top: 20px;
  }

  .form-panel {
    padding-top: 22px;
    padding-bottom: 16px;
  }

  .form-brand {
    margin-bottom: 26px;
  }

  .form-wrap {
    padding: 12px 0;
  }

  .form-subtitle {
    margin-bottom: 22px;
  }

  .first-run-hint {
    margin-top: 18px;
  }
}

@media (max-width: 960px) {
  .login-page {
    padding: 0;
  }

  .login-shell {
    min-height: 100vh;
    grid-template-columns: 1fr;
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .brand-panel {
    display: none;
  }

  .form-panel {
    padding: 24px 24px 20px;
  }

  .form-brand {
    margin-bottom: 40px;
  }

  .form-wrap {
    width: min(420px, 100%);
    padding: 32px 0;
  }

  .form-wrap h2 {
    font-size: 32px;
  }
}

@media (max-width: 480px) {
  .form-panel {
    padding: 18px 18px 16px;
  }

  .form-wrap h2 {
    font-size: 29px;
  }

  .form-subtitle {
    margin-bottom: 24px;
  }

  .form-brand {
    margin-bottom: 30px;
  }

  .form-options {
    align-items: flex-start;
    flex-direction: column;
    gap: 0;
  }

  .options-hint {
    display: none;
  }
}
</style>
