import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The frontend is served by the Python backend (single origin, port 8000).
// `npm run build:serve` compiles straight into degreeprograms/webapp/static/app.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../degreeprograms/webapp/static/app",
    emptyOutDir: true,
  },
});
