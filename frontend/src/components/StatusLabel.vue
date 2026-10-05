<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    status: string
    text?: string
  }>(),
  { text: '' },
)

const labels: Record<string, string> = {
  online: '在线',
  offline: '离线',
  unknown: '未知',
  running: '运行中',
  stopped: '已停止',
  error: '异常',
}
</script>

<template>
  <span class="status-label" :class="`is-${props.status}`">
    <span class="status-dot" aria-hidden="true" />
    {{ props.text || labels[props.status] }}
  </span>
</template>

<style scoped>
.status-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #787774;
  font-size: 13px;
  white-space: nowrap;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  background: #a7a6a2;
}

.is-online,
.is-running {
  color: #0f6d61;
}

.is-online .status-dot,
.is-running .status-dot {
  background: #0f7b6c;
}

.is-offline,
.is-error {
  color: #b44949;
}

.is-offline .status-dot,
.is-error .status-dot {
  background: #c94c4c;
}

.is-stopped .status-dot {
  background: #9b7b38;
}
</style>
