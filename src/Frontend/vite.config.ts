import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Repo im Windows-Dateisystem + Docker Desktop: Dateiereignisse kommen im Container
// nicht zuverlässig an, deshalb Polling. In WSL2 mit DEV_POLLING=false abschalten.
const usePolling = process.env.DEV_POLLING !== 'false'
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://backend:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    // Der Playwright-Container ruft die App unter http://frontend-dev:5173 auf.
    allowedHosts: ['frontend-dev'],
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      // /api/... geht unverändert an das Backend, das unter /api/... antwortet (wie nginx in Produktion).
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
})
