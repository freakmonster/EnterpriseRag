import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,           // 允许外网/隧道访问
    allowedHosts: true,   // 不校验 Host 头（ngrok 等隧道域名非 localhost）
    // 开发时代理，把 /api 请求转发到后端 FastAPI 8001端口
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
