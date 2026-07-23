/**
 * API 基础设施 - 统一的 HTTP 客户端
 */

// ============ 类型定义 ============

export interface ApiError extends Error {
  status: number;
  statusText: string;
  detail?: string;
  code?: string;
}

export interface RequestConfig {
  timeout?: number;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  acceptedStatuses?: number[];
}

export interface HttpResponse<T> {
  data: T;
  status: number;
  headers: Headers;
}

// ============ 工具函数 ============

function createApiError(
  message: string,
  status: number,
  statusText: string,
  detail?: string,
  code?: string,
): ApiError {
  const error = new Error(message) as ApiError;
  error.name = "ApiError";
  error.status = status;
  error.statusText = statusText;
  error.detail = detail;
  if (code) {
    error.code = code;
  }
  return error;
}

interface ParsedErrorResponse {
  message: string;
  code?: string;
}

async function parseErrorResponse(response: Response): Promise<ParsedErrorResponse> {
  try {
    const data: unknown = await response.json();
    if (typeof data === "object" && data !== null) {
      const payload = data as Record<string, unknown>;
      if (typeof payload.detail === "string") {
        return { message: payload.detail };
      }
      if (typeof payload.detail === "object" && payload.detail !== null) {
        const detail = payload.detail as Record<string, unknown>;
        if (typeof detail.message === "string") {
          return {
            message: detail.message,
            ...(typeof detail.code === "string" ? { code: detail.code } : {}),
          };
        }
      }
      if (typeof payload.message === "string") {
        return { message: payload.message };
      }
      if (typeof payload.error === "string") {
        return { message: payload.error };
      }
    }
  } catch {
    // Fall through to the response status text.
  }
  return { message: response.statusText };
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof Error && typeof (error as Partial<ApiError>).status === "number";
}

// ============ 核心请求方法 ============

async function requestResponse<T>(
  method: string,
  path: string,
  body?: unknown,
  config: RequestConfig = {}
): Promise<HttpResponse<T>> {
  const { timeout = 30000, signal, headers = {}, acceptedStatuses = [] } = config;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  // 合并外部取消信号
  if (signal) {
    signal.addEventListener("abort", () => controller.abort());
  }

  try {
    const init: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      signal: controller.signal,
    };

    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }

    const response = await fetch(path, init);
    clearTimeout(timeoutId);

    if (!response.ok && !acceptedStatuses.includes(response.status)) {
      const { message, code } = await parseErrorResponse(response);
      throw createApiError(`请求失败: ${message}`, response.status, response.statusText, message, code);
    }

    // 处理空响应
    const text = await response.text();
    if (!text) {
      return {
        data: undefined as T,
        status: response.status,
        headers: response.headers,
      };
    }

    return {
      data: JSON.parse(text) as T,
      status: response.status,
      headers: response.headers,
    };
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === "AbortError") {
      throw createApiError("请求超时或已取消", 0, "Timeout");
    }
    throw error;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  config: RequestConfig = {}
): Promise<T> {
  const response = await requestResponse<T>(method, path, body, config);
  return response.data;
}

async function requestBinary(path: string, config: RequestConfig = {}): Promise<ArrayBuffer> {
  const { timeout = 30000, signal } = config;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  if (signal) {
    signal.addEventListener("abort", () => controller.abort());
  }

  try {
    const response = await fetch(path, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!response.ok) {
      const { message, code } = await parseErrorResponse(response);
      throw createApiError(`请求失败: ${message}`, response.status, response.statusText, message, code);
    }

    return response.arrayBuffer();
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === "AbortError") {
      throw createApiError("请求超时", 0, "Timeout");
    }
    throw error;
  }
}

// ============ 导出的 HTTP 方法 ============

export const http = {
  get: <T>(path: string, config?: RequestConfig) => request<T>("GET", path, undefined, config),
  getResponse: <T>(path: string, config?: RequestConfig) => requestResponse<T>("GET", path, undefined, config),
  post: <T>(path: string, body?: unknown, config?: RequestConfig) => request<T>("POST", path, body, config),
  put: <T>(path: string, body?: unknown, config?: RequestConfig) => request<T>("PUT", path, body, config),
  patch: <T>(path: string, body?: unknown, config?: RequestConfig) => request<T>("PATCH", path, body, config),
  delete: <T>(path: string, config?: RequestConfig) => request<T>("DELETE", path, undefined, config),
  getBinary: (path: string, config?: RequestConfig) => requestBinary(path, config),
};

// ============ SSE 事件流 ============

export interface SSEEventHandler<T = unknown> {
  onMessage: (data: T) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
}

export function createEventSource<T = unknown>(path: string, handler: SSEEventHandler<T>): EventSource {
  const eventSource = new EventSource(path);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as T;
      handler.onMessage(data);
    } catch (error) {
      console.error("SSE 数据解析失败:", error);
    }
  };

  eventSource.onerror = (error) => {
    console.error("SSE 连接错误:", error);
    handler.onError?.(error);
  };

  eventSource.onopen = () => {
    handler.onOpen?.();
  };

  return eventSource;
}













