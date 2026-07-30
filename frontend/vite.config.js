import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import process from 'node:process'

const apiTarget = process.env.VID2NOTE_DEV_API_TARGET || 'http://localhost:8765'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  build: { chunkSizeWarningLimit: 1000 },
  server: { port: 5735, proxy: { '/api': { target: apiTarget, changeOrigin: true } } }
})
