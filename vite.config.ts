import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Ajustamos la base para que los assets carguen en GitHub Pages
  // Reemplaza 'nombre-de-tu-repo' con el nombre real de tu repositorio
  base: process.env.NODE_ENV === 'production' ? '/ron3ia-api/' : '/',
  build: {
    outDir: 'dist',
    sourcemap: true
  },
  server: {
    port: 3000,
    host: true
  }
})
