<template>
  <aside
    class="workspace-tree"
    data-testid="workspace-tree"
    aria-label="知识文件树"
    :aria-hidden="!visible"
    :class="{ 'is-hidden': !visible }"
    :style="{ width: `${width}px` }"
  >
    <div class="tree-heading">
      <strong>个人知识库</strong>
      <button type="button" aria-label="收起文件树" @click="$emit('close')"><Fold /></button>
    </div>
    <WikiSearch :results="vault.searchResults" @search="vault.search" @open="open" />
    <nav aria-label="知识目录" class="tree-content">
      <WikiTree :tree="vault.tree" :pending-count="changesets.pendingCount" :active-path="vault.currentPage?.path" @open="open" @review="router.push('/workspace/changesets')" />
    </nav>
    <ResizablePane
      :model-value="width"
      :min="220"
      :max="420"
      side="right"
      label="调整文件树宽度"
      @update:model-value="$emit('resize', $event)"
    />
  </aside>
</template>

<script setup lang="ts">
import { Fold } from '@element-plus/icons-vue'
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import WikiSearch from '../wiki/WikiSearch.vue'
import WikiTree from '../wiki/WikiTree.vue'
import ResizablePane from './ResizablePane.vue'
import { useChangeSetStore } from '../../stores/changesets'
import { useVaultStore } from '../../stores/vault'

defineProps<{ visible: boolean; width: number }>()
defineEmits<{ close: []; resize: [width: number] }>()
const router = useRouter()
const vault = useVaultStore()
const changesets = useChangeSetStore()
function open(path: string): void { void router.push({ path: '/workspace/wiki', query: { path } }) }
onMounted(() => { void vault.refreshTree(); void changesets.refresh() })
</script>
