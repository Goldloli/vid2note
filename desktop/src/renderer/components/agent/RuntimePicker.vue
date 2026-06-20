<template><label class="runtime-picker">Runtime<select :value="modelValue" :disabled="locked" @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"><option v-for="runtime in runtimes" :key="runtime.id" :value="runtime.id" :disabled="!runtime.detection.available">{{ runtime.label }} · {{ runtime.detection.available ? runtime.detection.version : runtime.detection.reason ?? '不可用' }}</option></select></label></template>
<script setup lang="ts">
import type { Runtime } from '../../api/agents'
defineProps<{ runtimes: Runtime[]; modelValue: string; locked?: boolean }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
