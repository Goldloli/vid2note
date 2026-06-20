export async function consumeEventStream(
  url: string,
  token: string | null,
  signal: AbortSignal,
  onData: (data: string) => void,
): Promise<void> {
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`SSE request failed (${response.status})`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (!signal.aborted) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      for (const line of block.split('\n')) {
        if (line.startsWith('data:')) onData(line.slice(5).trimStart())
      }
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
}
