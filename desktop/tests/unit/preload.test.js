const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { runInNewContext } = require('node:vm')
const test = require('node:test')

test('preload exposes the authenticated backend connection to the renderer', async () => {
  let exposed
  const invocations = []
  const source = readFileSync('src/preload/index.js', 'utf8')
  runInNewContext(source, {
    require: () => ({
      contextBridge: { exposeInMainWorld: (_name, api) => { exposed = api } },
      ipcRenderer: { invoke: async (...args) => { invocations.push(args); return { baseUrl: 'http://127.0.0.1:18080', token: 'token' } } },
    }),
  })

  const connection = await exposed.getBackendConnection()

  assert.deepEqual(connection, { baseUrl: 'http://127.0.0.1:18080', token: 'token' })
  assert.deepEqual(invocations, [['get-backend-connection']])
})
