<template>
  <span class="config-status" :class="tone">
    <i aria-hidden="true"></i>
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup>
defineProps({
  tone: { type: String, default: 'neutral' },
  label: { type: String, default: '' },
})
</script>
