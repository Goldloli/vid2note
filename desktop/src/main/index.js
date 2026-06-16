const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const net = require('net')

let mainWindow = null
let pythonProcess = null
let backendPort = null

const isDev = process.env.NODE_ENV === 'development'
const PYTHON_DIST_DIR = path.join(process.resourcesPath, 'python')
const PYTHON_EXE = path.join(PYTHON_DIST_DIR, 'bin', 'python3')

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
  const dataDir = path.join(app.getPath('userData'), 'data')

  const env = {
    ...process.env,
    VID2NOTE_HOST: '127.0.0.1',
    VID2NOTE_PORT: String(backendPort),
    VID2NOTE_DATA_DIR: dataDir,
    VID2NOTE_LOG_LEVEL: isDev ? 'debug' : 'info',
  }

  const pythonPath = isDev
    ? 'python3'
    : PYTHON_EXE

  const scriptPath = isDev
    ? path.join(__dirname, '../../server/src/vid2note_server/main.py')
    : path.join(PYTHON_DIST_DIR, 'server', 'main.py')

  const args = isDev
    ? ['-m', 'uvicorn', 'vid2note_server.main:app', '--host', '127.0.0.1', '--port', String(backendPort)]
    : ['-m', 'uvicorn', 'vid2note_server.main:app', '--host', '127.0.0.1', '--port', String(backendPort)]

  pythonProcess = spawn(pythonPath, args, {
    env,
    cwd: isDev ? path.join(__dirname, '../..') : PYTHON_DIST_DIR,
    stdio: isDev ? 'inherit' : 'pipe',
  })

  pythonProcess.on('error', (err) => {
    console.error('Python backend failed to start:', err)
  })

  pythonProcess.on('exit', (code) => {
    console.log(`Python backend exited with code ${code}`)
    pythonProcess = null
  })

  // 等待后端启动
  await waitForBackend(`http://127.0.0.1:${backendPort}/api/v1/health`)
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
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/dist/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// IPC: 暴露后端地址给 renderer
ipcMain.handle('get-backend-url', () => {
  return `http://127.0.0.1:${backendPort}`
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
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
})
