import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { QueryProvider } from "@/providers/QueryProvider";

import "./styles/tokens.css"; // 设计系统变量
import "./styles.css";
import "./animations.css";
import "./enhancements.css"; // 界面增强样式

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryProvider>
      <App />
    </QueryProvider>
  </React.StrictMode>
);
