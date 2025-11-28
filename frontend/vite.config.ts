import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 从环境变量读取端口配置，支持灵活部署
const BACKEND_PORT = process.env.BACKEND_PORT || "8000";
const FRONTEND_PORT = parseInt(process.env.FRONTEND_PORT || "5173", 10);

export default defineConfig({
  plugins: [react()],
  server: {
    port: FRONTEND_PORT,
    proxy: {
      "/api": {
        target: `http://localhost:${BACKEND_PORT}`,
        changeOrigin: true,
      },
    },
  },
});
