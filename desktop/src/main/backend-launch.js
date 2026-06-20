const path = require('node:path')

function resolveBackendLaunch({
  isDev,
  resourcesPath,
  projectRoot,
  dataDir,
  port,
  inheritedEnv = process.env,
}) {
  const env = {
    ...inheritedEnv,
    VID2NOTE_HOST: '127.0.0.1',
    VID2NOTE_PORT: String(port),
    VID2NOTE_DATA_DIR: dataDir,
    VID2NOTE_LOG_LEVEL: isDev ? 'debug' : 'info',
  }

  if (isDev) {
    return {
      command: inheritedEnv.VID2NOTE_VENV_PYTHON || 'python3',
      args: [
        '-m',
        'uvicorn',
        'vid2note_server.main:app',
        '--host',
        '127.0.0.1',
        '--port',
        String(port),
      ],
      cwd: projectRoot,
      env,
    }
  }

  const backendDir = path.join(resourcesPath, 'backend')
  env.VID2NOTE_RESOURCES_DIR = path.join(backendDir, '_internal', 'bin')
  return {
    command: path.join(backendDir, 'vid2note-server'),
    args: [],
    cwd: backendDir,
    env,
  }
}

module.exports = { resolveBackendLaunch }
