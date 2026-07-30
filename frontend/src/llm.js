export const LLM_PROVIDERS = [
  'deepseek',
  'qwen',
  'glm',
  'moonshot',
  'minimax',
  'doubao',
  'baidu',
  'ollama',
  'custom',
]

export const DEFAULT_LLM_MODELS = {
  deepseek: 'deepseek-v4-flash',
  qwen: 'qwen3.7-plus',
  glm: 'glm-5.2',
  moonshot: 'kimi-k2.6',
  minimax: 'MiniMax-M2.7',
  doubao: 'doubao-seed-2-0-lite-260215',
  baidu: 'ernie-5.0',
  ollama: 'qwen3.5',
  custom: '',
}

export const DEFAULT_OLLAMA_BASE_URL = 'http://host.docker.internal:11434/v1'

function nonEmpty(value) {
  return typeof value === 'string' && Boolean(value.trim())
}

export function configuredLlmProviders(response) {
  const definitions = Array.isArray(response?.providers) ? response.providers : []
  const profiles = response?.profiles && typeof response.profiles === 'object' ? response.profiles : {}
  const credentials = response?.credentials && typeof response.credentials === 'object' ? response.credentials : {}

  return definitions.flatMap(definition => {
    const id = typeof definition?.id === 'string' ? definition.id.trim() : ''
    const profile = profiles[id]
    if (!id || !profile || !nonEmpty(profile.model) || !nonEmpty(profile.base_url)) return []

    const requiredCredentials = Array.isArray(definition.credential_fields)
      ? definition.credential_fields.filter(field => field?.required)
      : []
    const credentialsReady = requiredCredentials.every(field => (
      Boolean(credentials[id]?.[field.id]?.configured)
    ))
    if (!credentialsReady) return []

    return [{
      id,
      name: profile.display_name?.trim() || definition.name?.trim() || id,
      model: profile.model.trim(),
    }]
  })
}

export function resolveConfiguredLlmProvider(providers, preferred) {
  const available = Array.isArray(providers) ? providers : []
  return available.some(provider => provider.id === preferred)
    ? preferred
    : (available[0]?.id || '')
}
