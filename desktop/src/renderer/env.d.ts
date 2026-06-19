/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent
  export default component
}

interface Window {
  electronAPI?: {
    getBackendUrl(): Promise<string>
    chooseLocalVideo(): Promise<string | null>
    openExternal(url: string): Promise<void>
  }
  mermaid?: {
    render(id: string, source: string): Promise<{ svg: string }>
  }
}
