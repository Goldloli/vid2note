import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AgentEventStream from './AgentEventStream.vue'

describe('AgentEventStream', () => {
  it('renders normalized events without runtime-specific branches', () => {
    const events = [
      { run_id: 'run_1', sequence: 0, type: 'run.started', timestamp: '2026-06-19T00:00:00Z', payload: {} },
      { run_id: 'run_1', sequence: 1, type: 'message.delta', timestamp: '2026-06-19T00:00:01Z', payload: { text: 'answer' } },
    ] as const
    const wrapper = mount(AgentEventStream, { props: { events }, global: { stubs: ['RouterLink'] } })
    expect(wrapper.findAll('[data-agent-event]')).toHaveLength(2)
    expect(wrapper.html()).not.toContain('codex-event')
    expect(wrapper.html()).not.toContain('claude-event')
  })
})
