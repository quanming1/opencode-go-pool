import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ["echarts"],
        },
      },
    },
  },
  server: {
    port: 48701,
    // 开发期代理到后端（骨架阶段后端只有 /health，C 阶段接真实 API）
    proxy: {
      "/api": {
        target: "http://127.0.0.1:48700",
        changeOrigin: true,
      },
    },
  },
});
