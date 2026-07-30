<template>
  <div class="loading-state" aria-busy="true" :aria-label="label">
    <div v-for="row in rows" :key="row" class="skeleton-row" :class="{ short: row === rows }"></div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, default: '加载中' },
  rows: { type: Number, default: 4 },
})
</script>
