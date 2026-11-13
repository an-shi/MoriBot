import { createRouter, createWebHistory } from 'vue-router'

import { i18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { getToken } from '@/utils/token'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/auth/LoginPage.vue'),
      meta: { titleKey: 'login.pageTitle' },
    },
    {
      path: '/',
      component: () => import('@/layouts/DefaultLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('@/views/HomePage.vue'),
          meta: { titleKey: 'nav.home', requiresAuth: true },
        },
        {
          path: 'providers',
          name: 'providers',
          component: () => import('@/views/ProvidersPage.vue'),
          meta: { titleKey: 'nav.providers', requiresAuth: true },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/SystemSettingsPage.vue'),
          meta: { titleKey: 'nav.settings', requiresAuth: true },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundPage.vue'),
      meta: { titleKey: 'notFound.pageTitle' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const token = getToken()
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth)

  if (to.name === 'login' && token) {
    return { name: 'home' }
  }

  if (requiresAuth && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (token && requiresAuth) {
    const auth = useAuthStore()
    if (!auth.user) {
      const user = await auth.fetchMe()
      if (!user) {
        return { name: 'login', query: { redirect: to.fullPath } }
      }
    }
  }

  return true
})

router.afterEach((to) => {
  const title = to.meta.titleKey ? `${i18n.global.t(to.meta.titleKey)} · MoriBot` : 'MoriBot'
  document.title = title
  // Navigation between pages with different heights can preserve the previous
  // scroll offset; reset it after the new view has painted.
  requestAnimationFrame(() => window.scrollTo({ top: 0, left: 0 }))
})

export default router
