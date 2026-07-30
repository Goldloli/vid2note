<template>
  <div class="password-control">
    <div class="password-input-wrap">
      <input
        class="input password-input"
        :type="inputType"
        :value="displayValue"
        :readonly="!editing || revealed"
        :placeholder="placeholder"
        :aria-label="label"
        autocomplete="off"
        spellcheck="false"
        @input="onInput"
      >
      <button
        class="password-eye"
        type="button"
        :disabled="loading || (!configured && !modelValue)"
        :aria-label="revealed ? hideLabel : revealLabel"
        :title="revealed ? hideLabel : revealLabel"
        @click="$emit(revealed ? 'hide' : 'reveal')"
      >
        <svg v-if="revealed" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 3l18 18M10.6 10.7a2 2 0 002.7 2.7M9.9 4.2A10.7 10.7 0 0112 4c5.3 0 9 5 9 5a15 15 0 01-3 3.5M6.2 6.3C4.3 7.6 3 9 3 9s3.7 5 9 5c1 0 2-.2 2.9-.5"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true">
          <path d="M3 12s3.7-5 9-5 9 5 9 5-3.7 5-9 5-9-5-9-5z"/><circle cx="12" cy="12" r="2.5"/>
        </svg>
      </button>
    </div>
    <div class="password-actions">
      <button
        v-if="configured && !editing"
        class="text-button"
        type="button"
        @click="startReplace"
      >{{ replaceLabel }}</button>
      <button
        v-if="configured"
        class="text-button danger"
        type="button"
        @click="requestClear"
      >{{ confirmClear ? confirmClearLabel : clearLabel }}</button>
      <button
        v-if="editing && configured"
        class="text-button"
        type="button"
        @click="cancelReplace"
      >{{ cancelLabel }}</button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  configured: { type: Boolean, default: false },
  masked: { type: String, default: '' },
  revealed: { type: Boolean, default: false },
  revealedValue: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  label: { type: String, default: 'API Key' },
  placeholder: { type: String, default: '' },
  revealLabel: { type: String, default: 'Reveal' },
  hideLabel: { type: String, default: 'Hide' },
  replaceLabel: { type: String, default: 'Replace' },
  clearLabel: { type: String, default: 'Clear' },
  confirmClearLabel: { type: String, default: 'Confirm clear' },
  cancelLabel: { type: String, default: 'Cancel' },
})
const emit = defineEmits(['update:modelValue', 'reveal', 'hide', 'clear'])
const editing = ref(!props.configured)
const confirmClear = ref(false)
let clearTimer

const inputType = computed(() => (props.revealed ? 'text' : 'password'))
const displayValue = computed(() => {
  if (props.revealed) return props.revealedValue
  if (editing.value) return props.modelValue
  return props.masked
})

watch(() => props.configured, value => {
  if (!value) editing.value = true
})

function onInput(event) {
  if (editing.value && !props.revealed) emit('update:modelValue', event.target.value)
}
function startReplace() {
  emit('hide')
  editing.value = true
  emit('update:modelValue', '')
}
function cancelReplace() {
  editing.value = false
  emit('update:modelValue', '')
}
function requestClear() {
  if (confirmClear.value) {
    confirmClear.value = false
    clearTimeout(clearTimer)
    emit('clear')
    return
  }
  confirmClear.value = true
  clearTimer = setTimeout(() => { confirmClear.value = false }, 5000)
}
</script>
