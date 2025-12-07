/**
 * 管理员/系统相关 API
 */

import { http } from "./base";

/**
 * 健康检查
 */
export async function checkHealth(): Promise<{ status: string }> {
  return http.get("/api/admin/health");
}

/**
 * 重置世界
 */
export async function resetWorld(keepSaves: boolean, keepMap: boolean): Promise<{ success: boolean }> {
  return http.post("/api/admin/reset", { keep_saves: keepSaves, keep_map: keepMap });
}

/**
 * 删除数据库
 */
export async function dropDatabase(): Promise<{ success: boolean }> {
  return http.post("/api/admin/drop-database", { confirm: true });
}

/**
 * 获取系统日志
 */
export async function fetchLogs(lines = 100): Promise<string[]> {
  const data = await http.get<{ logs: string[] }>(`/api/system/logs?lines=${lines}`);
  return data.logs;
}

// ============ AI 诊断 ============

export interface AIDiagnostics {
  concurrency_limit: number;
  active_requests: number;
  queued_requests: number;
  total_requests: number;
  total_timeouts: number;
  timeout_rate: string;
  request_stats: Record<string, {
    total: number;
    success: number;
    timeout: number;
    error: number;
    avg_time: number;
  }>;
  advice: string[];
}

export async function fetchAIDiagnostics(): Promise<AIDiagnostics> {
  return http.get<AIDiagnostics>("/api/system/ai-diagnostics");
}

export async function resetAIDiagnostics(): Promise<void> {
  await http.post("/api/system/ai-diagnostics/reset");
}

// ============ 任务控制 ============

export interface TaskDiagnostics {
  success: boolean;
  concurrency_limit?: number;
  active_requests?: number;
  queued_requests?: number;
  total_requests?: number;
  total_timeouts?: number;
  timeout_rate?: string;
  error?: string;
}

export interface AbortTasksResult {
  success: boolean;
  message: string;
  active_requests?: number;
  queued_requests?: number;
}

export async function abortCurrentTasks(): Promise<AbortTasksResult> {
  try {
    return await http.post<AbortTasksResult>("/api/tasks/abort");
  } catch (error) {
    return { success: false, message: String(error) };
  }
}

export async function skipCurrentAIStep(): Promise<AbortTasksResult> {
  try {
    return await http.post<AbortTasksResult>("/api/tasks/skip-ai-step");
  } catch (error) {
    return { success: false, message: String(error) };
  }
}

export async function getTaskDiagnostics(): Promise<TaskDiagnostics> {
  try {
    return await http.get<TaskDiagnostics>("/api/tasks/diagnostics");
  } catch (error) {
    return { success: false, error: String(error) };
  }
}












