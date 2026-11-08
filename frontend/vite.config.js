import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/exercises': 'http://127.0.0.1:8000',
      '/sets': 'http://127.0.0.1:8000',
    },
  },
});
