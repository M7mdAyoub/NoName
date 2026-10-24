import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

declare const process: { env: Record<string, string | undefined> }; // Node global; @types/node is not a dependency

// In development the API is proxied, so the app talks to its own origin (no CORS setup needed).
// Point VITE_API_TARGET at another server if the backend is not on 127.0.0.1:8000.
const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000';
const apiPaths = ['/upload', '/draft', '/publish', '/forms', '/dashboard', '/qualitative', '/export.csv', '/healthz', '/readyz'];

export default defineConfig({
  plugins: [react()],
  base: './',
  server: { port: 5173, strictPort: true, proxy: Object.fromEntries(apiPaths.map(path => [path, { target, changeOrigin: true }])) },
});
