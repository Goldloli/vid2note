const assert = require('node:assert/strict')
const path = require('node:path')
const test = require('node:test')

const { resolveBackendLaunch } = require('../../src/main/backend-launch')

test('production launches only the bundled backend and media resources', () => {
  const resourcesPath = path.join(path.sep, 'Applications', 'vid2note.app', 'Contents', 'Resources')
  const launch = resolveBackendLaunch({
    isDev: false,
    resourcesPath,
    dataDir: '/tmp/vid2note-data',
    port: 18080,
    inheritedEnv: { PATH: '', PIP_NO_INDEX: '1', VID2NOTE_VENV_PYTHON: '/missing/python' },
  })

  assert.equal(
    launch.command,
    path.join(resourcesPath, 'backend', 'vid2note-server'),
  )
  assert.deepEqual(launch.args, [])
  assert.equal(launch.cwd, path.join(resourcesPath, 'backend'))
  assert.equal(launch.env.VID2NOTE_HOST, '127.0.0.1')
  assert.equal(launch.env.VID2NOTE_PORT, '18080')
  assert.equal(launch.env.VID2NOTE_DATA_DIR, '/tmp/vid2note-data')
  assert.equal(
    launch.env.VID2NOTE_RESOURCES_DIR,
    path.join(resourcesPath, 'backend', '_internal', 'bin'),
  )
  assert.equal(launch.env.PIP_NO_INDEX, '1')
  assert.equal(launch.env.VID2NOTE_VENV_PYTHON, '/missing/python')
})

test('development keeps the source-backed Python launch', () => {
  const launch = resolveBackendLaunch({
    isDev: true,
    resourcesPath: '/unused',
    projectRoot: '/repo/desktop',
    dataDir: '/tmp/vid2note-data',
    port: 18081,
    inheritedEnv: { VID2NOTE_VENV_PYTHON: '/repo/.venv/bin/python', PYTHONPATH: '/repo/src' },
  })

  assert.equal(launch.command, '/repo/.venv/bin/python')
  assert.deepEqual(launch.args, [
    '-m',
    'uvicorn',
    'vid2note_server.main:app',
    '--host',
    '127.0.0.1',
    '--port',
    '18081',
  ])
  assert.equal(launch.cwd, '/repo/desktop')
  assert.equal(launch.env.PYTHONPATH, '/repo/src')
})
