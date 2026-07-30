<template>
  <button
    class="setting-switch"
    :class="{ active: modelValue }"
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="label"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <span aria-hidden="true"></span>
  </button>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, required: true },
  label: { type: String, required: true },
})
defineEmits(['update:modelValue'])
</script>
