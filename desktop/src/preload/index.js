const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  chooseLocalVideo: () => ipcRenderer.invoke('choose-local-video'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
})
