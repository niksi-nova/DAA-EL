import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The PORT used by the Flask backend lives in the single .env file at the
  // project root (one level up from frontend/), not inside frontend/.env.
  // envDir points Vite there so `import.meta.env.PORT` (read in src/api.js)
  // resolves to the same value app.py reads.
  envDir: '../',
  // Vite only exposes env vars to client code if their name matches one of
  // these prefixes. Default is just 'VITE_'; we add the bare 'PORT' prefix
  // so the root .env's PORT=... variable is usable without renaming it.
  envPrefix: ['VITE_', 'PORT'],
})
