import { describe, expect, it } from 'vitest'

import { toApiError } from '../errors'

describe('toApiError', () => {
  it('preserves ErrorEnvelope fields', () => {
    const envelope = {
      code: 'DOWNLOAD_TIMEOUT',
      message: 'timed out',
      user_message: '下载超时',
      retryable: true,
      component: 'download',
      operation: '/process/start',
    }

    const error = toApiError({ response: { data: { error: envelope } } })

    expect(error.code).toBe('DOWNLOAD_TIMEOUT')
    expect(error.retryable).toBe(true)
    expect(error.message).toBe('下载超时')
  })

  it('uses a safe fallback for unknown failures', () => {
    const error = toApiError(new Error('socket internals'))

    expect(error.code).toBe('NETWORK_ERROR')
    expect(error.message).toBe('网络连接失败，请稍后重试')
  })
})
