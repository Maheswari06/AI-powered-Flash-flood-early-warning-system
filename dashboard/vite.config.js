import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: ['leaflet', 'react-leaflet'],
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      // Phase 1 — Core pipeline
      '/api/v1/ingest': { target: 'http://localhost:8001', changeOrigin: true },
      '/api/v1/virtual-gauge': { target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/predict': { target: 'http://localhost:8004', changeOrigin: true },
      '/api/v1/features': { target: 'http://localhost:8003', changeOrigin: true },
      '/api/v1/alerts': { target: 'http://localhost:8005', changeOrigin: true },
      // Phase 2 — Intelligence layer
      '/api/v1/causal': { target: 'http://localhost:8006', changeOrigin: true },
      '/api/v1/ledger': { target: 'http://localhost:8007', changeOrigin: true },
      '/api/v1/chorus': { target: 'http://localhost:8008', changeOrigin: true },
      '/api/v1/fl': { target: 'http://localhost:8009', changeOrigin: true },
      '/api/v1/federated': { target: 'http://localhost:8009', changeOrigin: true },
      '/api/v1/evacuation': { target: 'http://localhost:8010', changeOrigin: true },
      '/api/v1/mirror': { target: 'http://localhost:8011', changeOrigin: true },
      // Phase 3 — ScarNet + Model Monitor + API Gateway
      '/api/v1/scarnet': { target: 'http://localhost:8012', changeOrigin: true },
      '/api/v1/monitor': { target: 'http://localhost:8013', changeOrigin: true },
      '/api/v1/copilot': { target: 'http://localhost:8016', changeOrigin: true },
      '/api/v1/dashboard': { target: 'http://localhost:8000', changeOrigin: true },
      // Fallback
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
