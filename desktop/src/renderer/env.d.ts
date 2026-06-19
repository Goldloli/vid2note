/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent
  export default component
}

interface Window {
  electronAPI?: {
    getBackendUrl(): Promise<string>
  }
  mermaid?: {
    render(id: string, source: string): Promise<{ svg: string }>
  }
}
