<script setup lang="ts">
import { Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import StatusLabel from '../components/StatusLabel.vue'
import type { Agent, Group, NodePayload, NodeProtocol, NodeRecord, Tag } from '../types'

const protocols: NodeProtocol[] = [
  'vless',
  'vmess',
  'trojan',
  'ss',
  'ss2022',
  'hysteria2',
  'tuic',
  'wireguard',
]

const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const nodes = ref<NodeRecord[]>([])
const selectedNodes = ref<NodeRecord[]>([])
const agents = ref<Agent[]>([])
const groups = ref<Group[]>([])
const tags = ref<Tag[]>([])
const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const filters = ref({ keyword: '', protocol: '', source_type: '', enabled: '' })
let refreshTimer: number | undefined

function emptyNode(): NodePayload {
  return {
    source_type: 'external',
    agent_id: null,
    name: '',
    address: '',
    port: 443,
    protocol: 'vless',
    uuid: '',
    password: '',
    cipher: '',
    tls: true,
    reality: true,
    sni: '',
    public_key: '',
    short_id: '',
    flow: '',
    network: 'tcp',
    security: 'reality',
    path: '',
    host: '',
    service_name: '',
    enabled: true,
    sort_order: 0,
    extra: {},
    group_ids: [],
    tag_ids: [],
  }
}

const form = ref<NodePayload>(emptyNode())
const needsUuid = computed(() => ['vless', 'vmess', 'tuic'].includes(form.value.protocol))
const needsPassword = computed(() =>
  ['trojan', 'ss', 'ss2022', 'hysteria2', 'tuic'].includes(form.value.protocol),
)
const needsCipher = computed(() => ['ss', 'ss2022'].includes(form.value.protocol))

async function load(): Promise<void> {
  loading.value = true
  try {
    const enabled = filters.value.enabled === '' ? undefined : filters.value.enabled === 'true'
    const [nodePage, agentPage, groupList, tagList] = await Promise.all([
      api.nodes({ ...filters.value, enabled, page_size: 500 }),
      api.agents({ page_size: 200 }),
      api.groups(),
      api.tags(),
    ])
    nodes.value = nodePage.items
    agents.value = agentPage.items
    groups.value = groupList
    tags.value = tagList
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法加载节点')
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingId.value = null
  form.value = emptyNode()
  dialogOpen.value = true
}

function openEdit(node: NodeRecord): void {
  editingId.value = node.id
  const { id: _id, online_status: _status, created_at: _created, updated_at: _updated, ...payload } = node
  form.value = JSON.parse(JSON.stringify(payload)) as NodePayload
  dialogOpen.value = true
}

function normalizePayload(): NodePayload {
  const payload = JSON.parse(JSON.stringify(form.value)) as NodePayload
  payload.agent_id = payload.source_type === 'managed' ? payload.agent_id : null
  for (const key of [
    'uuid',
    'password',
    'cipher',
    'sni',
    'public_key',
    'short_id',
    'flow',
    'network',
    'security',
    'path',
    'host',
    'service_name',
  ] as const) {
    payload[key] = payload[key]?.trim() || null
  }
  return payload
}

async function save(): Promise<void> {
  if (!form.value.name.trim() || !form.value.address.trim()) {
    ElMessage.warning('请填写节点名称和地址')
    return
  }
  if (form.value.source_type === 'managed' && !form.value.agent_id) {
    ElMessage.warning('托管节点必须选择边缘主机')
    return
  }
  saving.value = true
  try {
    const payload = normalizePayload()
    if (editingId.value) await api.updateNode(editingId.value, payload)
    else await api.createNode(payload)
    ElMessage.success(editingId.value ? '节点已更新' : '节点已创建')
    dialogOpen.value = false
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(node: NodeRecord): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除节点 ${node.name}？`, '删除节点', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.deleteNode(node.id)
    ElMessage.success('节点已删除')
    await load()
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败')
  }
}

function handleSelectionChange(selection: NodeRecord[]): void {
  selectedNodes.value = selection
}

async function removeSelected(): Promise<void> {
  if (!selectedNodes.value.length) return
  const count = selectedNodes.value.length
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${count} 个节点？此操作无法撤销。`, '批量删除节点', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    deleting.value = true
    const result = await api.deleteNodes(selectedNodes.value.map((node) => node.id))
    ElMessage.success(`已删除 ${result.deleted} 个节点`)
    await load()
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '批量删除失败')
  } finally {
    deleting.value = false
  }
}

function generateUuid(): void {
  form.value.uuid = crypto.randomUUID()
}

function groupNames(ids: string[]): string {
  const names = groups.value.filter((group) => ids.includes(group.id)).map((group) => group.name)
  return names.join('、') || '未分组'
}

onMounted(() => {
  void load()
  refreshTimer = window.setInterval(() => void load(), 30_000)
})

onUnmounted(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="page">
    <PageHeader title="节点" description="统一管理 SBoardNode 托管节点与外部导入节点；外部节点显示 TCP 可达性。">
      <el-button type="primary" :icon="Plus" @click="openCreate">添加节点</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
      <el-button @click="$router.push('/import')">批量导入</el-button>
      <el-button
        :icon="Delete"
        :disabled="!selectedNodes.length"
        :loading="deleting"
        @click="removeSelected"
      >
        {{ selectedNodes.length ? `删除所选 (${selectedNodes.length})` : '批量删除' }}
      </el-button>
    </PageHeader>

    <div class="filter-bar surface">
      <el-input
        v-model="filters.keyword"
        :prefix-icon="Search"
        clearable
        placeholder="搜索名称或地址"
        @keyup.enter="load"
        @clear="load"
      />
      <el-select v-model="filters.protocol" clearable placeholder="全部协议" @change="load">
        <el-option v-for="protocol in protocols" :key="protocol" :label="protocol" :value="protocol" />
      </el-select>
      <el-select v-model="filters.source_type" clearable placeholder="全部来源" @change="load">
        <el-option label="托管节点" value="managed" />
        <el-option label="外部节点" value="external" />
      </el-select>
      <el-select v-model="filters.enabled" clearable placeholder="全部状态" @change="load">
        <el-option label="已启用" value="true" />
        <el-option label="已停用" value="false" />
      </el-select>
      <el-button @click="load">筛选</el-button>
    </div>

    <div class="surface table-surface" v-loading="loading">
      <el-table
        v-if="nodes.length"
        :data="nodes"
        row-key="id"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }: { row: NodeRecord }">
            <StatusLabel :status="row.online_status" />
          </template>
        </el-table-column>
        <el-table-column label="节点" min-width="210">
          <template #default="{ row }: { row: NodeRecord }">
            <div class="primary-cell">
              <strong>{{ row.name }}</strong>
              <span class="mono">{{ row.address }}:{{ row.port }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="协议" width="115">
          <template #default="{ row }: { row: NodeRecord }">
            <span class="protocol-label">{{ row.protocol }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="105">
          <template #default="{ row }: { row: NodeRecord }">
            {{ row.source_type === 'managed' ? 'SBoardNode' : '外部导入' }}
          </template>
        </el-table-column>
        <el-table-column label="传输" width="120">
          <template #default="{ row }: { row: NodeRecord }">
            {{ row.network || 'tcp' }}{{ row.reality ? ' / reality' : row.tls ? ' / tls' : '' }}
          </template>
        </el-table-column>
        <el-table-column label="分组" min-width="130">
          <template #default="{ row }: { row: NodeRecord }">
            <span class="muted">{{ groupNames(row.group_ids) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="116" fixed="right">
          <template #default="{ row }: { row: NodeRecord }">
            <div class="row-actions">
              <el-button text :icon="Edit" aria-label="编辑节点" @click="openEdit(row)" />
              <el-button text :icon="Delete" aria-label="删除节点" @click="remove(row)" />
            </div>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-else title="没有匹配的节点" description="添加一个节点，或从分享链接批量导入。">
        <el-button type="primary" @click="openCreate">添加节点</el-button>
      </EmptyState>
    </div>

    <el-dialog
      v-model="dialogOpen"
      :title="editingId ? '编辑节点' : '添加节点'"
      width="min(760px, 95vw)"
      destroy-on-close
    >
      <el-form label-position="top" class="node-form" @submit.prevent="save">
        <div class="form-grid">
          <el-form-item label="节点名称" required>
            <el-input v-model="form.name" placeholder="例如：东京 VLESS" />
          </el-form-item>
          <el-form-item label="协议" required>
            <el-select v-model="form.protocol">
              <el-option v-for="protocol in protocols" :key="protocol" :label="protocol" :value="protocol" />
            </el-select>
          </el-form-item>
          <el-form-item label="地址" required>
            <el-input v-model="form.address" placeholder="域名或 IP" />
          </el-form-item>
          <el-form-item label="端口" required>
            <el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" />
          </el-form-item>
          <el-form-item label="来源">
            <el-radio-group v-model="form.source_type">
              <el-radio value="external">外部节点</el-radio>
              <el-radio value="managed">SBoardNode 托管</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="form.source_type === 'managed'" label="边缘主机" required>
            <el-select v-model="form.agent_id" placeholder="选择主机">
              <el-option v-for="agent in agents" :key="agent.id" :label="agent.name" :value="agent.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="needsUuid" label="UUID" required class="wide-field">
            <div class="inline-field">
              <el-input v-model="form.uuid" class="mono-input" placeholder="UUID" />
              <el-button @click="generateUuid">生成</el-button>
            </div>
          </el-form-item>
          <el-form-item v-if="needsPassword" label="密码" required :class="{ 'wide-field': !needsCipher }">
            <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
          </el-form-item>
          <el-form-item v-if="needsCipher" label="加密方法" required>
            <el-input v-model="form.cipher" placeholder="例如：aes-128-gcm" />
          </el-form-item>
          <el-form-item label="分组">
            <el-select v-model="form.group_ids" multiple clearable placeholder="可选">
              <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="标签">
            <el-select v-model="form.tag_ids" multiple clearable placeholder="可选">
              <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
            </el-select>
          </el-form-item>
        </div>

        <el-collapse class="advanced-options">
          <el-collapse-item title="TLS、Reality 与传输选项" name="advanced">
            <div class="form-grid inner-grid">
              <el-form-item label="安全层">
                <div class="switches">
                  <el-checkbox v-model="form.tls">TLS</el-checkbox>
                  <el-checkbox v-model="form.reality">Reality</el-checkbox>
                </div>
              </el-form-item>
              <el-form-item label="传输方式">
                <el-select v-model="form.network" clearable>
                  <el-option label="tcp" value="tcp" />
                  <el-option label="ws" value="ws" />
                  <el-option label="grpc" value="grpc" />
                  <el-option label="httpupgrade" value="httpupgrade" />
                </el-select>
              </el-form-item>
              <el-form-item label="SNI">
                <el-input v-model="form.sni" />
              </el-form-item>
              <el-form-item label="Flow">
                <el-input v-model="form.flow" placeholder="xtls-rprx-vision" />
              </el-form-item>
              <el-form-item v-if="form.reality" label="Reality Public Key">
                <el-input v-model="form.public_key" />
              </el-form-item>
              <el-form-item v-if="form.reality" label="Reality Short ID">
                <el-input v-model="form.short_id" />
              </el-form-item>
              <el-form-item label="Path">
                <el-input v-model="form.path" />
              </el-form-item>
              <el-form-item label="Host">
                <el-input v-model="form.host" />
              </el-form-item>
              <el-form-item v-if="form.network === 'grpc'" label="gRPC Service Name">
                <el-input v-model="form.service_name" />
              </el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>

        <div class="form-footer-options">
          <el-checkbox v-model="form.enabled">启用节点</el-checkbox>
          <label>
            排序
            <el-input-number v-model="form.sort_order" :min="-9999" :max="9999" controls-position="right" />
          </label>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存节点</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.filter-bar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(130px, 0.45fr)) auto;
  gap: 8px;
  margin-bottom: 12px;
  padding: 12px;
}

.table-surface {
  min-height: 320px;
  overflow: hidden;
}

.primary-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.primary-cell strong {
  overflow: hidden;
  color: #37352f;
  font-size: 13px;
  font-weight: 550;
  text-overflow: ellipsis;
}

.primary-cell span {
  overflow: hidden;
  color: #8b8a86;
  text-overflow: ellipsis;
}

.protocol-label {
  padding: 2px 5px;
  color: #4e5e64;
  background: #edf3f5;
  border-radius: 4px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.row-actions {
  display: flex;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.wide-field {
  grid-column: 1 / -1;
}

.inline-field {
  display: grid;
  width: 100%;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.mono-input :deep(input) {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}

.node-form :deep(.el-select),
.node-form :deep(.el-input-number) {
  width: 100%;
}

.advanced-options {
  margin-top: 2px;
  border-top-color: #ebeae7;
  border-bottom-color: #ebeae7;
}

.inner-grid {
  padding-top: 12px;
}

.switches {
  display: flex;
  min-height: 32px;
  align-items: center;
  gap: 16px;
}

.form-footer-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 18px;
}

.form-footer-options label {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #787774;
  font-size: 12px;
}

.form-footer-options :deep(.el-input-number) {
  width: 110px;
}

@media (max-width: 1000px) {
  .filter-bar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .filter-bar,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .wide-field {
    grid-column: auto;
  }
}
</style>
