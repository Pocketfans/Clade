/**
 * 配置相关 API
 */

import { http } from "./base";
import type { UIConfig } from "../api.types";

/**
 * 获取 UI 配置
 */
export async function fetchUIConfig(): Promise<UIConfig> {
  console.log("[API] 加载配置...");
  const config = await http.get<UIConfig>("/api/config/ui");
  console.log("[API] 配置加载成功");
  return config;
}

/**
 * 保存 UI 配置
 */
export async function updateUIConfig(config: UIConfig): Promise<UIConfig> {
  console.log("[API] 保存配置...");
  const result = await http.post<UIConfig>("/api/config/ui", config);
  console.log("[API] 配置保存成功");
  return result;
}

// ============ API 测试 ============

export interface ApiTestParams {
  type: "chat" | "embedding";
  base_url: string;
  api_key: string;
  model: string;
  provider?: string;
  provider_type?: "openai" | "anthropic" | "google";
}

export interface ApiTestResult {
  success: boolean;
  message: string;
  details?: string;
}

/**
 * 测试 API 连接
 */
export async function testApiConnection(params: ApiTestParams): Promise<ApiTestResult> {
  try {
    return await http.post<ApiTestResult>("/api/config/test-api", params, { timeout: 30000 });
  } catch (error) {
    return { success: false, message: "连接失败", details: String(error) };
  }
}

// ============ 模型列表 ============

export interface ModelInfo {
  id: string;
  name: string;
  description?: string;
  context_window?: number | null;
}

export interface FetchModelsResult {
  success: boolean;
  message: string;
  models: ModelInfo[];
}

/**
 * 获取服务商的模型列表
 */
export async function fetchProviderModels(params: {
  base_url: string;
  api_key: string;
  provider_type: "openai" | "anthropic" | "google";
}): Promise<FetchModelsResult> {
  try {
    return await http.post<FetchModelsResult>("/api/config/fetch-models", params, { timeout: 20000 });
  } catch (error) {
    return { success: false, message: String(error), models: [] };
  }
}












