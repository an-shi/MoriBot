import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import '@/styles/main.scss'

import App from './App.vue'
import { i18n } from './i18n'
import router from './router'
import vuetify from './plugins/vuetify'

const app = createApp(App)

app.use(createPinia())
app.use(i18n)
app.use(router)
app.use(vuetify)
app.mount('#app')
