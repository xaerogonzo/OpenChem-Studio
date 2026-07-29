import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import wasm from 'vite-plugin-wasm'
import topLevelAwait from 'vite-plugin-top-level-await'

// Builds a fully self-contained static bundle (index.html + JS/CSS/wasm
// assets) that gets loaded via QWebEngineView.setUrl(QUrl.fromLocalFile(...)).
// `base: './'` keeps every asset reference relative so the page works when
// opened straight from the filesystem, with no dev server involved.
//
// ketcher-core bundles Raphael.js via a bare `require('raphael')` that
// survives Vite's default esbuild-based CJS interop, producing a runtime
// "require is not defined" error (see https://github.com/epam/ketcher/issues/5565).
// Routing that dependency through Vite/Rollup's own commonjs plugin (rather
// than skipping it) fixes it; wasm()/topLevelAwait() are separately needed
// for ketcher-standalone's indigo WASM engine.
export default defineConfig({
  plugins: [wasm(), topLevelAwait(), react()],
  base: './',
  optimizeDeps: {
    include: ['ketcher-core', 'ketcher-react', 'ketcher-standalone'],
  },
  define: {
    // ketcher-core's bundled Raphael.js references the Node `global` and
    // `process.env` globals directly; `globalThis` covers both the main
    // thread and worker contexts indigo runs in (unlike `window`).
    global: 'globalThis',
    'process.env': '{}',
  },
  worker: {
    format: 'es',
    plugins: () => [wasm(), topLevelAwait()],
  },
  build: {
    outDir: '../../src/openchem/resources/ketcher/dist',
    emptyOutDir: true,
    target: 'esnext',
    // Minification (esbuild/terser) re-triggers a TDZ bug ("Cannot access
    // 'x' before initialization") from the circular imports inside
    // ketcher-core once variable names are mangled. Gzip size is nearly
    // identical minified or not (~8.7MB, dominated by the embedded indigo
    // WASM binary), so there's no real tradeoff in leaving this off.
    minify: false,
    commonjsOptions: {
      include: [/ketcher/, /node_modules/],
      transformMixedEsModules: true,
    },
  },
})
