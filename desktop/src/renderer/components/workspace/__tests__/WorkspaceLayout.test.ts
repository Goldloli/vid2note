import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkspaceLayout from '../../../layouts/WorkspaceLayout.vue'
import { useWorkspaceStore } from '../../../stores/workspace'

const { getConfig } = vi.hoisted(() => ({ getConfig: vi.fn() }))
vi.mock('../../../api/config', () => ({ getConfig }))

describe('WorkspaceLayout', () => {
  beforeEach(() => {
    getConfig.mockReset()
    getConfig.mockResolvedValue({ autonomy_mode: 'approval' })
  })

  it('collapses tree below 1100 and opens agent as drawer below 850', async () => {
    const pinia = createPinia()
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div>content</div>' } }],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(WorkspaceLayout, { global: { plugins: [pinia, router] } })
    useWorkspaceStore(pinia).setViewportWidth(820)
    await nextTick()

    expect(wrapper.get('[data-testid="workspace-tree"]').attributes('aria-hidden')).toBe('true')
    expect(wrapper.get('[data-testid="agent-panel"]').classes()).toContain('is-drawer')
    expect(wrapper.text()).toContain('A · 审批')

    useWorkspaceStore(pinia).toggleTree()
    await nextTick()
    expect(wrapper.get('[data-testid="workspace-tree"]').attributes('aria-hidden')).toBe('false')
  })

  it('shows the backend autonomy mode in the toolbar and agent panel', async () => {
    getConfig.mockResolvedValue({ autonomy_mode: 'high-autonomy' })
    const pinia = createPinia()
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div>content</div>' } }],
    })
    await router.push('/')
    await router.isReady()

    const wrapper = mount(WorkspaceLayout, { global: { plugins: [pinia, router] } })
    await vi.waitFor(() => expect(wrapper.text().match(/C · 高自治/g)).toHaveLength(2))
    expect(getConfig).toHaveBeenCalledOnce()
  })
})
