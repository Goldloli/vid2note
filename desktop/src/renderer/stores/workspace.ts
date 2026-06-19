import { computed, onMounted, onUnmounted, ref } from 'vue'
import { defineStore } from 'pinia'

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

  onMounted(() => window.addEventListener('resize', updateViewport))
  onUnmounted(() => window.removeEventListener('resize', updateViewport))

  return {
    treeOpen,
    agentOpen,
    treeWidth,
    agentWidth,
    autonomyMode,
    viewportWidth,
    treeVisible,
    agentDrawer,
    setViewportWidth,
    setTreeWidth,
    setAgentWidth,
    toggleTree,
    toggleAgent,
  }
})
