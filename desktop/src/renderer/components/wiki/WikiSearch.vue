<template>
  <div class="wiki-search">
    <label class="tree-search"><Search /><span class="sr-only">搜索知识库</span><input v-model="query" type="search" placeholder="搜索页面和来源"></label>
    <div v-if="results.length" class="search-results" role="listbox">
      <button v-for="result in results" :key="result.path" type="button" role="option" @click="$emit('open', result.path)">
        <strong>{{ result.title }}</strong><small>{{ result.path }}</small><span>{{ result.snippet }}</span>
      </button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { Search } from '@element-plus/icons-vue'
import { ref, watch } from 'vue'
import type { VaultSearchResult } from '../../api/vault'
const props = defineProps<{ results: VaultSearchResult[] }>()
const emit = defineEmits<{ search: [query: string]; open: [path: string] }>()
const query = ref('')
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, (value) => { clearTimeout(timer); timer = setTimeout(() => emit('search', value), 300) })
void props
</script>
