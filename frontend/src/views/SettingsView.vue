<script setup lang="ts">
import { Check, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { api } from '../api'
import { getAdminToken, setAdminToken } from '../api/client'
import PageHeader from '../components/PageHeader.vue'

const token = ref('')
const testing = ref(false)
const connected = ref<boolean | null>(null)
const backendVersion = ref('')
const origin = window.location.origin

async function saveAndTest(): Promise<void> {
  if (!token.value.trim()) {
    ElMessage.warning('请输入管理 Token')
    return
  }
  const previous = getAdminToken()
  setAdminToken(token.value)
  testing.value = true
  connected.value = null
  try {
    await api.overview()
    connected.value = true
    ElMessage.success('连接成功，管理 Token 已保存')
  } catch (reason) {
    connected.value = false
    setAdminToken(previous)
    ElMessage.error(reason instanceof Error ? reason.message : '连接失败')
  } finally {
    testing.value = false
  }
}

async function loadHealth(): Promise<void> {
  try {
    const response = await fetch('/health')
    const data = (await response.json()) as { version?: string }
    backendVersion.value = data.version ?? ''
  } catch {
    backendVersion.value = ''
  }
}

onMounted(() => {
  token.value = getAdminToken()
  void loadHealth()
})
</script>

<template>
  <div class="page">
    <PageHeader title="设置" description="配置当前浏览器连接 SBoard 后端所需的管理凭据。" />

    <section class="settings-grid">
      <div class="surface settings-panel">
        <div class="panel-title">
          <el-icon><Lock /></el-icon>
          <div>
            <h2 class="section-title">管理 Token</h2>
            <p class="section-note">仅保存在当前浏览器，不会写入前端构建产物。</p>
          </div>
        </div>
        <el-form label-position="top" @submit.prevent="saveAndTest">
          <el-form-item label="SBOARD_ADMIN_TOKEN">
            <el-input
              v-model="token"
              type="password"
              show-password
              autocomplete="current-password"
              placeholder="粘贴后端配置的管理 Token"
              @keyup.enter="saveAndTest"
            />
          </el-form-item>
          <el-button type="primary" :loading="testing" @click="saveAndTest">验证并保存</el-button>
        </el-form>
      </div>

      <aside class="surface info-panel">
        <h2 class="section-title">连接信息</h2>
        <dl>
          <div>
            <dt>API 地址</dt>
            <dd class="mono">{{ origin }}</dd>
          </div>
          <div>
            <dt>后端版本</dt>
            <dd>{{ backendVersion || '无法读取' }}</dd>
          </div>
          <div>
            <dt>凭据状态</dt>
            <dd :class="{ success: connected === true, failed: connected === false }">
              <el-icon v-if="connected === true"><Check /></el-icon>
              {{ connected === null ? (token ? '已保存，尚未验证' : '尚未配置') : connected ? '连接正常' : '验证失败' }}
            </dd>
          </div>
        </dl>
        <p class="privacy-note">
          这是单管理员面板，不包含用户系统。请只在可信设备中保存 Token，并通过 HTTPS 或内网访问。
        </p>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.8fr);
  gap: 16px;
}

.settings-panel,
.info-panel {
  padding: 22px;
}

.panel-title {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  margin-bottom: 24px;
}

.panel-title > .el-icon {
  margin-top: 1px;
  color: #787774;
  font-size: 19px;
}

.el-form {
  max-width: 620px;
}

dl {
  margin: 18px 0;
}

dl > div {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #efeeeb;
}

dt {
  color: #8b8a86;
  font-size: 12px;
}

dd {
  overflow: hidden;
  margin: 0;
  color: #4b4a46;
  font-size: 12px;
  text-overflow: ellipsis;
}

dd.success {
  color: #0f7b6c;
}

dd.failed {
  color: #b44949;
}

.privacy-note {
  margin: 20px 0 0;
  padding: 13px;
  color: #6f6e69;
  background: #f7f6f3;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.65;
}

@media (max-width: 920px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
