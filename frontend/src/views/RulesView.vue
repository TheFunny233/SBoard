<script setup lang="ts">
import { Delete, Edit, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import type { Group, NodeRecord, RuleSet, RuleSetPayload, RuleTargetMode } from '../types'

interface RuleTemplate {
  name: string
  category: string
  description: string
  targetMode: RuleTargetMode
  sortOrder: number
  rules: string[]
}

const templates: RuleTemplate[] = [
  {
    name: '中国大陆与局域网',
    category: '直连',
    description: '中国大陆域名、IP 与局域网地址直接连接',
    targetMode: 'direct',
    sortOrder: -300,
    rules: [
      'GEOSITE,private',
      'GEOIP,private,no-resolve',
      'GEOSITE,cn',
      'GEOIP,CN,no-resolve',
    ],
  },
  {
    name: 'AI 高纯净度',
    category: 'AI',
    description: 'OpenAI、Claude 与 Gemini；建议目标选择高纯净度节点组',
    targetMode: 'group',
    sortOrder: -200,
    rules: [
      'DOMAIN-SUFFIX,openai.com',
      'DOMAIN-SUFFIX,chatgpt.com',
      'DOMAIN-SUFFIX,oaistatic.com',
      'DOMAIN-SUFFIX,oaiusercontent.com',
      'DOMAIN-SUFFIX,claude.ai',
      'DOMAIN-SUFFIX,anthropic.com',
      'DOMAIN,gemini.google.com',
      'DOMAIN,aistudio.google.com',
      'DOMAIN-SUFFIX,generativelanguage.googleapis.com',
    ],
  },
  {
    name: '大流量与开发站点',
    category: '通用代理',
    description: 'YouTube、X、Instagram、Google、GitHub、GitLab 及常用开发资源',
    targetMode: 'node',
    sortOrder: -100,
    rules: [
      'DOMAIN-SUFFIX,youtube.com',
      'DOMAIN-SUFFIX,youtu.be',
      'DOMAIN-SUFFIX,googlevideo.com',
      'DOMAIN-SUFFIX,ytimg.com',
      'DOMAIN-SUFFIX,ggpht.com',
      'DOMAIN-SUFFIX,x.com',
      'DOMAIN-SUFFIX,twitter.com',
      'DOMAIN-SUFFIX,twimg.com',
      'DOMAIN-SUFFIX,instagram.com',
      'DOMAIN-SUFFIX,cdninstagram.com',
      'DOMAIN-SUFFIX,google.com',
      'DOMAIN-SUFFIX,googleapis.com',
      'DOMAIN-SUFFIX,gstatic.com',
      'DOMAIN-SUFFIX,googleusercontent.com',
      'DOMAIN-SUFFIX,github.com',
      'DOMAIN-SUFFIX,githubusercontent.com',
      'DOMAIN-SUFFIX,githubassets.com',
      'DOMAIN-SUFFIX,github.io',
      'DOMAIN-SUFFIX,gitlab.com',
      'DOMAIN-SUFFIX,gitlab-static.net',
      'DOMAIN-SUFFIX,npmjs.com',
      'DOMAIN-SUFFIX,npmjs.org',
      'DOMAIN-SUFFIX,docker.com',
      'DOMAIN-SUFFIX,docker.io',
    ],
  },
]

const loading = ref(false)
const saving = ref(false)
const rules = ref<RuleSet[]>([])
const nodes = ref<NodeRecord[]>([])
const groups = ref<Group[]>([])
const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const rulesText = ref('')

function emptyForm(): RuleSetPayload {
  return {
    name: '',
    description: null,
    enabled: true,
    target_mode: 'node',
    node_id: null,
    group_id: null,
    rules: [],
    sort_order: 0,
  }
}

const form = ref<RuleSetPayload>(emptyForm())
const enabledNodes = computed(() => nodes.value.filter((node) => node.enabled))

async function load(): Promise<void> {
  loading.value = true
  try {
    const [ruleList, nodePage, groupList] = await Promise.all([
      api.rules(),
      api.nodes({ page_size: 500 }),
      api.groups(),
    ])
    rules.value = ruleList
    nodes.value = nodePage.items
    groups.value = groupList
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法加载规则')
  } finally {
    loading.value = false
  }
}

function openCreate(template?: RuleTemplate): void {
  editingId.value = null
  form.value = {
    ...emptyForm(),
    name: template?.name || '',
    description: template?.description || null,
    target_mode: template?.targetMode || 'node',
    sort_order: template?.sortOrder || 0,
  }
  rulesText.value = template?.rules.join('\n') || ''
  dialogOpen.value = true
}

function openEdit(rule: RuleSet): void {
  editingId.value = rule.id
  form.value = {
    name: rule.name,
    description: rule.description,
    enabled: rule.enabled,
    target_mode: rule.target_mode,
    node_id: rule.node_id,
    group_id: rule.group_id,
    rules: [...rule.rules],
    sort_order: rule.sort_order,
  }
  rulesText.value = rule.rules.join('\n')
  dialogOpen.value = true
}

function targetLabel(rule: RuleSet): string {
  if (rule.target_mode === 'direct') return 'DIRECT'
  if (rule.target_mode === 'reject') return 'REJECT'
  if (rule.target_mode === 'group') return rule.target_group_name || '目标节点组已删除'
  return rule.target_node_name || '目标节点已删除'
}

function onTargetModeChange(mode: RuleTargetMode): void {
  if (mode !== 'node') form.value.node_id = null
  if (mode !== 'group') form.value.group_id = null
}

async function save(): Promise<void> {
  const conditions = rulesText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入规则名称')
    return
  }
  if (form.value.target_mode === 'node' && !form.value.node_id) {
    ElMessage.warning('请选择目标节点')
    return
  }
  if (form.value.target_mode === 'group' && !form.value.group_id) {
    ElMessage.warning('请选择目标节点组')
    return
  }
  if (!conditions.length) {
    ElMessage.warning('请至少填写一条规则')
    return
  }
  saving.value = true
  try {
    const payload: RuleSetPayload = {
      ...form.value,
      name: form.value.name.trim(),
      description: form.value.description?.trim() || null,
      node_id: form.value.target_mode === 'node' ? form.value.node_id : null,
      group_id: form.value.target_mode === 'group' ? form.value.group_id : null,
      rules: conditions,
    }
    if (editingId.value) await api.updateRule(editingId.value, payload)
    else await api.createRule(payload)
    ElMessage.success(editingId.value ? '规则已更新' : '规则已创建')
    dialogOpen.value = false
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function toggle(rule: RuleSet): Promise<void> {
  try {
    await api.updateRule(rule.id, { enabled: !rule.enabled })
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '更新失败')
  }
}

async function remove(rule: RuleSet): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除规则 ${rule.name}？`, '删除规则', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.deleteRule(rule.id)
    ElMessage.success('规则已删除')
    await load()
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="规则" description="为 Clash Meta 订阅设置按站点分流的目标节点或节点组。">
      <el-button type="primary" :icon="Plus" @click="openCreate()">添加规则</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </PageHeader>

    <section class="surface template-section">
      <div class="section-heading">
        <div>
          <h2>常用场景</h2>
          <p>大陆流量默认直连；AI 使用高纯净度节点组，通用代理单独选择节点。</p>
        </div>
      </div>
      <div class="template-grid">
        <button
          v-for="template in templates"
          :key="template.name"
          class="template-card"
          type="button"
          @click="openCreate(template)"
        >
          <span>{{ template.category }}</span>
          <strong>{{ template.name }}</strong>
          <small>{{ template.rules.length }} 条规则</small>
        </button>
      </div>
    </section>

    <div class="surface table-surface" v-loading="loading">
      <el-table v-if="rules.length" :data="rules" row-key="id">
        <el-table-column label="规则集" min-width="210">
          <template #default="{ row }: { row: RuleSet }">
            <div class="primary-cell">
              <strong>{{ row.name }}</strong>
              <span>{{ row.description || '无描述' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="目标" min-width="150">
          <template #default="{ row }: { row: RuleSet }">
            <span
              class="target-label"
              :class="{
                missing:
                  (row.target_mode === 'node' && !row.target_node_name) ||
                  (row.target_mode === 'group' && !row.target_group_name),
              }"
            >
              {{ targetLabel(row) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="条件" width="90">
          <template #default="{ row }: { row: RuleSet }">{{ row.rules.length }} 条</template>
        </el-table-column>
        <el-table-column label="优先级" width="90" prop="sort_order" />
        <el-table-column label="启用" width="76">
          <template #default="{ row }: { row: RuleSet }">
            <el-switch :model-value="row.enabled" aria-label="启用规则" @change="toggle(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="116" fixed="right">
          <template #default="{ row }: { row: RuleSet }">
            <div class="row-actions">
              <el-button text :icon="Edit" aria-label="编辑规则" @click="openEdit(row)" />
              <el-button text :icon="Delete" aria-label="删除规则" @click="remove(row)" />
            </div>
          </template>
        </el-table-column>
      </el-table>
      <EmptyState v-else title="还没有分流规则" description="使用常用站点模板，或手动添加一组 Clash Meta 规则。">
        <el-button type="primary" @click="openCreate()">添加第一条规则</el-button>
      </EmptyState>
    </div>

    <el-dialog
      v-model="dialogOpen"
      :title="editingId ? '编辑规则' : '添加规则'"
      width="min(680px, 94vw)"
      destroy-on-close
    >
      <el-form label-position="top" @submit.prevent="save">
        <div class="form-grid">
          <el-form-item label="规则名称" required>
            <el-input v-model="form.name" placeholder="例如：YouTube" />
          </el-form-item>
          <el-form-item label="优先级">
            <el-input-number v-model="form.sort_order" :min="-9999" :max="9999" controls-position="right" />
          </el-form-item>
        </div>
        <el-form-item label="说明">
          <el-input v-model="form.description" placeholder="可选" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item label="流量目标" required>
            <el-select v-model="form.target_mode" @change="onTargetModeChange">
              <el-option label="指定节点" value="node" />
              <el-option label="指定节点组" value="group" />
              <el-option label="DIRECT（直连）" value="direct" />
              <el-option label="REJECT（拒绝）" value="reject" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.target_mode === 'node'" label="目标节点" required>
            <el-select v-model="form.node_id" filterable placeholder="选择节点">
              <el-option
                v-for="node in enabledNodes"
                :key="node.id"
                :label="`${node.name} · ${node.protocol}`"
                :value="node.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="form.target_mode === 'group'" label="目标节点组" required>
            <el-select v-model="form.group_id" filterable placeholder="选择节点组">
              <el-option
                v-for="group in groups"
                :key="group.id"
                :label="group.name"
                :value="group.id"
              />
            </el-select>
          </el-form-item>
        </div>
        <p v-if="form.target_mode === 'group'" class="target-help">
          节点组在「分组与标签」中维护；订阅只会写入该组内且已被订阅包含的节点。
        </p>
        <el-form-item label="规则条件（每行一条）" required>
          <el-input
            v-model="rulesText"
            type="textarea"
            :rows="10"
            resize="vertical"
            placeholder="DOMAIN-SUFFIX,youtube.com&#10;DOMAIN-KEYWORD,googlevideo"
            class="rule-editor"
          />
        </el-form-item>
        <p class="rule-help">
          这里只写匹配条件，不要填写策略名称；目标节点或节点组会自动附加。支持 DOMAIN、DOMAIN-SUFFIX、DOMAIN-KEYWORD、GEOSITE、GEOIP、IP-CIDR 等常见类型。
        </p>
        <el-checkbox v-model="form.enabled">启用此规则集</el-checkbox>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存规则</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.template-section {
  margin-bottom: 12px;
  padding: 16px;
}

.section-heading h2 {
  margin: 0;
  color: #37352f;
  font-size: 14px;
  font-weight: 600;
}

.section-heading p {
  margin: 4px 0 0;
  color: #8b8a86;
  font-size: 12px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.template-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  padding: 12px;
  color: #37352f;
  text-align: left;
  background: #fbfbfa;
  border: 1px solid #e5e4e1;
  border-radius: 6px;
  cursor: pointer;
}

.template-card:hover {
  background: #f7f6f3;
  border-color: #d8d7d3;
}

.template-card span,
.template-card small {
  color: #8b8a86;
  font-size: 11px;
}

.template-card strong {
  overflow: hidden;
  max-width: 100%;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-surface {
  min-height: 300px;
  overflow: hidden;
}

.primary-cell {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.primary-cell strong {
  color: #37352f;
  font-size: 13px;
  font-weight: 550;
}

.primary-cell span {
  overflow: hidden;
  color: #8b8a86;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.target-label {
  color: #4e5e64;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}

.target-label.missing {
  color: #b42318;
}

.row-actions {
  display: flex;
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(150px, 0.45fr);
  gap: 16px;
}

.el-form :deep(.el-select),
.el-form :deep(.el-input-number) {
  width: 100%;
}

.rule-editor :deep(textarea) {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
}

.rule-help {
  margin: -8px 0 14px;
  color: #8b8a86;
  font-size: 11px;
  line-height: 1.6;
}

.target-help {
  margin: -8px 0 14px;
  color: #8b8a86;
  font-size: 11px;
  line-height: 1.6;
}

@media (max-width: 900px) {
  .template-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .template-grid,
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
