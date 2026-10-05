<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <header class="page-header">
    <h1>{{ title }}</h1>
    <p>{{ description }}</p>
    <div v-if="$slots.default" class="page-toolbar">
      <slot />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  margin-bottom: 28px;
}

h1 {
  margin: 0;
  color: #37352f;
  font-size: clamp(28px, 4vw, 38px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

p {
  max-width: 720px;
  margin: 10px 0 0;
  color: #787774;
  font-size: 14px;
  line-height: 1.7;
}
</style>

