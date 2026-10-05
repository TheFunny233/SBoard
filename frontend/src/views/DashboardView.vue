<script setup lang="ts">
import { Connection, Link, Tickets, Warning } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { api } from '../api'
import PageHeader from '../components/PageHeader.vue'
import StatusLabel from '../components/StatusLabel.vue'
import type { Agent, Overview } from '../types'
import { formatBytes, formatDate } from '../utils'

const loading = ref(true)
const error = ref('')
const overview = ref<Overview | null>(null)
const agents = ref<Agent[]>([])

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [summary, agentPage] = await Promise.all([
      api.overview(),
      api.agents({ page: 1, page_size: 6 }),
    ])
    overview.value = summary
    agents.value = agentPage.items
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法加载概览'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page" v-loading="loading">
    <PageHeader title="概览" description="查看边缘主机、代理节点与订阅的当前状态。">
      <el-button @click="load">刷新</el-button>
      <el-button type="primary" @click="$router.push('/nodes')">管理节点</el-button>
    </PageHeader>

    <el-alert v-if="error" :title="error" type="warning" :closable="false" show-icon class="notice" />

    <template v-if="overview">
      <section class="metrics" aria-label="核心指标">
        <article class="metric surface block-row">
          <span class="drag-handle" aria-hidden="true">⋮⋮</span>
          <el-icon><Connection /></el-icon>
          <div>
            <strong>{{ overview.agents_online }} / {{ overview.agents_total }}</strong>
            <span>边缘主机在线</span>
          </div>
        </article>
        <article class="metric surface block-row">
          <span class="drag-handle" aria-hidden="true">⋮⋮</span>
          <el-icon><Link /></el-icon>
          <div>
            <strong>{{ overview.managed_nodes + overview.external_nodes }}</strong>
            <span>可管理节点</span>
          </div>
        </article>
        <article class="metric surface block-row">
          <span class="drag-handle" aria-hidden="true">⋮⋮</span>
          <el-icon><Tickets /></el-icon>
          <div>
            <strong>{{ overview.subscriptions }}</strong>
            <span>统一订阅</span>
          </div>
        </article>
        <article class="metric surface block-row">
          <span class="drag-handle" aria-hidden="true">⋮⋮</span>
          <el-icon><Warning /></el-icon>
          <div>
            <strong>{{ overview.agents_offline }}</strong>
            <span>离线主机</span>
          </div>
        </article>
      </section>

      <section class="content-grid">
        <div class="surface section-panel">
          <div class="section-heading">
            <div>
              <h2 class="section-title">边缘主机</h2>
              <p class="section-note">最近登记的主机与资源状态</p>
            </div>
            <RouterLink to="/agents" class="subtle-link">查看全部</RouterLink>
          </div>
          <div v-if="agents.length" class="agent-list">
            <div v-for="agent in agents" :key="agent.id" class="agent-row block-row">
              <span class="drag-handle" aria-hidden="true">⋮⋮</span>
              <div class="agent-main">
                <strong>{{ agent.name }}</strong>
                <span>{{ agent.last_ip || '尚无连接地址' }} · {{ formatDate(agent.last_seen_at) }}</span>
              </div>
              <div class="agent-memory desktop-only">
                {{ formatBytes(agent.memory_used_bytes) }} / {{ formatBytes(agent.memory_total_bytes) }}
              </div>
              <StatusLabel :status="agent.online ? 'online' : 'offline'" />
            </div>
          </div>
          <div v-else class="small-empty">还没有边缘主机</div>
        </div>

        <div class="surface section-panel protocol-panel">
          <div class="section-heading">
            <div>
              <h2 class="section-title">协议分布</h2>
              <p class="section-note">当前启用模型中的节点协议</p>
            </div>
          </div>
          <div v-if="Object.keys(overview.nodes_by_protocol).length" class="protocol-list">
            <div v-for="(count, protocol) in overview.nodes_by_protocol" :key="protocol" class="protocol-row">
              <span>{{ protocol }}</span>
              <strong>{{ count }}</strong>
            </div>
          </div>
          <div v-else class="small-empty">尚未添加节点</div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.notice {
  margin-bottom: 20px;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 26px;
}

.metric {
  display: flex;
  min-height: 112px;
  align-items: flex-start;
  gap: 13px;
  padding: 20px 18px;
}

.metric > .drag-handle {
  position: absolute;
  top: 12px;
  left: 2px;
}

.metric > .el-icon {
  margin-top: 3px;
  color: #787774;
  font-size: 19px;
}

.metric div {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.metric strong {
  color: #37352f;
  font-size: 25px;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.metric span:last-child {
  color: #787774;
  font-size: 12px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(240px, 0.8fr);
  gap: 16px;
}

.section-panel {
  overflow: hidden;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid #ebeae7;
}

.section-heading a {
  font-size: 13px;
}

.agent-list {
  padding: 6px 8px;
}

.agent-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto 72px;
  align-items: center;
  gap: 10px;
  min-height: 58px;
  padding: 8px 10px;
  border-radius: 6px;
}

.agent-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.agent-main strong {
  overflow: hidden;
  font-size: 13px;
  font-weight: 550;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-main span,
.agent-memory {
  color: #8b8a86;
  font-size: 11px;
}

.agent-memory {
  font-family: "SFMono-Regular", Consolas, monospace;
}

.protocol-list {
  padding: 9px 12px 14px;
}

.protocol-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 8px;
  border-bottom: 1px solid #f0efec;
  font-size: 13px;
}

.protocol-row:last-child {
  border-bottom: 0;
}

.protocol-row span {
  color: #5f5e59;
}

.protocol-row strong {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 500;
}

.small-empty {
  padding: 48px 20px;
  color: #9b9a97;
  font-size: 13px;
  text-align: center;
}

@media (max-width: 1040px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .metrics {
    grid-template-columns: 1fr;
  }

  .metric {
    min-height: 92px;
  }

  .agent-row {
    grid-template-columns: 12px minmax(0, 1fr) auto;
  }
}
</style>

