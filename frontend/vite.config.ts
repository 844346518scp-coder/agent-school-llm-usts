import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { rollupOptions: { output: { manualChunks(id) {
    if (!id.includes('node_modules')) return
    if (id.includes('katex')) return 'math'
    if (id.includes('echarts') || id.includes('zrender')) return 'charts'
    if (id.includes('element-plus') || id.includes('@floating-ui')) return 'ui'
    if (id.includes('/vue/') || id.includes('@vue')) return 'vue'
  } } } },
})
