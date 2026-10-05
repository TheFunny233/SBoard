<script setup lang="ts">
import { Delete, Edit, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import type { Group, Tag } from '../types'

const loading = ref(false)
const groups = ref<Group[]>([])
const tags = ref<Tag[]>([])
const groupName = ref('')
const tagName = ref('')
const editOpen = ref(false)
const editType = ref<'group' | 'tag'>('group')
const editId = ref('')
const editName = ref('')
const editDescription = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[groups.value, tags.value] = await Promise.all([api.groups(), api.tags()])
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '无法加载分组和标签')
  } finally {
    loading.value = false
  }
}

async function addGroup(): Promise<void> {
  if (!groupName.value.trim()) return
  try {
    await api.createGroup({ name: groupName.value, description: null, sort_order: groups.value.length })
    groupName.value = ''
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '创建分组失败')
  }
}

async function addTag(): Promise<void> {
  if (!tagName.value.trim()) return
  try {
    await api.createTag({ name: tagName.value, color: '#e3e1db' })
    tagName.value = ''
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '创建标签失败')
  }
}

function openGroup(group: Group): void {
  editType.value = 'group'
  editId.value = group.id
  editName.value = group.name
  editDescription.value = group.description || ''
  editOpen.value = true
}

function openTag(tag: Tag): void {
  editType.value = 'tag'
  editId.value = tag.id
  editName.value = tag.name
  editDescription.value = ''
  editOpen.value = true
}

async function saveEdit(): Promise<void> {
  if (!editName.value.trim()) {
    ElMessage.warning('名称不能为空')
    return
  }
  try {
    if (editType.value === 'group') {
      await api.updateGroup(editId.value, {
        name: editName.value,
        description: editDescription.value || null,
      })
    } else {
      await api.updateTag(editId.value, { name: editName.value })
    }
    editOpen.value = false
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '保存失败')
  }
}

async function remove(type: 'group' | 'tag', item: Group | Tag): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除${type === 'group' ? '分组' : '标签'} ${item.name}？节点本身不会被删除。`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    if (type === 'group') await api.deleteGroup(item.id)
    else await api.deleteTag(item.id)
    await load()
  } catch (reason) {
    if (reason === 'cancel' || reason === 'close') return
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <PageHeader title="分组与标签" description="分组用于地域和订阅组织，标签用于轻量筛选与用途标记。" />

    <section class="taxonomy-grid">
      <div class="surface taxonomy-panel">
        <div class="panel-heading">
          <div>
            <h2 class="section-title">节点分组</h2>
            <p class="section-note">一个节点可以属于多个分组。</p>
          </div>
          <span>{{ groups.length }}</span>
        </div>
        <div class="quick-add">
          <el-input v-model="groupName" placeholder="新分组名称" @keyup.enter="addGroup" />
          <el-button :icon="Plus" aria-label="添加分组" @click="addGroup" />
        </div>
        <div class="item-list">
          <div v-for="group in groups" :key="group.id" class="item-row block-row">
            <span class="drag-handle" aria-hidden="true">⋮⋮</span>
            <div>
              <strong>{{ group.name }}</strong>
              <span>{{ group.description || '无说明' }}</span>
            </div>
            <el-button text :icon="Edit" aria-label="编辑分组" @click="openGroup(group)" />
            <el-button text :icon="Delete" aria-label="删除分组" @click="remove('group', group)" />
          </div>
          <div v-if="!groups.length" class="empty-row">还没有分组</div>
        </div>
      </div>

      <div class="surface taxonomy-panel">
        <div class="panel-heading">
          <div>
            <h2 class="section-title">节点标签</h2>
            <p class="section-note">例如流媒体、备用、家用。</p>
          </div>
          <span>{{ tags.length }}</span>
        </div>
        <div class="quick-add">
          <el-input v-model="tagName" placeholder="新标签名称" @keyup.enter="addTag" />
          <el-button :icon="Plus" aria-label="添加标签" @click="addTag" />
        </div>
        <div class="item-list">
          <div v-for="tag in tags" :key="tag.id" class="item-row tag-row block-row">
            <span class="drag-handle" aria-hidden="true">⋮⋮</span>
            <span class="tag-swatch" :style="{ backgroundColor: tag.color || '#e3e1db' }" aria-hidden="true" />
            <div><strong>{{ tag.name }}</strong></div>
            <el-button text :icon="Edit" aria-label="编辑标签" @click="openTag(tag)" />
            <el-button text :icon="Delete" aria-label="删除标签" @click="remove('tag', tag)" />
          </div>
          <div v-if="!tags.length" class="empty-row">还没有标签</div>
        </div>
      </div>
    </section>

    <el-dialog
      v-model="editOpen"
      :title="editType === 'group' ? '编辑分组' : '编辑标签'"
      width="min(480px, 92vw)"
    >
      <el-form label-position="top" @submit.prevent="saveEdit">
        <el-form-item label="名称">
          <el-input v-model="editName" @keyup.enter="saveEdit" />
        </el-form-item>
        <el-form-item v-if="editType === 'group'" label="说明">
          <el-input v-model="editDescription" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.taxonomy-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.taxonomy-panel {
  overflow: hidden;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid #ebeae7;
}

.panel-heading > span {
  color: #9b9a97;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}

.quick-add {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  padding: 12px;
  background: #faf9f7;
  border-bottom: 1px solid #ebeae7;
}

.item-list {
  padding: 6px 8px;
}

.item-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 32px 32px;
  align-items: center;
  gap: 6px;
  min-height: 54px;
  padding: 7px 6px;
  border-radius: 6px;
}

.item-row > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.item-row strong {
  overflow: hidden;
  color: #37352f;
  font-size: 13px;
  font-weight: 550;
  text-overflow: ellipsis;
}

.item-row div span {
  overflow: hidden;
  color: #8b8a86;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-row {
  grid-template-columns: 18px 12px minmax(0, 1fr) 32px 32px;
}

.tag-swatch {
  width: 10px;
  height: 10px;
  border: 1px solid rgb(55 53 47 / 10%);
  border-radius: 2px;
}

.empty-row {
  padding: 44px 20px;
  color: #9b9a97;
  font-size: 13px;
  text-align: center;
}

@media (max-width: 850px) {
  .taxonomy-grid {
    grid-template-columns: 1fr;
  }
}
</style>

