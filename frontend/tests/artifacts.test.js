import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ProductReadError,
  readProductText,
  rewriteTaskScreenshotLinks,
} from '../src/artifacts.js'

function response({
  status = 200,
  contentType = 'text/plain; charset=utf-8',
  text = '',
} = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: name => name.toLowerCase() === 'content-type' ? contentType : '' },
    text: async () => text,
  }
}

test('does not request a product before the task has registered it', async () => {
  let calls = 0
  const result = await readProductText({
    url: '/product',
    available: false,
    fetchImpl: async () => {
      calls += 1
      return response()
    },
  })
  assert.deepEqual(result, { state: 'unavailable', text: '' })
  assert.equal(calls, 0)
})

test('treats 404 as missing instead of rendering the JSON body', async () => {
  const result = await readProductText({
    url: '/product',
    fetchImpl: async () => response({
      status: 404,
      contentType: 'application/json',
      text: '{"detail":"missing"}',
    }),
  })
  assert.deepEqual(result, { state: 'missing', text: '' })
})

test('rejects HTML and JSON responses even when HTTP status is 200', async () => {
  for (const candidate of [
    response({ contentType: 'text/html', text: '<!DOCTYPE html><html></html>' }),
    response({ contentType: 'text/plain', text: '  <html><body>app</body></html>' }),
    response({ contentType: 'application/json', text: '{"detail":"error"}' }),
  ]) {
    await assert.rejects(
      readProductText({
        url: '/product',
        fetchImpl: async () => candidate,
      }),
      error => error instanceof ProductReadError && error.reason === 'invalid-content',
    )
  }
})

test('returns valid SRT or Markdown text unchanged', async () => {
  const result = await readProductText({
    url: '/product',
    fetchImpl: async () => response({ text: '# 笔记\n\n正文' }),
  })
  assert.deepEqual(result, { state: 'ready', text: '# 笔记\n\n正文' })
})

test('rewrites historical and normalized screenshot paths to indexed product URLs', () => {
  const markdown = [
    '![第一张](../../screenshots/task_demo/shot_1680.png)',
    '![第二张](screenshots/task_demo/shot_2725.png "说明")',
  ].join('\n')
  const result = rewriteTaskScreenshotLinks(markdown, 'task_demo', [
    'notes/task_demo/../../screenshots/task_demo/shot_1680.png',
    'screenshots/task_demo/shot_2725.png',
  ])
  assert.match(result, /products\/screenshot\?index=0/)
  assert.match(result, /products\/screenshot\?index=1 "说明"/)
  assert.doesNotMatch(result, /\.\.\/\.\.\/screenshots/)
})

test('does not rewrite external or unregistered images', () => {
  const markdown = [
    '![外部](https://example.com/shot_1.png)',
    '![未登记](../../screenshots/other/shot_999.png)',
  ].join('\n')
  const result = rewriteTaskScreenshotLinks(markdown, 'task_demo', [
    'screenshots/task_demo/shot_1.png',
  ])
  assert.match(result, /https:\/\/example\.com\/shot_1\.png/)
  assert.match(result, /\.\.\/\.\.\/screenshots\/other\/shot_999\.png/)
  assert.doesNotMatch(result, /products\/screenshot/)
})
