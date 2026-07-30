<template>
  <div class="toast-stack" aria-live="polite" aria-atomic="false">
    <div v-for="toast in items" :key="toast.id" class="toast" :class="toast.tone">
      <span>{{ toast.message }}</span>
      <button type="button" :aria-label="dismissLabel" @click="$emit('dismiss', toast.id)">×</button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  dismissLabel: { type: String, default: 'Dismiss' },
})
defineEmits(['dismiss'])
</script>
