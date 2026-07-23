/**
 * 配置相关 API
 */

import { http, isApiError } from "./base";
import type { UIConfig } from "../api.types";

export type OutboundErrorCode =
  | "outbound_url_invalid"
  | "outbound_https_required"
  | "local_ai_disabled"
  | "private_network_blocked"
  | "outbound_dns_failed"
  | "outbound_connect_failed"
  | "outbound_response_too_large"
  | "outbound_bad_response"
  | "outbound_timeout"
  | "admin_token_unconfigured"
  | "admin_token_invalid";

export interface UpdateUIConfigOptions {
  adminToken?: string;
}

export const SECURITY_GUIDANCE: Partial<Record<OutboundErrorCode, string>> = {
  local_ai_disabled: "配置已保留；请在本页使用管理员令牌开启本地 AI 访问。",
  private_network_blocked: "该地址属于局域网或特殊网络，Clade 不允许访问。",
  outbound_https_required: "公网 AI 地址必须使用 HTTPS。",
  admin_token_unconfigured: "服务端尚未配置 CLADE_ADMIN_TOKEN。",
  admin_token_invalid: "管理员令牌不正确，请重新输入。",
};

export function getConfigErrorMessage(error: unknown): string {
  if (!isApiError(error)) return "请求失败";
  const code = error.code as OutboundErrorCode | undefined;
  return (code && SECURITY_GUIDANCE[code]) || error.detail || "请求失败";
}

function getOutboundErrorCode(error: unknown): OutboundErrorCode | undefined {
  return isApiError(error) ? error.code as OutboundErrorCode | undefined : undefined;
}

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
export async function updateUIConfig(
  config: UIConfig,
  options: UpdateUIConfigOptions = {},
): Promise<UIConfig> {
  console.log("[API] 保存配置...");
  const clearProviderApiKeys = Object.entries(config.providers || {})
    .filter(([, provider]) => provider.api_key_clear_requested)
    .map(([providerId]) => providerId);
  const body = {
    config,
    clear_provider_api_keys: clearProviderApiKeys,
  };
  const result = options.adminToken
    ? await http.post<UIConfig>("/api/config/ui", body, {
        headers: { "X-Clade-Admin-Token": options.adminToken },
      })
    : await http.post<UIConfig>("/api/config/ui", body);
  console.log("[API] 配置保存成功");
  return result;
}

// ============ API 测试 ============

export interface ApiTestParams {
  type: "chat" | "embedding";
  provider_id?: string;
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
  code?: OutboundErrorCode;
}

/**
 * 测试 API 连接
 */
export async function testApiConnection(params: ApiTestParams): Promise<ApiTestResult> {
  try {
    return await http.post<ApiTestResult>("/api/config/test-api", params, { timeout: 30000 });
  } catch (error) {
    const code = getOutboundErrorCode(error);
    return {
      success: false,
      message: getConfigErrorMessage(error),
      ...(code ? { code } : {}),
    };
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
  code?: OutboundErrorCode;
}

/**
 * 获取服务商的模型列表
 */
export async function fetchProviderModels(params: {
  provider_id?: string;
  base_url: string;
  api_key: string;
  provider_type: "openai" | "anthropic" | "google";
}): Promise<FetchModelsResult> {
  try {
    return await http.post<FetchModelsResult>("/api/config/fetch-models", params, { timeout: 20000 });
  } catch (error) {
    const code = getOutboundErrorCode(error);
    return {
      success: false,
      message: getConfigErrorMessage(error),
      models: [],
      ...(code ? { code } : {}),
    };
  }
}













