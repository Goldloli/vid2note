const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const net = require('net')
const { PythonService } = require('./python-service')
const { resolveBackendLaunch } = require('./backend-launch')
const { createSessionToken, withSessionToken } = require('./session-auth')

let mainWindow = null
let pythonProcess = null
let backendPort = null
const pythonService = new PythonService({ graceMs: 30_000 })
const apiToken = createSessionToken()

const isDev = process.env.NODE_ENV === 'development'

async function findFreePort(start = 18080) {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(start, '127.0.0.1', () => {
      const port = server.address().port
      server.close(() => resolve(port))
    })
    server.on('error', (err) => {
      if (err.code === 'EADDRINUSE') {
        findFreePort(start + 1).then(resolve, reject)
      } else {
        reject(err)
      }
    })
  })
}

async function startPythonBackend() {
  backendPort = await findFreePort()
  const dataDir = process.env.VID2NOTE_DATA_DIR || path.join(app.getPath('userData'), 'data')
  const launch = resolveBackendLaunch({
    isDev,
    resourcesPath: process.resourcesPath,
    projectRoot: path.join(__dirname, '../..'),
    dataDir,
    port: backendPort,
    inheritedEnv: process.env,
  })
  launch.env = withSessionToken(launch.env, apiToken)

  pythonProcess = spawn(launch.command, launch.args, {
    env: launch.env,
    cwd: launch.cwd,
    stdio: isDev ? 'inherit' : 'pipe',
  })
  pythonService.attach(pythonProcess)

  if (!isDev && pythonProcess.stderr) {
    pythonProcess.stderr.on('data', (d) => {
      console.error('[backend]', d.toString().trim())
    })
  }
  if (!isDev && pythonProcess.stdout) {
    pythonProcess.stdout.on('data', (d) => {
      console.log('[backend]', d.toString().trim())
    })
  }

  pythonProcess.on('error', (err) => {
    console.error('Python backend failed to start:', err)
  })

  pythonProcess.on('exit', (code) => {
    console.log(`Python backend exited with code ${code}`)
    pythonProcess = null
  })

  await waitForBackend(`http://127.0.0.1:${backendPort}/api/v1/health`, 30_000)
  return backendPort
}

async function waitForBackend(url, timeout = 30000) {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    try {
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      // ignore
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw new Error('Backend failed to start within timeout')
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    // macOS: 保留原生 traffic light（关闭/最小化/最大化），但隐藏标题文字，
    // 这样左上角只显示系统原生的三个圆点，不与 HTML 内绘制的按钮重复。
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    trafficLightPosition: { x: 14, y: 13 },
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    mainWindow.loadURL(process.env.VID2NOTE_RENDERER_URL || 'http://localhost:5173')
    if (process.env.VID2NOTE_OPEN_DEVTOOLS === '1') mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../../dist/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// IPC: 暴露后端地址给 renderer
ipcMain.handle('get-backend-url', () => {
  return `http://127.0.0.1:${backendPort}`
})
ipcMain.handle('get-backend-connection', () => ({
  baseUrl: `http://127.0.0.1:${backendPort}`,
  token: apiToken,
}))
ipcMain.handle('choose-local-video', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [{ name: '视频', extensions: ['mp4', 'mov', 'mkv', 'webm', 'm4v'] }],
  })
  return result.canceled ? null : result.filePaths[0]
})
ipcMain.handle('open-external', async (_event, value) => {
  const url = new URL(value)
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported external URL')
  await shell.openExternal(url.toString())
})

app.whenReady().then(async () => {
  try {
    await startPythonBackend()
    createWindow()
  } catch (err) {
    console.error('Failed to start app:', err)
    app.quit()
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  pythonService.stop()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  pythonService.stop()
})
