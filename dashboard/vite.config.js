import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 3000,
    proxy: {
      '/admin': 'http://127.0.0.1:8000',
      '/gpu': 'http://127.0.0.1:8000',
      '/try-on-vton': 'http://127.0.0.1:8000',
      '/tryvtry-vton': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
});
