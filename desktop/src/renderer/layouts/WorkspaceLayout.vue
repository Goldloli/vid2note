<template>
  <div class="workspace-layout">
    <ToolRail />
    <WorkspaceTree
      :visible="store.treeVisible"
      :width="store.treeWidth"
      @close="store.treeOpen = false"
      @resize="store.setTreeWidth"
    />
    <WorkspaceMain />
    <AgentPlaceholder
      :open="store.agentOpen"
      :drawer="store.agentDrawer"
      :width="store.agentWidth"
      :autonomy-label="store.autonomyLabel"
      :class="{ 'is-drawer': store.agentDrawer }"
      @close="store.agentOpen = false"
      @resize="store.setAgentWidth"
    />
  </div>
</template>

<script setup lang="ts">
import AgentPlaceholder from '../components/workspace/AgentPlaceholder.vue'
import ToolRail from '../components/workspace/ToolRail.vue'
import WorkspaceMain from '../components/workspace/WorkspaceMain.vue'
import WorkspaceTree from '../components/workspace/WorkspaceTree.vue'
import { useWorkspaceStore } from '../stores/workspace'

const store = useWorkspaceStore()
</script>
