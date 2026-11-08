import { defineConfig } from 'vite';

// Keep the API paths unchanged; forward requests to the local Python server.
export default defineConfig({
  server: {
    proxy: {
      '/exercises': 'http://127.0.0.1:8000',
      '/sets': 'http://127.0.0.1:8000',
    },
  },
});
