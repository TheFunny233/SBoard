<script setup lang="ts">
import { Check, Delete, Edit, Plus, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { api } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import type { Group, NodeRecord, RuleSet, RuleSetPayload, RuleTargetMode, RuleTemplate } from '../types'

const templates = ref<RuleTemplate[]>([])
const defaultsOpen = ref(false)
const defaultsSaving = ref(false)
const defaultTargets = ref({ ai_group_id: '', bulk_group_id: '' })

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
const defaultTemplates = computed(() => templates.value.filter((template) => template.apply_by_default))
const suggestedTargets = computed(() => ({
  ai_group_id: suggestedGroup('ai'),
  bulk_group_id: suggestedGroup('bulk'),
}))

function suggestedGroup(role: 'ai' | 'bulk'): string {
  const keys = role === 'ai' ? ['ai'] : ['static', 'nsfw', 'bulk']
  const names = templates.value.filter((template) => keys.includes(template.key)).map((template) => template.name)
  const currentTargets = new Set(rules.value
    .filter((rule) => names.includes(rule.name) && rule.target_mode === 'group' && groups.value.some((group) => group.id === rule.group_id))
    .map((rule) => rule.group_id as string))
  // Keep an existing consistent mapping; conflicting targets require a choice.
  if (currentTargets.size) return currentTargets.size === 1 ? [...currentTargets][0]! : ''
  const aliases = role === 'ai'
    ? ['ai', 'ai组', 'ai高纯净度', '高纯净度', '人工智能']
    : ['大流量', '大流量组', 'bulk', 'bulk组', '通用', '通用代理']
  const exact = groups.value.filter((group) => aliases.includes(group.name.toLowerCase().replace(/\s+/g, '')))
  const matches = exact.length ? exact : groups.value.filter((group) => role === 'ai'
    ? /(^|[^a-z])ai([^a-z]|$)|纯净|人工智能/i.test(group.name)
    : /大流量|(^|[^a-z])bulk([^a-z]|$)|通用/i.test(group.name))
  return matches.length === 1 ? matches[0]!.id : ''
}

function groupName(id: string): string {
  return groups.value.find((group) => group.id === id)?.name || '待选择节点组'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [ruleList, nodePage, groupList, templateList] = await Promise.all([
      api.rules(),
      api.nodes({ page_size: 500 }),
      api.groups(),
      api.ruleTemplates(),
    ])
    rules.value = ruleList
    nodes.value = nodePage.items
    groups.value = groupList
    templates.value = templateList
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
    target_mode: template?.target_mode || 'node',
    sort_order: template?.sort_order || 0,
  }
  if (template?.target_mode === 'group' && template.apply_by_default) {
    form.value.group_id = suggestedGroup(template.key === 'ai' ? 'ai' : 'bulk') || null
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

function openDefaults(): void {
  defaultTargets.value = { ...suggestedTargets.value }
  defaultsOpen.value = true
}

async function applyRecommended(): Promise<void> {
  if (loading.value || defaultsSaving.value) return
  const targets = suggestedTargets.value
  if (!targets.ai_group_id || !targets.bulk_group_id || targets.ai_group_id === targets.bulk_group_id) {
    openDefaults()
    return
  }
  defaultTargets.value = { ...targets }
  await applyDefaults()
}

async function applyDefaults(): Promise<void> {
  if (defaultsSaving.value) return
  if (!defaultTargets.value.ai_group_id || !defaultTargets.value.bulk_group_id) {
    ElMessage.warning('请选择 AI 组和大流量组')
    return
  }
  defaultsSaving.value = true
  try {
    await api.applyDefaultRules(defaultTargets.value)
    defaultsOpen.value = false
    ElMessage.success('推荐规则已应用；请刷新客户端订阅')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '应用默认分流失败')
  } finally {
    defaultsSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="规则" description="为 Clash Meta 订阅设置按站点分流的目标节点或节点组。">
      <el-button :icon="Plus" @click="openCreate()">添加规则</el-button>
      <el-button :icon="Refresh" @click="load">刷新</el-button>
    </PageHeader>

    <section class="surface recommended-section">
      <div>
        <h2>推荐分流 · 一键配置</h2>
        <p>按 Geosite 分类分流，并保留具体域名补漏。更新 {{ defaultTemplates.length || 6 }} 个内置预设，保留其他自定义规则。</p>
      </div>
      <div class="routing-summary">
        <span>AI → <strong>{{ groupName(suggestedTargets.ai_group_id) }}</strong></span>
        <span>Static / NSFW / 娱乐 → <strong>{{ groupName(suggestedTargets.bulk_group_id) }}</strong></span>
        <span>大陆 / 局域网 → <strong>直连</strong></span>
      </div>
      <div class="recommended-actions">
        <el-button type="primary" :icon="Check" :loading="defaultsSaving" :disabled="loading" @click="applyRecommended">
          一键应用推荐规则
        </el-button>
        <el-button :disabled="loading || defaultsSaving" @click="openDefaults">选择目标组</el-button>
      </div>
      <p>优先沿用已有规则的目标组；无法明确识别时会让你选择。应用后刷新客户端订阅生效。</p>
      <p v-if="!loading && !groups.length">
        还没有节点组，请先在 <router-link to="/taxonomy">分组与标签</router-link> 创建，并在 <router-link to="/nodes">节点</router-link> 中分配成员。
      </p>
    </section>

    <section class="surface template-section">
      <div class="section-heading">
        <div>
          <h2>常用场景</h2>
          <p>Geosite 分类覆盖 + 域名补漏：AI 走专用组，Static、NSFW 与娱乐走大流量组，大陆直连。</p>
        </div>
      </div>
      <div class="template-grid">
        <button
          v-for="template in templates"
          :key="template.name"
          class="template-card"
          type="button"
          :title="template.description"
          @click="openCreate(template)"
        >
          <span>{{ template.category }} · {{ template.apply_by_default ? '默认预设' : '可选，单独添加' }}</span>
          <strong>{{ template.name }}</strong>
          <small>{{ template.rules.length }} 条规则</small>
          <small class="geosite-label">{{ template.rules.filter((rule) => rule.startsWith('GEOSITE,')).map((rule) => rule.slice(8)).join(' / ') }}</small>
        </button>
      </div>
      <p class="geosite-help">
        Clash Meta 订阅会指定完整 Geosite 数据源并每天更新。若客户端提示分类不存在，请更新客户端 Geo 数据；已有规则可用「一键应用推荐规则」升级。游戏、Crypto、广告拦截模板按需单独添加。
      </p>
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
      <EmptyState v-else title="还没有分流规则" description="点击上方「一键应用推荐规则」快速配置，也可以单独添加站点规则。">
        <el-button @click="openCreate()">手动添加规则</el-button>
      </EmptyState>
    </div>

    <el-dialog v-model="defaultsOpen" title="选择推荐规则的目标组" width="min(540px, 94vw)">
      <el-form label-position="top" @submit.prevent="applyDefaults">
        <p v-if="!groups.length" class="geosite-help">请先在 <router-link to="/taxonomy" @click="defaultsOpen = false">分组与标签</router-link> 创建 AI 和大流量组，再到节点页分配成员。</p>
        <el-form-item label="AI 专用节点组" required>
          <el-select v-model="defaultTargets.ai_group_id" placeholder="选择 AI 组">
            <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="大流量节点组" required>
          <el-select v-model="defaultTargets.bulk_group_id" placeholder="选择大流量组">
            <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
          </el-select>
        </el-form-item>
        <p class="target-help">会创建或更新内置预设（含同名旧版预设），保留其他自定义规则。请先在「节点」中分配成员，在「分组与标签」中设置各组的测速策略。</p>
        <ul class="default-summary">
          <li v-for="preset in defaultTemplates" :key="preset.key">
            {{ preset.name }} → {{ preset.target_mode === 'direct' ? '直连' : preset.key === 'ai' ? 'AI 组' : '大流量组' }}（{{ preset.rules.length }} 条）
          </li>
        </ul>
      </el-form>
      <template #footer>
        <el-button @click="defaultsOpen = false">取消</el-button>
        <el-button type="primary" :loading="defaultsSaving" :disabled="!defaultTargets.ai_group_id || !defaultTargets.bulk_group_id" @click="applyDefaults">应用推荐规则</el-button>
      </template>
    </el-dialog>

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
          节点组在「分组与标签」中维护，可独立设置自动测速；订阅只会写入该组内已启用且被订阅包含的节点。
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
.recommended-section {
  margin-bottom: 16px;
  padding: 20px;
}

.recommended-section h2 {
  margin: 0;
  color: #37352f;
  font-size: 17px;
}

.recommended-section p {
  margin: 8px 0 0;
  color: #787774;
  font-size: 12px;
  line-height: 1.7;
}

.routing-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 16px 0;
  color: #787774;
  font-size: 12px;
}

.routing-summary strong {
  color: #37352f;
  font-weight: 550;
}

.recommended-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.recommended-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.default-summary {
  color: #787774;
  font-size: 13px;
  line-height: 1.9;
  padding-left: 20px;
}

.geosite-help {
  margin: 12px 0 0;
  color: #787774;
  font-size: 12px;
  line-height: 1.7;
}

.geosite-label {
  overflow-wrap: anywhere;
}

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
