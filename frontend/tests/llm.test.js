import assert from 'node:assert/strict'
import test from 'node:test'
import { configuredLlmProviders, resolveConfiguredLlmProvider } from '../src/llm.js'

const response = {
  providers: [
    {
      id: 'deepseek',
      name: 'DeepSeek',
      credential_fields: [{ id: 'api_key', required: true }],
    },
    {
      id: 'qwen',
      name: '通义千问',
      credential_fields: [{ id: 'api_key', required: true }],
    },
    {
      id: 'ollama',
      name: 'Ollama',
      is_local: true,
      credential_fields: [],
    },
    {
      id: 'custom',
      name: '自定义兼容服务',
      credential_fields: [{ id: 'api_key', required: true }],
    },
  ],
  profiles: {
    deepseek: {
      display_name: 'DeepSeek',
      model: 'deepseek-v4-flash',
      base_url: 'https://api.deepseek.com/v1',
    },
    qwen: {
      display_name: '通义千问',
      model: 'qwen3.7-plus',
      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    },
    ollama: {
      display_name: 'Ollama',
      model: 'qwen3:30b',
      base_url: 'http://host.docker.internal:11434/v1',
    },
    custom: {
      display_name: '自定义兼容服务',
      model: '',
      base_url: '',
    },
  },
  credentials: {
    deepseek: { api_key: { configured: true } },
    qwen: { api_key: { configured: false } },
    ollama: {},
    custom: { api_key: { configured: false } },
  },
}

test('only returns providers whose required public configuration is complete', () => {
  assert.deepEqual(configuredLlmProviders(response), [
    { id: 'deepseek', name: 'DeepSeek', model: 'deepseek-v4-flash' },
    { id: 'ollama', name: 'Ollama', model: 'qwen3:30b' },
  ])
})

test('custom provider requires profile fields and required credential state', () => {
  const configured = structuredClone(response)
  configured.profiles.custom.model = 'private-model'
  configured.profiles.custom.base_url = 'https://llm.example.test/v1'
  configured.credentials.custom.api_key.configured = true

  assert.equal(configuredLlmProviders(configured).at(-1).id, 'custom')
})

test('preferred provider falls back to the first configured provider or empty', () => {
  const providers = configuredLlmProviders(response)
  assert.equal(resolveConfiguredLlmProvider(providers, 'ollama'), 'ollama')
  assert.equal(resolveConfiguredLlmProvider(providers, 'qwen'), 'deepseek')
  assert.equal(resolveConfiguredLlmProvider([], 'deepseek'), '')
})
