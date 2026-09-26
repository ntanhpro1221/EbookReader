import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// Bản build cho app Android (Capacitor): cùng mã giao diện, lối vào riêng (android.html -> src/android/main.tsx),
// ra thư mục web của dự án Android (mobile/www). Sau build, android.html được đổi tên thành index.html.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: {
    outDir: path.resolve(import.meta.dirname, "../mobile/www"),
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
    rollupOptions: { input: path.resolve(import.meta.dirname, "android.html") },
  },
});
