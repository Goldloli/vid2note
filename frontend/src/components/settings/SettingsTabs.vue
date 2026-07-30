<template>
  <nav class="settings-tabs" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="(tab, index) in tabs"
      :id="`${idPrefix}-tab-${tab.id}`"
      :key="tab.id"
      class="settings-tab"
      :class="{ active: modelValue === tab.id }"
      type="button"
      role="tab"
      :aria-selected="modelValue === tab.id"
      :aria-controls="`${idPrefix}-panel-${tab.id}`"
      :tabindex="modelValue === tab.id ? 0 : -1"
      @click="$emit('update:modelValue', tab.id)"
      @keydown="onKeydown($event, index)"
    >
      <span>{{ tab.label }}</span>
      <small v-if="tab.description">{{ tab.description }}</small>
    </button>
  </nav>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: String, required: true },
  tabs: { type: Array, required: true },
  ariaLabel: { type: String, default: 'Settings sections' },
  idPrefix: { type: String, default: 'settings' },
})
const emit = defineEmits(['update:modelValue'])

function onKeydown(event, index) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  let next = index
  if (event.key === 'Home') next = 0
  if (event.key === 'End') next = props.tabs.length - 1
  if (event.key === 'ArrowLeft') next = (index - 1 + props.tabs.length) % props.tabs.length
  if (event.key === 'ArrowRight') next = (index + 1) % props.tabs.length
  const target = props.tabs[next]
  emit('update:modelValue', target.id)
  requestAnimationFrame(() => document.getElementById(`${props.idPrefix}-tab-${target.id}`)?.focus())
}
</script>
