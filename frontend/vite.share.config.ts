import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

const entry = process.env.SHARE_ENTRY ?? 'plotly'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-share',
    emptyOutDir: false,
    copyPublicDir: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: fileURLToPath(new URL(`./src/share/${entry}.tsx`, import.meta.url)),
      output: {
        inlineDynamicImports: true,
        entryFileNames: `share-${entry}.js`,
        assetFileNames: 'share.[ext]',
      },
    },
  },
})
