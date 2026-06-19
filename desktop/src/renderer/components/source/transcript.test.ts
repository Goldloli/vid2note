import { describe, expect, it } from 'vitest'
import { parseTranscript } from './transcript'

describe('parseTranscript', () => {
  it('reads stable ids and millisecond ranges from vault transcript markdown', () => {
    const markdown = '# Transcript\n\n## 00:12:41–00:13:28\n\nA claim ^seg-000142-deadbeef\n'
    expect(parseTranscript(markdown)).toEqual([
      { id: 'seg-000142-deadbeef', startMs: 761000, endMs: 808000, text: 'A claim' },
    ])
  })
})
