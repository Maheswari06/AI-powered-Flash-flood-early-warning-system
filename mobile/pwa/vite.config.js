import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import { VitePWA } from "vite-plugin-pwa"

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/*.png"],
      manifest: false,           // We use our own manifest.json
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        runtimeCaching: [
          {
            urlPattern: /\/api\/v1\/predictions/,
            handler: "NetworkFirst",
            options: {
              cacheName: "predictions-cache",
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
            },
          },
          {
            urlPattern: /\/api\/v1\/evacuation/,
            handler: "NetworkFirst",
            options: {
              cacheName: "evacuation-cache",
              networkTimeoutSeconds: 5,
            },
          },
          {
            urlPattern: /\/api\/v1\/chorus/,
            handler: "NetworkFirst",
            options: { cacheName: "chorus-cache", networkTimeoutSeconds: 5 },
          },
        ],
      },
    }),
  ],
  base: "/pwa/",
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
})
