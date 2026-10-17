<script setup lang="ts">
import type { GroupPolicy } from '../types'

const policy = defineModel<GroupPolicy>({ required: true })
</script>

<template>
  <el-form-item label="节点选择策略">
    <el-select v-model="policy.strategy" style="width: 100%">
      <el-option label="手动选择" value="select" />
      <el-option label="自动测速（最低延迟）" value="url-test" />
      <el-option label="故障转移（按节点顺序）" value="fallback" />
    </el-select>
  </el-form-item>
  <template v-if="policy.strategy !== 'select'">
    <el-form-item label="测速地址">
      <el-input v-model="policy.test_url" placeholder="https://www.gstatic.com/generate_204" />
    </el-form-item>
    <el-form-item label="测速间隔（秒）">
      <el-input-number v-model="policy.test_interval" :min="30" :max="86400" />
    </el-form-item>
    <el-form-item v-if="policy.strategy === 'url-test'" label="切换容差（毫秒）">
      <el-input-number v-model="policy.test_tolerance" :min="0" :max="1000" />
    </el-form-item>
  </template>
  <p class="policy-help">
    每组仅使用自己的已启用成员。保存后刷新 Clash Meta 订阅生效；客户端按连接延迟测速，不代表下载带宽或站点解锁能力。
  </p>
</template>

<style scoped>
.policy-help {
  color: #8b8a86;
  font-size: 12px;
  line-height: 1.7;
}
</style>
