<script setup lang="ts">
import { CopyDocument, Plus, Refresh, SwitchButton } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusLabel from '../components/StatusLabel.vue'
import type { Agent } from '../types'
import { copyText, formatBytes, formatDate, formatUptime } from '../utils'

const loading = ref(false)
const agents = ref<Agent[]>([])
const createOpen = ref(false)
const creating = ref(false)
const newName = ref('')
const secretOpen = ref(false)
const oneTimeToken = ref('')
const oneTimeNodeId = ref('')
const oneTimeConfig = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    agents.value = (await api.agents({ page_size: 200 })).items
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法加载边缘主机')
  } finally {
    loading.value = false
  }
}

function showSecret(token: string, nodeId: string, config?: Record<string, unknown>): void {
  oneTimeToken.value = token
  oneTimeNodeId.value = nodeId
  oneTimeConfig.value = config ? JSON.stringify(config, null, 2) : ''
  secretOpen.value = true
}

async function createAgent(): Promise<void> {
  if (!newName.value.trim()) {
    ElMessage.warning('请输入主机名称')
    return
  }
  creating.value = true
  try {
    const result = await api.createAgent(newName.value)
    createOpen.value = false
    newName.value = ''
    showSecret(result.token, result.agent.id, result.config)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '创建失败')
  } finally {
    creating.value = false
  }
}

async function toggleAgent(agent: Agent): Promise<void> {
  try {
    await api.updateAgent(agent.id, { enabled: !agent.enabled })
    ElMessage.success(agent.enabled ? '已停用主机' : '已启用主机')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '操作失败')
  }
}

async function rotateToken(agent: Agent): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `重置后 ${agent.name} 的旧 Token 会立即失效，需要手动更新 SBoardNode 配置。`,
      '重置 Agent Token',
      { confirmButtonText: '继续重置', cancelButtonText: '取消', type: 'warning' },
    )
    const result = await api.rotateAgentToken(agent.id)
    showSecret(result.token, result.agent_id)
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '重置失败')
  }
}

async function deleteAgent(agent: Agent): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${agent.name}？存在托管节点时后端会拒绝删除。`,
      '删除边缘主机',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await api.deleteAgent(agent.id)
    ElMessage.success('边缘主机已删除')
    await load()
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败')
  }
}

async function copy(value: string): Promise<void> {
  await copyText(value)
  ElMessage.success('已复制')
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="边缘主机" description="管理运行 SBoardNode 的 Linux 主机与一次性通信凭据。">
      <el-button type="primary" :icon="Plus" @click="createOpen = true">添加主机</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </PageHeader>

    <div class="surface table-surface" v-loading="loading">
      <el-table v-if="agents.length" :data="agents" row-key="id">
        <el-table-column label="状态" width="95">
          <template #default="{ row }: { row: Agent }">
            <StatusLabel :status="row.online ? 'online' : 'offline'" />
          </template>
        </el-table-column>
        <el-table-column label="主机" min-width="180">
          <template #default="{ row }: { row: Agent }">
            <div class="primary-cell">
              <strong>{{ row.name }}</strong>
              <span class="mono">{{ row.id }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Xray" width="110">
          <template #default="{ row }: { row: Agent }">
            <StatusLabel :status="row.xray_status" :text="row.xray_version || row.xray_status" />
          </template>
        </el-table-column>
        <el-table-column label="资源" min-width="180">
          <template #default="{ row }: { row: Agent }">
            <div class="resource-cell">
              <span>CPU {{ row.cpu_percent === null ? '—' : `${row.cpu_percent.toFixed(1)}%` }}</span>
              <span>{{ formatBytes(row.memory_used_bytes) }} / {{ formatBytes(row.memory_total_bytes) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="运行时间" width="130">
          <template #default="{ row }: { row: Agent }">{{ formatUptime(row.uptime_seconds) }}</template>
        </el-table-column>
        <el-table-column label="最后心跳" width="120">
          <template #default="{ row }: { row: Agent }">{{ formatDate(row.last_seen_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }: { row: Agent }">
            <div class="row-actions">
              <el-button size="small" @click="rotateToken(row)">重置 Token</el-button>
              <el-dropdown trigger="click">
                <el-button size="small" aria-label="更多操作">•••</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item :icon="SwitchButton" @click="toggleAgent(row)">
                      {{ row.enabled ? '停用' : '启用' }}
                    </el-dropdown-item>
                    <el-dropdown-item divided class="danger-text" @click="deleteAgent(row)">
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-else title="还没有边缘主机" description="创建 Agent 后，将一次性 Token 手动写入 SBoardNode 配置。">
        <el-button type="primary" @click="createOpen = true">添加第一台主机</el-button>
      </EmptyState>
    </div>

    <el-dialog v-model="createOpen" title="添加边缘主机" width="min(480px, 92vw)" destroy-on-close>
      <el-form label-position="top" @submit.prevent="createAgent">
        <el-form-item label="主机名称">
          <el-input v-model="newName" autofocus placeholder="例如：香港轻量服务器" @keyup.enter="createAgent" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createAgent">创建并生成 Token</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="secretOpen" title="保存一次性凭据" width="min(620px, 94vw)" :close-on-click-modal="false">
      <el-alert
        title="关闭后无法再次查看明文 Token。请立即保存到 SBoardNode 的配置文件。"
        type="warning"
        :closable="false"
        show-icon
      />
      <div class="secret-block">
        <div>
          <span>Node ID</span>
          <code>{{ oneTimeNodeId }}</code>
        </div>
        <el-button :icon="CopyDocument" @click="copy(oneTimeNodeId)">复制</el-button>
      </div>
      <div class="secret-block">
        <div>
          <span>Agent Token</span>
          <code>{{ oneTimeToken }}</code>
        </div>
        <el-button :icon="CopyDocument" @click="copy(oneTimeToken)">复制</el-button>
      </div>
      <div v-if="oneTimeConfig" class="config-block">
        <div class="config-heading">
          <span>配置参考</span>
          <el-button size="small" :icon="CopyDocument" @click="copy(oneTimeConfig)">复制配置</el-button>
        </div>
        <pre>{{ oneTimeConfig }}</pre>
      </div>
      <template #footer>
        <el-button type="primary" @click="secretOpen = false">我已保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.table-surface {
  min-height: 300px;
  overflow: hidden;
}

.primary-cell,
.resource-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.primary-cell strong {
  color: #37352f;
  font-size: 13px;
  font-weight: 550;
}

.primary-cell span,
.resource-cell span {
  overflow: hidden;
  color: #8b8a86;
  font-size: 11px;
  text-overflow: ellipsis;
}

.row-actions {
  display: flex;
  gap: 6px;
}

.secret-block {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  margin-top: 14px;
  padding: 12px;
  background: #f7f6f3;
  border: 1px solid #e5e4e1;
  border-radius: 6px;
}

.secret-block > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.secret-block span,
.config-heading span {
  color: #787774;
  font-size: 11px;
}

.secret-block code {
  overflow: hidden;
  color: #37352f;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  text-overflow: ellipsis;
}

.config-block {
  margin-top: 14px;
}

.config-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

pre {
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 14px;
  color: #4b4a46;
  background: #f7f6f3;
  border: 1px solid #e5e4e1;
  border-radius: 6px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  line-height: 1.6;
}
</style>

