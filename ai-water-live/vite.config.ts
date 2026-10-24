import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));

// base './' にして、dist/ をどこに置いても（GitHub Pages のサブパスでも）動くようにする
export default defineConfig({
  base: './',
  build: {
    target: 'es2020',
    rollupOptions: {
      input: { main: here + 'index.html', methodology: here + 'methodology.html', film: here + 'film.html' },
      output: { manualChunks: (id: string) => (id.includes('node_modules/three') ? 'three' : undefined) },
    },
  },
  test: { include: ['test/**/*.test.ts'] },
});
