import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import en from '../src/locales/en.js'
import zh from '../src/locales/zh.js'

test('bcut 前端文案只描述使用方式，不展示实验性和内部额度说明', () => {
  const copy = JSON.stringify({ zh: { asr: zh.asr, engine: zh.engine.bcut }, en: { asr: en.asr, engine: en.engine.bcut } })

  assert.doesNotMatch(copy, /实验性|公益接口|12 小时额度|Experimental|public-service|12-hour budget/i)
})

test('ASR 页面不展示 bcut 的恒定就绪状态或内部额度诊断', () => {
  const source = readFileSync(new URL('../src/views/Asr.vue', import.meta.url), 'utf8')

  assert.doesNotMatch(source, /cloudReady|bcutBudget|bcutBudgetText/)
})
