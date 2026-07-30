<template>
  <div class="section-header">
    <div>
      <div class="section-header-title">
        <h2>{{ title }}</h2>
        <span v-if="count !== null && count !== undefined" class="section-count">{{ count }}</span>
      </div>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="section-header-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  count: { type: [Number, String], default: null },
})
</script>
