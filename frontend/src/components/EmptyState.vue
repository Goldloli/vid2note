<template>
  <div class="empty-state" :class="`empty-state-${tone}`">
    <div class="empty-state-icon" aria-hidden="true">
      <AppIcon :name="icon" :size="24" weight="duotone" />
    </div>
    <strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
    <div v-if="$slots.actions" class="empty-state-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
import AppIcon from '@/components/AppIcon.vue'

defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: String, default: 'tray' },
  tone: { type: String, default: 'neutral' },
})
</script>
