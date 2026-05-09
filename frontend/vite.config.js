import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 5174, // 5173 reserved for other dapps
    strictPort: false
  },
  define: {
    // @dfinity/agent expects globalThis.global in browsers
    global: 'globalThis'
  },
  optimizeDeps: {
    esbuildOptions: { target: 'es2020' }
  }
});
