import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/dashboard/',
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true, assetsDir: 'assets', chunkSizeWarningLimit: 900,
    rollupOptions: { output: { manualChunks: id => id.includes('node_modules') ? (/react/.test(id) && !/antd/.test(id) ? 'react' : 'antd') : undefined, entryFileNames: 'assets/[name]-[hash].js',
      chunkFileNames: 'assets/[name]-[hash].js', assetFileNames: 'assets/[name]-[hash][extname]' } } },
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: { '/api': {
      target: 'http://127.0.0.1:8780', changeOrigin: true,
      configure(proxy) {
        proxy.on('proxyReq', (req) => {
          // Python rejects non-local origins. Browser remains same-origin to Vite.
          if (req.getHeader('origin')) req.setHeader('origin', 'http://127.0.0.1:8780');
        });
      },
    } },
  },
});
