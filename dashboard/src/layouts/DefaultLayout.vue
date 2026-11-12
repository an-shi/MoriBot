<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDisplay } from 'vuetify'
import { useRoute, useRouter } from 'vue-router'

import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import MoriLogo from '@/components/MoriLogo.vue'
import { useThemeMode } from '@/composables/useThemeMode'
import { APP_VERSION } from '@/config'
import { useAuthStore } from '@/stores/auth'
import { useSystemStore } from '@/stores/system'
import { formatDateTime } from '@/utils/format'

type NavItem = {
  labelKey: string
  icon: string
  to?: string
  available: boolean
}

const navItems: NavItem[] = [
  { labelKey: 'nav.home', icon: 'mdi-view-dashboard-outline', to: '/', available: true },
  { labelKey: 'nav.chat', icon: 'mdi-message-text-outline', available: false },
  { labelKey: 'nav.providers', icon: 'mdi-brain', available: false },
  { labelKey: 'nav.platforms', icon: 'mdi-lan-connect', available: false },
  { labelKey: 'nav.plugins', icon: 'mdi-puzzle-outline', available: false },
  { labelKey: 'nav.logs', icon: 'mdi-text-box-outline', available: false },
  { labelKey: 'nav.settings', icon: 'mdi-cog-outline', available: false },
]

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const system = useSystemStore()
const { t, locale } = useI18n()
const { mdAndUp } = useDisplay()
const { isDark, toggle: toggleTheme } = useThemeMode()

const drawer = ref(true)
const loggingOut = ref(false)

watch(
  mdAndUp,
  (desktop) => {
    drawer.value = desktop
  },
  { immediate: true },
)

const displayName = computed(
  () => auth.user?.display_name || auth.user?.username || t('layout.roleAdmin'),
)
const initials = computed(() => displayName.value.charAt(0).toUpperCase())
const roleLabel = computed(() =>
  auth.user?.role === 'admin' ? t('layout.roleAdmin') : auth.user?.role || t('layout.roleMember'),
)
const pageTitle = computed(() => t(String(route.meta.titleKey || 'nav.home')))
const version = computed(() => system.publicInfo?.version || APP_VERSION)
const coreRunning = computed(() => Boolean(system.info?.running))
const platformCountLabel = computed(() => {
  const count = system.info?.platforms ?? 0
  return t('layout.platformCount', { count }, count)
})
const lastLogin = computed(() =>
  formatDateTime(auth.user?.last_login_at, locale.value, t('layout.neverLoggedIn')),
)

onMounted(() => {
  void system.fetchInfo()
  if (!system.publicInfo) {
    void system.fetchPublicInfo()
  }
})

async function handleLogout(): Promise<void> {
  loggingOut.value = true
  try {
    await auth.logout()
    await router.replace({ name: 'login' })
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <v-navigation-drawer
    v-model="drawer"
    :permanent="mdAndUp"
    :temporary="!mdAndUp"
    :width="270"
    class="mori-drawer"
    flat
  >
    <div class="drawer-inner">
      <router-link to="/" class="brand-link" @click="!mdAndUp && (drawer = false)">
        <MoriLogo :size="38" show-text />
      </router-link>

      <p class="nav-label">{{ t('nav.console') }}</p>
      <nav class="nav-list" :aria-label="t('nav.mainNavigation')">
        <template v-for="item in navItems" :key="item.labelKey">
          <router-link
            v-if="item.available"
            :to="item.to!"
            class="nav-item"
            active-class="nav-item--active"
            @click="!mdAndUp && (drawer = false)"
          >
            <v-icon size="19">{{ item.icon }}</v-icon>
            <span>{{ t(item.labelKey) }}</span>
          </router-link>
          <div v-else class="nav-item nav-item--disabled" aria-disabled="true">
            <v-icon size="19">{{ item.icon }}</v-icon>
            <span>{{ t(item.labelKey) }}</span>
            <span class="soon-badge">{{ t('common.soon') }}</span>
          </div>
        </template>
      </nav>

      <div class="drawer-spacer" />

      <div class="runtime-card">
        <div class="runtime-head">
          <span class="runtime-dot" :class="{ 'runtime-dot--live': coreRunning }" />
          <span>{{ t('layout.coreService') }}</span>
          <strong>{{ coreRunning ? t('layout.running') : t('layout.connecting') }}</strong>
        </div>
        <div class="runtime-meta">
          <span>v{{ version }}</span>
          <span>{{ platformCountLabel }}</span>
        </div>
      </div>
    </div>
  </v-navigation-drawer>

  <v-app-bar flat height="72" class="mori-appbar">
    <v-app-bar-nav-icon v-if="!mdAndUp" @click="drawer = true" />
    <div class="appbar-title">
      <span class="appbar-kicker">MORIBOT / {{ pageTitle }}</span>
      <strong>{{ pageTitle }}</strong>
    </div>

    <v-spacer />

    <LanguageSwitcher />

    <v-btn
      icon
      variant="text"
      class="appbar-icon"
      :aria-label="isDark ? t('common.theme.switchToLight') : t('common.theme.switchToDark')"
      @click="toggleTheme"
    >
      <v-icon size="19">{{ isDark ? 'mdi-weather-sunny' : 'mdi-weather-night' }}</v-icon>
      <v-tooltip activator="parent" location="bottom">
        {{ isDark ? t('common.theme.light') : t('common.theme.dark') }}
      </v-tooltip>
    </v-btn>

    <v-divider vertical class="appbar-divider" />

    <v-menu location="bottom end" :offset="10" transition="fade-transition">
      <template #activator="{ props }">
        <v-btn v-bind="props" variant="text" class="user-button">
          <span class="user-avatar">{{ initials }}</span>
          <span class="user-copy">
            <strong>{{ displayName }}</strong>
            <small>{{ roleLabel }}</small>
          </span>
          <v-icon size="16" class="user-chevron">mdi-chevron-down</v-icon>
        </v-btn>
      </template>

      <v-list class="user-menu" density="compact">
        <v-list-item class="user-menu-header">
          <template #prepend>
            <v-icon color="primary">mdi-account-circle-outline</v-icon>
          </template>
          <v-list-item-title>{{ auth.user?.username || 'admin' }}</v-list-item-title>
          <v-list-item-subtitle>
            {{ t('layout.recentLogin', { time: lastLogin }) }}
          </v-list-item-subtitle>
        </v-list-item>
        <v-divider class="my-1" />
        <v-list-item
          :disabled="loggingOut"
          class="logout-item"
          @click="handleLogout"
        >
          <template #prepend>
            <v-icon>mdi-logout-variant</v-icon>
          </template>
          <v-list-item-title>
            {{ loggingOut ? t('layout.loggingOut') : t('layout.logout') }}
          </v-list-item-title>
        </v-list-item>
      </v-list>
    </v-menu>
  </v-app-bar>

  <v-main class="mori-main">
    <router-view />
  </v-main>
</template>

<style scoped lang="scss">
.mori-drawer {
  border-right: 1px solid var(--mori-line) !important;
  background: var(--mori-panel) !important;
}

.drawer-inner {
  display: flex;
  height: 100%;
  flex-direction: column;
  padding: 22px 14px 18px;
}

.brand-link {
  display: inline-flex;
  width: fit-content;
  margin: 2px 10px 32px;
  border-radius: 12px;
}

.nav-label {
  margin: 0 14px 10px;
  color: var(--mori-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.nav-list {
  display: grid;
  gap: 3px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 43px;
  padding: 0 12px;
  border-radius: 12px;
  color: var(--mori-muted);
  font-size: 13.5px;
  font-weight: 500;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.nav-item :deep(.v-icon) {
  color: color-mix(in srgb, var(--mori-muted) 82%, transparent);
  transition: color 0.18s ease;
}

.nav-item:hover {
  background: var(--mori-panel-2);
  color: var(--mori-text);
}

.nav-item:hover :deep(.v-icon) {
  color: var(--mori-mint);
}

.nav-item--active {
  background: var(--mori-mint-soft);
  color: var(--mori-text);
  font-weight: 600;
}

.nav-item--active :deep(.v-icon) {
  color: var(--mori-mint);
}

.nav-item--disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.nav-item--disabled:hover {
  background: transparent;
  color: var(--mori-muted);
}

.nav-item--disabled:hover :deep(.v-icon) {
  color: color-mix(in srgb, var(--mori-muted) 82%, transparent);
}

.soon-badge {
  margin-left: auto;
  padding: 2px 6px;
  border: 1px solid var(--mori-line);
  border-radius: 999px;
  color: var(--mori-muted);
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.drawer-spacer {
  flex: 1;
}

.runtime-card {
  padding: 14px;
  border: 1px solid var(--mori-line);
  border-radius: 14px;
  background:
    radial-gradient(circle at 100% 0, var(--mori-mint-soft), transparent 60%),
    var(--mori-panel-2);
}

.runtime-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--mori-muted);
  font-size: 11.5px;
}

.runtime-head strong {
  margin-left: auto;
  color: var(--mori-text);
  font-size: 11px;
  font-weight: 600;
}

.runtime-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--mori-muted);
}

.runtime-dot--live {
  background: var(--mori-mint);
  animation: mori-pulse 2.4s ease-in-out infinite;
}

.runtime-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--mori-line);
  color: var(--mori-muted);
  font-size: 10.5px;
}

.mori-appbar {
  border-bottom: 1px solid var(--mori-line);
  background: color-mix(in srgb, var(--mori-panel) 88%, transparent) !important;
  backdrop-filter: blur(18px);
}

.appbar-title {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-left: 4px;
}

.appbar-kicker {
  color: var(--mori-mint);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.appbar-title strong {
  color: var(--mori-text);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.appbar-icon {
  color: var(--mori-muted) !important;
}

.appbar-divider {
  height: 22px !important;
  margin: 0 10px;
  border-color: var(--mori-line) !important;
}

.user-button {
  height: 48px !important;
  padding: 4px 8px !important;
  border-radius: 12px !important;
  text-transform: none !important;
  color: var(--mori-text) !important;
}

.user-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  flex: none;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--mori-mint) 45%, transparent);
  border-radius: 11px;
  background:
    linear-gradient(145deg, color-mix(in srgb, var(--mori-mint) 26%, transparent), transparent),
    var(--mori-panel-2);
  color: var(--mori-mint);
  font-size: 13px;
  font-weight: 700;
}

.user-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  margin: 0 8px 0 10px;
  gap: 1px;
}

.user-copy strong {
  color: var(--mori-text);
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.2;
}

.user-copy small {
  color: var(--mori-muted);
  font-size: 10px;
  line-height: 1.2;
}

.user-chevron {
  color: var(--mori-muted);
}

.user-menu {
  min-width: 248px;
  border: 1px solid var(--mori-line);
  background: var(--mori-panel) !important;
  box-shadow: var(--mori-shadow);
}

.user-menu-header {
  padding-top: 8px;
  padding-bottom: 8px;
}

.user-menu-header :deep(.v-list-item-title) {
  color: var(--mori-text);
  font-size: 13px;
  font-weight: 600;
}

.user-menu-header :deep(.v-list-item-subtitle) {
  color: var(--mori-muted);
  font-size: 10.5px;
}

.logout-item :deep(.v-list-item-title) {
  font-size: 13px;
}

.mori-main {
  min-height: calc(100vh - 72px);
  background: var(--mori-bg);
}

@media (max-width: 600px) {
  .appbar-title strong {
    font-size: 14px;
  }

  .appbar-kicker {
    display: none;
  }

  .user-copy,
  .user-chevron {
    display: none;
  }

  .user-button {
    min-width: 0 !important;
    padding: 4px !important;
  }

  .appbar-divider {
    margin: 0 4px;
  }
}
</style>
