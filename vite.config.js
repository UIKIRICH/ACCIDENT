import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      },
      '/health': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      },
      '/keyframes': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      },
      '/uploaded_videos': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      }
    }
  }
})