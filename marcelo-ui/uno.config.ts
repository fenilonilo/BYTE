import { defineConfig, presetUno } from 'unocss'

export default defineConfig({
  presets: [presetUno()],
  theme: {
    colors: {
      bg: '#060a0f',
      blue: 'rgba(99,179,255,1)',
      violet: 'rgba(150,80,255,1)',
      green: 'rgba(150,255,180,1)',
      amber: 'rgba(255,200,80,1)',
      red: 'rgba(255,100,80,1)',
      ice: 'rgba(150,220,255,1)',
    },
    fontFamily: {
      sans: 'Inter, system-ui, sans-serif',
      mono: "'JetBrains Mono', monospace",
    },
  },
})
