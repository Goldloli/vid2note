<template>
  <label class="setting-field">
    <span class="setting-field-copy">
      <strong>{{ label }}</strong>
      <small v-if="hint">{{ hint }}</small>
    </span>
    <span class="setting-field-control"><slot /></span>
  </label>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  hint: { type: String, default: '' },
})
</script>
