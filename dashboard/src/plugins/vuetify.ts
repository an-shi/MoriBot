import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
const moribotDark = {
  dark: true,
  colors: {
    background: '#07100c',
    surface: '#0c1712',
    'surface-variant': '#13231c',
    primary: '#7be3b3',
    'on-primary': '#07100c',
    secondary: '#57b997',
    accent: '#d8b26e',
    error: '#ff7b72',
    info: '#6fb8ff',
    success: '#7be3b3',
    warning: '#e6c27a',
    'on-surface': '#e8f2ed',
    'on-background': '#e8f2ed',
  },
}

const moribotLight = {
  dark: false,
  colors: {
    background: '#f3f7f4',
    surface: '#ffffff',
    'surface-variant': '#edf4ef',
    primary: '#1f7a58',
    'on-primary': '#ffffff',
    secondary: '#3d8a6b',
    accent: '#9a6d25',
    error: '#c43d3d',
    info: '#256aa8',
    success: '#1f7a58',
    warning: '#9a6d25',
    'on-surface': '#12231b',
    'on-background': '#12231b',
  },
}

export default createVuetify({
  locale: {
    locale: 'zhHans',
    fallback: 'en',
  },
  theme: {
    defaultTheme: 'moribot-dark',
    themes: {
      'moribot-dark': moribotDark,
      'moribot-light': moribotLight,
    },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  display: {
    mobileBreakpoint: 'md',
  },
  defaults: {
    VBtn: {
      rounded: 'lg',
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VCard: {
      rounded: 'xl',
    },
    VMenu: {
      rounded: 'lg',
    },
  },
})
