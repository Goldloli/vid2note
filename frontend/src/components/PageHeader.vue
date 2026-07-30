<template>
  <header class="page-header">
    <div class="page-header-copy">
      <div v-if="icon" class="page-header-icon" aria-hidden="true">
        <AppIcon :name="icon" :size="20" weight="duotone" />
      </div>
      <div>
        <h1>{{ title }}</h1>
        <p v-if="subtitle">{{ subtitle }}</p>
        <slot name="meta" />
      </div>
    </div>
    <div v-if="$slots.actions" class="page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  icon: { type: String, default: '' },
})
</script>
