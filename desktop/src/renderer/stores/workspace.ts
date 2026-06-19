import { computed, onMounted, onUnmounted, ref } from 'vue'
import { defineStore } from 'pinia'

import { getConfig } from '../api/config'

export type AutonomyMode = 'approval' | 'auto-revertible' | 'high-autonomy'

const readWidth = (key: string, fallback: number): number => {
  if (typeof localStorage === 'undefined') return fallback
  const stored = Number(localStorage.getItem(key))
  return Number.isFinite(stored) && stored > 0 ? stored : fallback
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value))

export const useWorkspaceStore = defineStore('workspace', () => {
  const initialViewportWidth = typeof window === 'undefined' ? 1440 : window.innerWidth
  const treeOpen = ref(initialViewportWidth >= 1100)
  const agentOpen = ref(true)
  const treeWidth = ref(readWidth('v2n-tree-width', 272))
  const agentWidth = ref(readWidth('v2n-agent-width', 380))
  const autonomyMode = ref<AutonomyMode>('approval')
  const autonomyLabel = computed(() => ({
    approval: 'A · 审批',
    'auto-revertible': 'B · 可回滚自治',
    'high-autonomy': 'C · 高自治',
  })[autonomyMode.value])
  const viewportWidth = ref(initialViewportWidth)

  const treeVisible = computed(() => treeOpen.value)
  const agentDrawer = computed(() => viewportWidth.value < 850)

  function setViewportWidth(width: number): void {
    if (viewportWidth.value >= 1100 && width < 1100) treeOpen.value = false
    viewportWidth.value = width
  }

  function setTreeWidth(width: number): void {
    treeWidth.value = clamp(width, 220, 420)
    localStorage.setItem('v2n-tree-width', String(treeWidth.value))
  }

  function setAgentWidth(width: number): void {
    agentWidth.value = clamp(width, 320, 560)
    localStorage.setItem('v2n-agent-width', String(agentWidth.value))
  }

  function toggleTree(): void {
    treeOpen.value = !treeOpen.value
  }

  function toggleAgent(): void {
    agentOpen.value = !agentOpen.value
  }

  function updateViewport(): void {
    setViewportWidth(window.innerWidth)
  }

  async function loadAutonomyMode(): Promise<void> {
    try {
      const config = await getConfig()
      const mode = config.autonomy_mode
      if (mode === 'approval' || mode === 'auto-revertible' || mode === 'high-autonomy') {
        autonomyMode.value = mode
      }
    } catch {
      autonomyMode.value = 'approval'
    }
  }

  onMounted(() => {
    window.addEventListener('resize', updateViewport)
    void loadAutonomyMode()
  })
  onUnmounted(() => window.removeEventListener('resize', updateViewport))

  return {
    treeOpen,
    agentOpen,
    treeWidth,
    agentWidth,
    autonomyMode,
    autonomyLabel,
    viewportWidth,
    treeVisible,
    agentDrawer,
    setViewportWidth,
    setTreeWidth,
    setAgentWidth,
    toggleTree,
    toggleAgent,
    loadAutonomyMode,
  }
})
