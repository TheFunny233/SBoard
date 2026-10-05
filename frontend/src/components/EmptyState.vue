<script setup lang="ts">
defineProps<{ title: string; description: string }>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon" aria-hidden="true">□</div>
    <strong>{{ title }}</strong>
    <p>{{ description }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  min-height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px;
  color: #787774;
  text-align: center;
}

.empty-icon {
  margin-bottom: 12px;
  color: #aaa8a3;
  font-size: 28px;
}

strong {
  color: #37352f;
  font-size: 15px;
}

p {
  max-width: 440px;
  margin: 7px 0 16px;
  font-size: 13px;
  line-height: 1.65;
}
</style>

