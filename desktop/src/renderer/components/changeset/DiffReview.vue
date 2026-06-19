<template>
  <section class="diff-review">
    <article v-for="(operation, index) in changeset.operations" :key="operation.path" :data-operation-index="index">
      <label><input v-model="selected" type="checkbox" :value="index">{{ operation.action }} · {{ operation.path }}</label>
      <div class="diff-columns"><pre>{{ operation.before ?? '新页面' }}</pre><pre>{{ operation.after }}</pre></div>
      <p>{{ operation.rationale }}</p>
    </article>
    <button data-testid="approve-selected" type="button" :disabled="blocked || !valid || !selected.length" @click="$emit('approve', selected)">批准所选变更</button>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
type Operation = { path: string; action: string; before?: string | null; after: string; rationale: string }
type ReviewChangeSet = { operations: readonly Operation[]; validation_result?: { valid: boolean } | null }
const props = withDefaults(defineProps<{ changeset: ReviewChangeSet; blocked?: boolean }>(), { blocked: false })
defineEmits<{ approve: [indexes: number[]] }>()
const selected = ref(props.changeset.operations.map((_operation, index) => index))
const valid = computed(() => props.changeset.validation_result?.valid !== false)
</script>
