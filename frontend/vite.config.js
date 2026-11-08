import { defineConfig } from 'vite';
import { isIP } from 'node:net';

function localPhotosOnly() {
  return {
    name: 'local-photos-only',
    configureServer(server) {
      // Check the original socket before forwarding: remote requests otherwise look local to Python.
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith('/progress-photos')) return next();
        const address = req.socket.remoteAddress;
        const local = address === '::1' || address === '::ffff:127.0.0.1' ||
          (isIP(address || '') === 4 && address.startsWith('127.'));
        if (!local) {
          res.writeHead(403, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify({ detail: 'Progress photos are available only on this computer for now.' }));
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [localPhotosOnly()],
  server: {
    proxy: {
      '/exercises': 'http://127.0.0.1:8000',
      '/sets': 'http://127.0.0.1:8000',
      '/progress-photos': 'http://127.0.0.1:8000',
    },
  },
});
