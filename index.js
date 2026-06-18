const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { spawn, execSync } = require('child_process')
const net = require('net')
const fs = require('fs')

let mainWindow = null
let pythonProcess = null
let backendPort = null

const isDev = process.env.NODE_ENV === 'development'
const SERVER_SRC_DIR = path.join(process.resourcesPath, 'server-src')

/**
 * 查找可用的 Python 解释器。
 * 优先级：
 *   1. VID2NOTE_VENV_PYTHON 环境变量（开发/测试用）
 *   2. app 数据目录下首次运行创建的 venv
 *   3. 系统 python3.11 / python3
 */
function findPython() {
  if (isDev) return process.env.VID2NOTE_VENV_PYTHON || 'python3'

  // 1. 环境变量指定的 Python（高级用户/开发）
  if (process.env.VID2NOTE_VENV_PYTHON && fs.existsSync(process.env.VID2NOTE_VENV_PYTHON)) {
    return process.env.VID2NOTE_VENV_PYTHON
  }

  // 2. app 数据目录下首次运行创建的 venv
  const userDataDir = app.getPath('userData')
  const venvPython = path.join(userDataDir, 'venv', 'bin', 'python')
  if (fs.existsSync(venvPython)) return venvPython

  // 3. 系统 python3.11（推荐）
  const candidates = [
    '/opt/homebrew/bin/python3.11',
    '/usr/local/bin/python3.11',
    process.env.HOME + '/.local/bin/python3.11',
    '/usr/bin/python3',
  ]
  for (const p of candidates) {
    if (fs.existsSync(p)) return p
  }
  return 'python3'
}

/**
 * 检查 Python 是否已安装 vid2note 依赖。若无，尝试用内置源码安装到 venv。
 */
function ensureDeps(pythonExe) {
  if (isDev) return pythonExe

  // 先检查是否已可 import
  try {
    execSync(`"${pythonExe}" -c "import vid2note_server, vid2note_core"`, {
      stdio: 'pipe',
      timeout: 10000,
    })
    return pythonExe // 已有依赖
  } catch (e) {
    // 需要安装
  }

  // 创建 venv 并安装
  const userDataDir = app.getPath('userData')
  const venvDir = path.join(userDataDir, 'venv')
  const venvPython = path.join(venvDir, 'bin', 'python')

  if (!fs.existsSync(venvPython)) {
    console.log('[vid2note] 首次运行：创建 venv…')
    try {
      execSync(`"${pythonExe}" -m venv "${venvDir}"`, { stdio: 'pipe', timeout: 60000 })
    } catch (e) {
      console.error('[vid2note] venv 创建失败:', e.message)
      return pythonExe
    }
  }

  console.log('[vid2note] 安装 vid2note 依赖…（首次约 2-5 分钟）')
  const coreSrc = path.join(process.resourcesPath, 'core-src')
  const serverSrc = SERVER_SRC_DIR
  try {
    execSync(`"${venvPython}" -m pip install -q -e "${coreSrc}[local-asr]" -e "${serverSrc}"`, {
      stdio: 'pipe',
      timeout: 600000,
    })
    console.log('[vid2note] 依赖安装完成')
    return venvPython
  } catch (e) {
    console.error('[vid2note] 依赖安装失败:', e.message)
    return venvPython // 仍尝试用 venv python 运行（可能部分可用）
  }
}

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

  let pythonExe = findPython()
  pythonExe = ensureDeps(pythonExe)

  // 设置 PYTHONPATH 让系统 python 能找到内置源码
  const coreSrcPath = path.join(process.resourcesPath, 'core-src', 'src')
  const serverSrcPath = path.join(SERVER_SRC_DIR, 'src')

  const env = {
    ...process.env,
    VID2NOTE_HOST: '127.0.0.1',
    VID2NOTE_PORT: String(backendPort),
    VID2NOTE_DATA_DIR: dataDir,
    VID2NOTE_LOG_LEVEL: isDev ? 'debug' : 'info',
    PYTHONPATH: isDev ? undefined : `${coreSrcPath}:${serverSrcPath}`,
  }

  const args = [
    '-m', 'uvicorn', 'vid2note_server.main:app',
    '--host', '127.0.0.1', '--port', String(backendPort),
  ]

  const cwd = isDev ? path.join(__dirname, '../..') : SERVER_SRC_DIR

  pythonProcess = spawn(pythonExe, args, {
    env,
    cwd,
    stdio: isDev ? 'inherit' : 'pipe',
  })

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

  // 等待后端启动（首次安装依赖时需要更长超时）
  await waitForBackend(`http://127.0.0.1:${backendPort}/api/v1/health`, 120000)
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
