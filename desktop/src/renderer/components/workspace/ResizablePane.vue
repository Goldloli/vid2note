<template>
  <div
    class="resize-handle"
    :class="`is-${side}`"
    role="separator"
    :aria-label="label"
    aria-orientation="vertical"
    :aria-valuenow="modelValue"
    :aria-valuemin="min"
    :aria-valuemax="max"
    tabindex="0"
    @pointerdown="startResize"
    @keydown.left.prevent="resizeBy(-10)"
    @keydown.right.prevent="resizeBy(10)"
  />
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: number
    min: number
    max: number
    side?: 'left' | 'right'
    label?: string
  }>(),
  { side: 'right', label: '调整面板宽度' },
)

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const resizeBy = (delta: number): void => {
  const direction = props.side === 'left' ? -1 : 1
  emit('update:modelValue', Math.min(props.max, Math.max(props.min, props.modelValue + delta * direction)))
}

const startResize = (event: PointerEvent): void => {
  const originX = event.clientX
  const originWidth = props.modelValue
  const direction = props.side === 'left' ? -1 : 1
  const move = (moveEvent: PointerEvent): void => {
    const width = originWidth + (moveEvent.clientX - originX) * direction
    emit('update:modelValue', Math.min(props.max, Math.max(props.min, width)))
  }
  const stop = (): void => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop, { once: true })
}
</script>
