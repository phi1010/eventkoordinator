import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  css: {
    modules: {
      localsConvention: 'camelCase'
    }
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
      '/oidc': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
      '/admin': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
})
