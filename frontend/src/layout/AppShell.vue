<script setup lang="ts">
import {
  CollectionTag,
  Connection,
  DataBoard,
  Fold,
  Menu,
  Setting,
  Share,
} from '@element-plus/icons-vue'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getAdminToken } from '../api/client'

const route = useRoute()
const router = useRouter()
const sidebarOpen = ref(false)
const tokenConfigured = ref(Boolean(getAdminToken()))

const navigation = [
  { to: '/', label: '概览', icon: DataBoard },
  { to: '/nodes', label: '节点', icon: Share },
  { to: '/agents', label: '边缘主机', icon: Connection },
  { to: '/subscriptions', label: '订阅', icon: Menu },
  { to: '/taxonomy', label: '分组与标签', icon: CollectionTag },
]

const syncToken = () => {
  tokenConfigured.value = Boolean(getAdminToken())
}

const handleInvalidToken = () => {
  tokenConfigured.value = false
  if (route.path !== '/settings') void router.push('/settings')
}

watch(
  () => route.path,
  () => {
    sidebarOpen.value = false
  },
)

onMounted(() => {
  window.addEventListener('sboard-token-change', syncToken)
  window.addEventListener('sboard-auth-invalid', handleInvalidToken)
})
onBeforeUnmount(() => {
  window.removeEventListener('sboard-token-change', syncToken)
  window.removeEventListener('sboard-auth-invalid', handleInvalidToken)
})
</script>

<template>
  <div class="app-shell">
    <button class="mobile-menu" type="button" aria-label="打开导航" @click="sidebarOpen = true">
      <el-icon><Menu /></el-icon>
    </button>
    <button
      v-if="sidebarOpen"
      class="sidebar-backdrop"
      type="button"
      aria-label="关闭导航"
      @click="sidebarOpen = false"
    />

    <aside class="sidebar" :class="{ 'is-open': sidebarOpen }">
      <div class="brand">
        <span class="brand-mark">S</span>
        <div>
          <strong>SBoard</strong>
          <span>节点控制台</span>
        </div>
        <button class="close-sidebar" type="button" aria-label="关闭导航" @click="sidebarOpen = false">
          <el-icon><Fold /></el-icon>
        </button>
      </div>

      <nav aria-label="主导航">
        <RouterLink
          v-for="item in navigation"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: route.path === item.to }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <RouterLink to="/settings" class="nav-item" :class="{ active: route.path === '/settings' }">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </RouterLink>
        <div class="connection-state">
          <span class="connection-dot" :class="{ configured: tokenConfigured }" />
          <span>{{ tokenConfigured ? '管理凭据已配置' : '等待配置管理凭据' }}</span>
        </div>
      </div>
    </aside>

    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.sidebar {
  position: fixed;
  z-index: 20;
  inset: 0 auto 0 0;
  display: flex;
  width: 240px;
  flex-direction: column;
  padding: 18px 12px 14px;
  background: #f7f6f3;
  border-right: 1px solid #e5e4e1;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 20px;
}

.brand-mark {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: #37352f;
  background: #fff;
  border: 1px solid #d8d7d3;
  border-radius: 6px;
  font-family: Georgia, serif;
  font-size: 18px;
  font-weight: 700;
}

.brand div {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 1px;
}

.brand strong {
  font-size: 14px;
  font-weight: 650;
}

.brand div span {
  color: #8b8a86;
  font-size: 11px;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  min-height: 34px;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  color: #5f5e59;
  border-radius: 6px;
  font-size: 14px;
  transition: background-color 150ms ease, color 150ms ease;
}

.nav-item:hover {
  color: #37352f;
  background: #efedea;
}

.nav-item:active,
.nav-item.active {
  color: #37352f;
  background: #e3e1db;
}

.nav-item .el-icon {
  color: #787774;
  font-size: 17px;
}

.sidebar-footer {
  display: flex;
  margin-top: auto;
  flex-direction: column;
  gap: 8px;
}

.connection-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 11px 2px;
  color: #8b8a86;
  font-size: 11px;
}

.connection-dot {
  width: 7px;
  height: 7px;
  background: #aaa8a3;
  border-radius: 2px;
}

.connection-dot.configured {
  background: #0f7b6c;
}

.main-content {
  min-height: 100vh;
  margin-left: 240px;
  background: #fff;
}

.mobile-menu,
.close-sidebar,
.sidebar-backdrop {
  display: none;
}

@media (max-width: 820px) {
  .main-content {
    margin-left: 0;
  }

  .sidebar {
    display: none;
    width: min(280px, 86vw);
  }

  .sidebar.is-open {
    display: flex;
  }

  .mobile-menu {
    position: fixed;
    z-index: 12;
    top: 18px;
    left: 18px;
    display: grid;
    width: 36px;
    height: 34px;
    place-items: center;
    color: #37352f;
    background: #f7f6f3;
    border: 1px solid #deddd9;
    border-radius: 6px;
  }

  .sidebar-backdrop {
    position: fixed;
    z-index: 18;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    padding: 0;
    background: rgb(15 15 15 / 18%);
    border: 0;
  }

  .close-sidebar {
    display: grid;
    width: 30px;
    height: 30px;
    place-items: center;
    color: #787774;
    background: transparent;
    border: 0;
    border-radius: 6px;
  }

  .close-sidebar:hover {
    background: #efedea;
  }
}
</style>
