import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const base = env.VITE_BASE?.trim() || (mode === 'production' ? '/ron3ia-api/' : '/')

  return {
    plugins: [react()],
    base,
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
    server: {
      port: 3000,
      host: true,
    },
  }
})
