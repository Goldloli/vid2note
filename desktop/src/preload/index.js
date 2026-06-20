const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  getBackendConnection: () => ipcRenderer.invoke('get-backend-connection'),
  chooseLocalVideo: () => ipcRenderer.invoke('choose-local-video'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
})
