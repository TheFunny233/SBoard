import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/nodes', name: 'nodes', component: () => import('../views/NodesView.vue') },
    { path: '/agents', name: 'agents', component: () => import('../views/AgentsView.vue') },
    { path: '/import', name: 'import', component: () => import('../views/ImportView.vue') },
    { path: '/rules', name: 'rules', component: () => import('../views/RulesView.vue') },
    {
      path: '/subscriptions',
      name: 'subscriptions',
      component: () => import('../views/SubscriptionsView.vue'),
    },
    { path: '/taxonomy', name: 'taxonomy', component: () => import('../views/TaxonomyView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
