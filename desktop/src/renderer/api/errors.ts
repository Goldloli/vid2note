import type { components } from './generated/schema'

export type ErrorEnvelope = components['schemas']['ErrorEnvelope']

export class ApiError extends Error {
  constructor(public readonly envelope: ErrorEnvelope) {
    super(envelope.user_message)
    this.name = 'ApiError'
  }

  get code(): string {
    return this.envelope.code
  }

  get retryable(): boolean {
    return this.envelope.retryable
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isEnvelope(value: unknown): value is ErrorEnvelope {
  if (!isRecord(value)) return false
  return (
    typeof value.code === 'string' &&
    typeof value.message === 'string' &&
    typeof value.user_message === 'string' &&
    typeof value.retryable === 'boolean' &&
    typeof value.component === 'string' &&
    typeof value.operation === 'string'
  )
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error

  if (isRecord(error) && isRecord(error.response) && isRecord(error.response.data)) {
    const envelope = error.response.data.error
    if (isEnvelope(envelope)) return new ApiError(envelope)
  }

  return new ApiError({
    code: 'NETWORK_ERROR',
    message: 'Network request failed',
    user_message: '网络连接失败，请稍后重试',
    retryable: true,
    component: 'renderer',
    operation: 'request',
  })
}
