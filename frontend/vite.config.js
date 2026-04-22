import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  // `@vitejs/plugin-react-swc` keeps the dev HMR experience, but it is currently
  // unstable in this workspace's production build on Windows. Build falls back to
  // Vite's default esbuild JSX transform, which remains compatible with the repo.
  plugins: command === 'serve' ? [react()] : [],
  esbuild: {
    jsx: 'automatic',
    jsxImportSource: 'react',
  },
  server: {
    watch: {
      usePolling: true, // 强制使用轮询，解决 Windows 上 Docker 挂载目录热更新失效的问题
    },
    host: true,
  },
  optimizeDeps: {
    include: ['react-resizable-panels'],
  },
}))
