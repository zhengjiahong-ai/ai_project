import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      usePolling: true, // 强制使用轮询，解决 Windows 上 Docker 挂载目录热更新失效的问题
    },
    host: true,
  },
  optimizeDeps: {
    include: ['react-resizable-panels'],
  },
})
