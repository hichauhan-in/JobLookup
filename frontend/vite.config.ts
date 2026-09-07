import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../joblookup/web", emptyOutDir: true },
  server: {
    host: "127.0.0.1",
    port: 5180,
    proxy: {
      "/api": {
        target: process.env.JOBLOOKUP_API_URL || "http://127.0.0.1:8800",
        changeOrigin: true,
      },
    },
  },
});
