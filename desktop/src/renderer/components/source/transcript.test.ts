import { describe, expect, it } from 'vitest'
import { findActiveSegment, parseTranscript } from './transcript'

describe('parseTranscript', () => {
  it('reads stable ids and millisecond ranges from vault transcript markdown', () => {
    const markdown = '# Transcript\n\n## 00:12:41–00:13:28\n\nA claim ^seg-000142-deadbeef\n'
    expect(parseTranscript(markdown)).toEqual([
      { id: 'seg-000142-deadbeef', startMs: 761000, endMs: 808000, text: 'A claim' },
    ])
  })

  it('finds the active segment in an ordered long transcript', () => {
    const segments = Array.from({ length: 10_000 }, (_, index) => ({
      id: `seg-${index}`,
      startMs: index * 1000,
      endMs: (index + 1) * 1000,
      text: String(index),
    }))

    expect(findActiveSegment(segments, 8_765_432)?.id).toBe('seg-8765')
    expect(findActiveSegment(segments, 10_000_000)).toBeUndefined()
  })
})
