import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // The API runs on uvicorn at 8000 during local development.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
