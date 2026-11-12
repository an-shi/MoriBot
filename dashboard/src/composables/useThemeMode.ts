import { computed, readonly, ref } from 'vue'
import { useTheme } from 'vuetify'

const STORAGE_KEY = 'moribot.theme'

export type ThemeMode = 'dark' | 'light'

function readInitialMode(): ThemeMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

// Shared across every component using the composable.
const mode = ref<ThemeMode>(readInitialMode())

export function useThemeMode() {
  const theme = useTheme()

  function apply(): void {
    const themeName = mode.value === 'dark' ? 'moribot-dark' : 'moribot-light'
    if (theme.global.name.value !== themeName) {
      theme.global.name.value = themeName
    }
    document.documentElement.classList.toggle('moribot-dark', mode.value === 'dark')
    document.documentElement.style.colorScheme = mode.value
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', mode.value === 'dark' ? '#08110d' : '#f3f7f4')
  }

  function setMode(next: ThemeMode): void {
    mode.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Theme persistence is a convenience, never a hard requirement.
    }
    apply()
  }

  function toggle(): void {
    setMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  apply()

  return {
    mode: readonly(mode),
    isDark: computed(() => mode.value === 'dark'),
    toggle,
    setMode,
  }
}
