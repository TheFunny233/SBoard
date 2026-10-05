<script setup lang="ts">
import { Check, DocumentChecked, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import type { Group, ImportResult, Tag } from '../types'

const content = ref('')
const groups = ref<Group[]>([])
const tags = ref<Tag[]>([])
const groupIds = ref<string[]>([])
const tagIds = ref<string[]>([])
const duplicatePolicy = ref<'skip' | 'create'>('skip')
const loading = ref(false)
const result = ref<ImportResult | null>(null)

const links = computed(() =>
  content.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean),
)

async function loadOptions(): Promise<void> {
  try {
    ;[groups.value, tags.value] = await Promise.all([api.groups(), api.tags()])
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法加载分组和标签')
  }
}

async function run(mode: 'preview' | 'commit'): Promise<void> {
  if (!links.value.length) {
    ElMessage.warning('请粘贴至少一个节点链接')
    return
  }
  loading.value = true
  try {
    result.value = await api.importNodes({
      mode,
      links: links.value,
      group_ids: groupIds.value,
      tag_ids: tagIds.value,
      duplicate_policy: duplicatePolicy.value,
      atomic: true,
    })
    if (mode === 'preview') ElMessage.success('解析完成，请检查结果')
    else if (result.value.created) ElMessage.success(`已导入 ${result.value.created} 个节点`)
    else ElMessage.info('没有创建新节点')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '导入失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadOptions)
</script>

<template>
  <div class="page">
    <PageHeader
      title="导入节点"
      description="粘贴分享链接，先预览规范化结果，再一次性写入数据库。不会访问远程订阅 URL。"
    >
      <el-button :icon="DocumentChecked" :loading="loading" @click="run('preview')">解析预览</el-button>
      <el-button type="primary" :icon="Upload" :loading="loading" @click="run('commit')">确认导入</el-button>
    </PageHeader>

    <section class="import-layout">
      <div class="surface editor-panel">
        <div class="panel-heading">
          <div>
            <h2 class="section-title">分享链接</h2>
            <p class="section-note">每行一个，支持 VLESS、VMess、Trojan、SS、Hysteria2 与 TUIC。</p>
          </div>
          <span>{{ links.length }} 条</span>
        </div>
        <el-input
          v-model="content"
          type="textarea"
          :rows="14"
          resize="vertical"
          spellcheck="false"
          placeholder="vless://...&#10;trojan://...&#10;ss://..."
        />
      </div>

      <aside class="surface options-panel">
        <h2 class="section-title">导入选项</h2>
        <el-form label-position="top">
          <el-form-item label="加入分组">
            <el-select v-model="groupIds" multiple clearable placeholder="不指定">
              <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="添加标签">
            <el-select v-model="tagIds" multiple clearable placeholder="不指定">
              <el-option v-for="tag in tags" :key="tag.id" :label="tag.name" :value="tag.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="遇到重复节点">
            <el-radio-group v-model="duplicatePolicy">
              <el-radio value="skip">跳过</el-radio>
              <el-radio value="create">仍然创建</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
        <div class="atomic-note">
          <el-icon><Check /></el-icon>
          <span>原子导入：任意链接解析失败时不会写入部分数据。</span>
        </div>
      </aside>
    </section>

    <section v-if="result" class="surface result-panel">
      <div class="result-heading">
        <div>
          <h2 class="section-title">{{ result.mode === 'preview' ? '解析预览' : '导入结果' }}</h2>
          <p class="section-note">
            共 {{ result.total }} 条，成功创建 {{ result.created }} 条，失败 {{ result.failed }} 条
          </p>
        </div>
      </div>
      <el-table :data="result.items" row-key="index">
        <el-table-column label="#" prop="index" width="58" />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <span class="result-status" :class="`is-${row.status}`">{{ row.status }}</span>
          </template>
        </el-table-column>
        <el-table-column label="名称" min-width="160">
          <template #default="{ row }">{{ row.node?.name || '—' }}</template>
        </el-table-column>
        <el-table-column label="协议" width="105">
          <template #default="{ row }">{{ row.node?.protocol || '—' }}</template>
        </el-table-column>
        <el-table-column label="地址" min-width="190">
          <template #default="{ row }">
            <span class="mono">{{ row.node ? `${row.node.address}:${row.node.port}` : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="220">
          <template #default="{ row }">
            <span :class="{ 'danger-text': row.error }">{{ row.error || row.warning || '可以导入' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.import-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(260px, 0.7fr);
  gap: 16px;
}

.editor-panel,
.options-panel {
  padding: 20px;
}

.panel-heading,
.result-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-heading > span {
  color: #9b9a97;
  font-size: 12px;
}

.editor-panel :deep(textarea) {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  line-height: 1.65;
}

.options-panel .section-title {
  margin-bottom: 18px;
}

.options-panel :deep(.el-select) {
  width: 100%;
}

.atomic-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  padding: 12px;
  color: #5f5e59;
  background: #f7f6f3;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.55;
}

.atomic-note .el-icon {
  margin-top: 2px;
  color: #0f7b6c;
}

.result-panel {
  margin-top: 16px;
  overflow: hidden;
}

.result-heading {
  margin: 0;
  padding: 18px 20px;
  border-bottom: 1px solid #ebeae7;
}

.result-status {
  color: #787774;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.result-status.is-created,
.result-status.is-valid {
  color: #0f7b6c;
}

.result-status.is-error {
  color: #b44949;
}

@media (max-width: 900px) {
  .import-layout {
    grid-template-columns: 1fr;
  }
}
</style>

