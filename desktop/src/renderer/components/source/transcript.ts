import type { TranscriptSegment } from './SourceTimeline.vue'

const milliseconds = (timestamp: string): number => {
  const [clock, fraction = '0'] = timestamp.split('.')
  const [hours, minutes, seconds] = clock!.split(':').map(Number)
  return ((hours! * 3600 + minutes! * 60 + seconds!) * 1000) + Number(fraction.padEnd(3, '0'))
}

export function parseTranscript(content: string): TranscriptSegment[] {
  return [...content.matchAll(/^## (\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)–(\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)\n\n([^\n]+) \^(seg-[\w-]+)$/gm)]
    .map((match) => ({
      id: match[4]!,
      startMs: milliseconds(match[1]!),
      endMs: milliseconds(match[2]!),
      text: match[3]!,
    }))
}

export function findActiveSegment(
  segments: TranscriptSegment[],
  currentMs: number,
): TranscriptSegment | undefined {
  let low = 0
  let high = segments.length - 1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    const segment = segments[middle]!
    if (currentMs < segment.startMs) high = middle - 1
    else if (currentMs >= segment.endMs) low = middle + 1
    else return segment
  }
  return undefined
}
