/**
 * API 基础设施 - 统一的 HTTP 客户端
 */

// ============ 类型定义 ============

export interface ApiError extends Error {
  status: number;
  statusText: string;
  detail?: string;
}

export interface RequestConfig {
  timeout?: number;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

// ============ 工具函数 ============

function createApiError(message: string, status: number, statusText: string, detail?: string): ApiError {
  const error = new Error(message) as ApiError;
  error.name = "ApiError";
  error.status = status;
  error.statusText = statusText;
  error.detail = detail;
  return error;
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail || data.message || data.error || response.statusText;
  } catch {
    return response.statusText;
  }
}

// ============ 核心请求方法 ============

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  config: RequestConfig = {}
): Promise<T> {
  const { timeout = 30000, signal, headers = {} } = config;

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

    if (!response.ok) {
      const detail = await parseErrorResponse(response);
      throw createApiError(`请求失败: ${detail}`, response.status, response.statusText, detail);
    }

    // 处理空响应
    const text = await response.text();
    if (!text) {
      return undefined as T;
    }

    return JSON.parse(text) as T;
  } catch (error: unknown) {
    clearTimeout(timeoutId);
    if (error instanceof Error && error.name === "AbortError") {
      throw createApiError("请求超时或已取消", 0, "Timeout");
    }
    throw error;
  }
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
      const detail = await parseErrorResponse(response);
      throw createApiError(`请求失败: ${detail}`, response.status, response.statusText, detail);
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

