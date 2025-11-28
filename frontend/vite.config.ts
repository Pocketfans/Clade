import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 从环境变量读取端口配置，支持灵活部署
const BACKEND_PORT = process.env.BACKEND_PORT || "8022";
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
  build: {
    // 调整警告阈值（单位：KB）- 考虑到 PixiJS 和应用代码的实际需求
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心库
          "vendor-react": ["react", "react-dom"],
          // 2D 渲染库 (PixiJS) - 分割核心和扩展
          "vendor-pixi": ["pixi.js"],
          // 数据可视化库
          "vendor-d3": ["d3"],
          // 图表库
          "vendor-recharts": ["recharts"],
          // 力导向图
          "vendor-force-graph": ["react-force-graph-2d"],
          // Markdown 渲染
          "vendor-markdown": ["react-markdown"],
          // 图标库
          "vendor-icons": ["lucide-react"],
        },
      },
    },
  },
});
