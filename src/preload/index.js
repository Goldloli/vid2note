const { contextBridge, ipcRenderer } = require('electron')

// 暴露后端地址给渲染进程（安全方式，不暴露完整 ipcRenderer）
contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
})
