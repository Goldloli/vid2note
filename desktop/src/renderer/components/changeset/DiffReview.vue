<template>
  <section class="diff-review">
    <article v-for="(operation, index) in changeset.operations" :key="`${changeset.id ?? ''}:${operation.path}`" :data-operation-index="index">
      <label><input v-model="selected" type="checkbox" :value="index">{{ actionLabel(operation.action) }} · {{ operation.path }}</label>
      <OperationDiff :before="operation.before ?? ''" :after="operation.after" />
      <p>{{ operation.rationale }}</p>
    </article>
    <button data-testid="approve-selected" type="button" :disabled="blocked || !valid || !selected.length" @click="$emit('approve', selected)">批准所选变更</button>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import OperationDiff from './OperationDiff.vue'
type Operation = { path: string; action: string; before?: string | null; after: string; rationale: string }
type ReviewChangeSet = { id?: string; operations: readonly Operation[]; validation_result?: { valid: boolean } | null }
const props = withDefaults(defineProps<{ changeset: ReviewChangeSet; blocked?: boolean }>(), { blocked: false })
defineEmits<{ approve: [indexes: number[]] }>()
const selected = ref(props.changeset.operations.map((_operation, index) => index))
const valid = computed(() => props.changeset.validation_result?.valid !== false)
const actionLabel = (action: string): string => ({ create: '创建', update: '更新', rename: '重命名', delete: '删除' })[action] ?? action
watch(() => props.changeset, (changeset) => { selected.value = changeset.operations.map((_operation, index) => index) })
</script>
