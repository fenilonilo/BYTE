import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import UnoCSS from '@unocss/vite'

export default defineConfig({
  plugins: [
    UnoCSS(),
    svelte(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
