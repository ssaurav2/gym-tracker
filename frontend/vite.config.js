import { defineConfig, loadEnv } from 'vite';
import { fileURLToPath } from 'node:url';
import { frontendConfiguration } from './src/frontendConfiguration.js';

export default defineConfig(({ mode }) => {
  // Reject privileged keys before they can be written into browser build output.
  const env = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), 'VITE_');
  frontendConfiguration(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_PUBLISHABLE_KEY);
  return {
    server: {
      proxy: {
        '/exercises': 'http://127.0.0.1:8000',
        '/sets': 'http://127.0.0.1:8000',
      },
    },
  };
});
