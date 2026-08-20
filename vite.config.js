import { defineConfig, loadEnv } from 'vite';
import { copyFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return {
    plugins: [{
      name: 'copy-classic-preview-scripts',
      async closeBundle() {
        await mkdir('dist', { recursive: true });
        await Promise.all(['script.js', 'config.js'].map((file) =>
          copyFile(path.resolve(file), path.resolve('dist', file)),
        ));
      },
    }],
    server: {
      port: 5173,
      proxy: {
        '/.proxy/api': {
          target: `http://127.0.0.1:${env.PORT || 3000}`,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/\.proxy/, ''),
        },
        '/.proxy/backend': {
          target: env.VITE_BACKEND_URL || env.BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/\.proxy\/backend/, ''),
        },
      },
    },
  };
});
