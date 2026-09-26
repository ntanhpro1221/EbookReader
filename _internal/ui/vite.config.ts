import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// Bản build nằm trong package Python (ebook_reader/webui/static) để app chạy không cần Node.
// Không đặt tên "dist": .gitignore của repo bỏ qua mọi thư mục dist/.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: {
    outDir: path.resolve(import.meta.dirname, "../ebook_reader/webui/static"),
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/media": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
});
