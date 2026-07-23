import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";
import {
  assertFrontendBindHostAllowed,
  resolveFrontendNetworkPolicy,
} from "./src/config/networkPolicy";

// 获取当前文件所在目录（确保 Vite 能找到 index.html）
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 从环境变量读取端口配置，支持灵活部署
const BACKEND_PORT = process.env.BACKEND_PORT || "8022";
const FRONTEND_PORT = parseInt(process.env.FRONTEND_PORT || "5188", 10);
const NETWORK_POLICY = resolveFrontendNetworkPolicy(process.env);

export default defineConfig({
  // 显式指定项目根目录，解决某些系统上启动脚本工作目录不正确的问题
  root: __dirname,
  plugins: [
    react(),
    {
      name: "clade-network-policy",
      configResolved(config) {
        assertFrontendBindHostAllowed(config.server.host, NETWORK_POLICY.lanEnabled);
        assertFrontendBindHostAllowed(config.preview.host, NETWORK_POLICY.lanEnabled);
      },
    },
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // 显式指定需要预打包的依赖，消除 Vite 5.x 的自动检测警告
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "pixi.js",
      "d3",
      "recharts",
      "react-force-graph-2d",
      "react-markdown",
      "lucide-react",
    ],
  },
  server: {
    host: NETWORK_POLICY.frontendHost,
    port: FRONTEND_PORT,
    proxy: {
      "/api": {
        target: `http://${NETWORK_POLICY.backendProxyHost}:${BACKEND_PORT}`,
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
