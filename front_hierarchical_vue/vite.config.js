import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  base: '/vue',
  server: {
    port: process.env.VITE_PORT || 5172
  }
})
