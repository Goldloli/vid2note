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
    <label class="tree-search">
      <Search />
      <span class="sr-only">搜索知识库</span>
      <input type="search" placeholder="搜索页面和来源" disabled>
    </label>
    <nav aria-label="知识目录" class="tree-content">
      <div class="tree-item is-active"><Document />index.md</div>
      <div class="tree-item"><Folder />wiki</div>
      <div class="tree-item"><Folder />sources</div>
      <div class="tree-item is-muted"><Folder />raw</div>
      <div class="tree-item"><Document />log.md</div>
    </nav>
    <div class="tree-status"><span>待审批</span><b>0</b></div>
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
import { Document, Fold, Folder, Search } from '@element-plus/icons-vue'

import ResizablePane from './ResizablePane.vue'

defineProps<{ visible: boolean; width: number }>()
defineEmits<{ close: []; resize: [width: number] }>()
</script>
