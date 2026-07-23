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
      usePolling: true,
    },
    host: true,
  },
  optimizeDeps: {
    include: ['react-resizable-panels'],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-is'],
          'vendor-pdf': ['pdfjs-dist'],
          'vendor-pdf-viewer': ['@react-pdf-viewer/core', '@react-pdf-viewer/highlight'],
          'vendor-charts': ['recharts'],
          'vendor-graph': ['react-force-graph-2d'],
          'vendor-markdown': ['react-markdown', 'remark-math', 'rehype-katex', 'katex'],
          'vendor-icons': ['lucide-react'],
          'vendor-data': ['axios'],
          'vendor-db': ['idb'],
        },
      },
    },
  },
}))
