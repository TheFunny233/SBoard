<script setup lang="ts">
import { CopyDocument, Plus, Refresh, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import type { Group, NodeRecord, Subscription, SubscriptionPreview, Tag } from '../types'
import { copyText, formatDate } from '../utils'

const loading = ref(false)
const saving = ref(false)
const subscriptions = ref<Subscription[]>([])
const nodes = ref<NodeRecord[]>([])
const groups = ref<Group[]>([])
const tags = ref<Tag[]>([])
const createOpen = ref(false)
const secretOpen = ref(false)
const previewOpen = ref(false)
const previewLoading = ref(false)
const secretUrls = ref<Record<string, string>>({})
const secretToken = ref('')
const preview = ref<SubscriptionPreview | null>(null)
const previewFormat = ref<'clash' | 'v2ray'>('clash')
const previewSubscriptionId = ref('')
const form = ref({
  name: '',
  include_all_nodes: true,
  node_ids: [] as string[],
  group_ids: [] as string[],
  tag_ids: [] as string[],
  group_name: 'Proxy',
  include_auto: true,
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const [subscriptionList, nodePage, groupList, tagList] = await Promise.all([
      api.subscriptions(),
      api.nodes({ enabled: true, page_size: 500 }),
      api.groups(),
      api.tags(),
    ])
    subscriptions.value = subscriptionList
    nodes.value = nodePage.items
    groups.value = groupList
    tags.value = tagList
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法加载订阅')
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  form.value = {
    name: '',
    include_all_nodes: true,
    node_ids: [],
    group_ids: [],
    tag_ids: [],
    group_name: 'Proxy',
    include_auto: true,
  }
  createOpen.value = true
}

function showSecret(token: string, urls: Record<string, string>): void {
  secretToken.value = token
  secretUrls.value = Object.fromEntries(
    Object.entries(urls).map(([key, value]) => [key, new URL(value, window.location.origin).toString()]),
  )
  secretOpen.value = true
}

async function createSubscription(): Promise<void> {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入订阅名称')
    return
  }
  saving.value = true
  try {
    const result = await api.createSubscription({
      name: form.value.name,
      enabled: true,
      include_all_nodes: form.value.include_all_nodes,
      node_ids: form.value.node_ids,
      group_ids: form.value.group_ids,
      tag_ids: form.value.tag_ids,
      config: {
        group_name: form.value.group_name,
        include_auto: form.value.include_auto,
      },
    })
    createOpen.value = false
    showSecret(result.token, result.urls)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '创建失败')
  } finally {
    saving.value = false
  }
}

async function toggle(subscription: Subscription): Promise<void> {
  try {
    await api.updateSubscription(subscription.id, { enabled: !subscription.enabled })
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '更新失败')
  }
}

async function rotate(subscription: Subscription): Promise<void> {
  try {
    await ElMessageBox.confirm('旧订阅地址会立即失效，需要更新所有客户端。', '重置订阅 Token', {
      confirmButtonText: '继续重置',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const result = await api.rotateSubscriptionToken(subscription.id)
    showSecret(result.token, result.urls)
    await load()
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '重置失败')
  }
}

async function openPreview(subscription: Subscription, format: 'clash' | 'v2ray' = 'clash'): Promise<void> {
  previewSubscriptionId.value = subscription.id
  previewFormat.value = format
  previewOpen.value = true
  await loadPreview()
}

async function loadPreview(): Promise<void> {
  previewLoading.value = true
  try {
    preview.value = await api.previewSubscription(previewSubscriptionId.value, previewFormat.value)
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法生成预览')
  } finally {
    previewLoading.value = false
  }
}

async function remove(subscription: Subscription): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除订阅 ${subscription.name}？`, '删除订阅', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.deleteSubscription(subscription.id)
    ElMessage.success('订阅已删除')
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
    <PageHeader title="订阅" description="从同一组节点生成 Clash Meta YAML 与 V2Ray Base64 订阅。">
      <el-button type="primary" :icon="Plus" @click="openCreate">创建订阅</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </PageHeader>

    <div class="surface table-surface" v-loading="loading">
      <el-table v-if="subscriptions.length" :data="subscriptions" row-key="id">
        <el-table-column label="订阅" min-width="190">
          <template #default="{ row }: { row: Subscription }">
            <div class="primary-cell">
              <strong>{{ row.name }}</strong>
              <span class="mono">{{ row.token_hint }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="节点范围" min-width="160">
          <template #default="{ row }: { row: Subscription }">
            <span v-if="row.include_all_nodes">全部启用节点</span>
            <span v-else>{{ row.node_ids.length }} 节点 · {{ row.group_ids.length }} 分组 · {{ row.tag_ids.length }} 标签</span>
          </template>
        </el-table-column>
        <el-table-column label="最近访问" width="130">
          <template #default="{ row }: { row: Subscription }">{{ formatDate(row.last_access_at) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="78">
          <template #default="{ row }: { row: Subscription }">
            <el-switch :model-value="row.enabled" aria-label="启用订阅" @change="toggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }: { row: Subscription }">
            <div class="row-actions">
              <el-button size="small" :icon="View" @click="openPreview(row)">预览</el-button>
              <el-button size="small" @click="rotate(row)">重置 Token</el-button>
              <el-dropdown trigger="click">
                <el-button size="small" aria-label="更多操作">•••</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item class="danger-text" @click="remove(row)">删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-else title="还没有订阅" description="创建一个订阅，将选定节点输出给 Clash Meta 或其他客户端。">
        <el-button type="primary" @click="openCreate">创建第一个订阅</el-button>
      </EmptyState>
    </div>

    <el-dialog v-model="createOpen" title="创建订阅" width="min(620px, 94vw)" destroy-on-close>
      <el-form label-position="top" @submit.prevent="createSubscription">
        <el-form-item label="订阅名称" required>
          <el-input v-model="form.name" placeholder="例如：个人设备" />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.include_all_nodes">包含全部启用节点</el-checkbox>
        </el-form-item>
        <template v-if="!form.include_all_nodes">
          <el-form-item label="指定节点">
            <el-select v-model="form.node_ids" multiple clearable placeholder="可选">
              <el-option v-for="node in nodes" :key="node.id" :label="node.name" :value="node.id" />
            </el-select>
          </el-form-item>
          <div class="selection-grid">
            <el-form-item label="包含分组">
              <el-select v-model="form.group_ids" multiple clearable placeholder="可选">
                <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="包含标签">
              <el-select v-model="form.tag_ids" multiple clearable placeholder="可选">
                <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
              </el-select>
            </el-form-item>
          </div>
        </template>
        <div class="selection-grid">
          <el-form-item label="Clash 代理组名称">
            <el-input v-model="form.group_name" />
          </el-form-item>
          <el-form-item label="自动测速组">
            <el-checkbox v-model="form.include_auto">生成 Auto 组</el-checkbox>
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createSubscription">创建订阅</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="secretOpen" title="保存订阅地址" width="min(650px, 94vw)" :close-on-click-modal="false">
      <el-alert title="明文 Token 和完整订阅地址关闭后无法再次查看。" type="warning" :closable="false" show-icon />
      <div class="secret-row">
        <div><span>Token</span><code>{{ secretToken }}</code></div>
        <el-button :icon="CopyDocument" @click="copy(secretToken)">复制</el-button>
      </div>
      <div v-for="(url, name) in secretUrls" :key="name" class="secret-row">
        <div><span>{{ name }}</span><code>{{ url }}</code></div>
        <el-button :icon="CopyDocument" @click="copy(url)">复制</el-button>
      </div>
      <template #footer>
        <el-button type="primary" @click="secretOpen = false">我已保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="previewOpen" title="订阅预览" size="min(720px, 94vw)">
      <div class="preview-toolbar">
        <el-radio-group v-model="previewFormat" @change="loadPreview">
          <el-radio-button value="clash">Clash Meta</el-radio-button>
          <el-radio-button value="v2ray">V2Ray Base64</el-radio-button>
        </el-radio-group>
        <el-button v-if="preview" :icon="CopyDocument" @click="copy(preview.content)">复制</el-button>
      </div>
      <div v-loading="previewLoading" class="preview-body">
        <el-alert
          v-for="warning in preview?.warnings"
          :key="warning"
          :title="warning"
          type="warning"
          :closable="false"
          class="preview-warning"
        />
        <pre v-if="preview">{{ preview.content }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.table-surface {
  min-height: 300px;
  overflow: hidden;
}

.primary-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.primary-cell strong {
  color: #37352f;
  font-size: 13px;
  font-weight: 550;
}

.primary-cell span {
  color: #8b8a86;
}

.row-actions {
  display: flex;
  gap: 6px;
}

.el-form :deep(.el-select) {
  width: 100%;
}

.selection-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.secret-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  margin-top: 12px;
  padding: 12px;
  background: #f7f6f3;
  border: 1px solid #e5e4e1;
  border-radius: 6px;
}

.secret-row > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.secret-row span {
  color: #787774;
  font-size: 11px;
  text-transform: capitalize;
}

.secret-row code {
  overflow: hidden;
  color: #37352f;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}

.preview-body {
  min-height: 240px;
}

.preview-warning {
  margin-bottom: 8px;
}

pre {
  min-height: 300px;
  max-height: calc(100vh - 200px);
  overflow: auto;
  margin: 0;
  padding: 16px;
  color: #4b4a46;
  background: #f7f6f3;
  border: 1px solid #e5e4e1;
  border-radius: 6px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}

@media (max-width: 600px) {
  .selection-grid {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>

