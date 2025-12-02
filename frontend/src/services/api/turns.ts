/**
 * 回合相关 API
 */

import { http } from "./base";
import type { TurnReport, PressureDraft, ActionQueueStatus, PressureTemplate } from "../api.types";

// 5分钟超时（回合执行可能很慢）
const TURN_TIMEOUT = 5 * 60 * 1000;

/**
 * 执行单回合推演
 */
export async function runTurn(pressures: PressureDraft[] = []): Promise<TurnReport[]> {
  console.log("🚀 [演化] 发送推演请求...");
  console.log("📋 [演化] 压力数量:", pressures.length);

  const data = await http.post<TurnReport[]>(
    "/api/turns/run",
    { rounds: 1, pressures },
    { timeout: TURN_TIMEOUT }
  );

  if (data && data.length > 0) {
    const report = data[data.length - 1];
    console.log("✅ [演化] 回合", report.turn_index, "完成");
  }

  return data || [];
}

/**
 * 批量执行多回合
 */
export async function runBatchTurns(
  rounds: number,
  pressuresPerRound?: PressureDraft[],
  onProgress?: (current: number, total: number, report: TurnReport) => void
): Promise<TurnReport[]> {
  const allReports: TurnReport[] = [];

  for (let i = 0; i < rounds; i++) {
    console.log(`🔄 [批量执行] 回合 ${i + 1}/${rounds}`);
    const reports = await runTurn(pressuresPerRound || []);
    allReports.push(...reports);

    if (reports.length > 0 && onProgress) {
      onProgress(i + 1, rounds, reports[reports.length - 1]);
    }
  }

  return allReports;
}

/**
 * 获取压力模板列表
 */
export async function fetchPressureTemplates(): Promise<PressureTemplate[]> {
  return http.get<PressureTemplate[]>("/api/pressures/templates");
}

/**
 * 获取历史回合报告
 */
export async function fetchHistory(limit = 10): Promise<TurnReport[]> {
  return http.get<TurnReport[]>(`/api/history?limit=${limit}`);
}

// ============ 队列 API ============

/**
 * 获取队列状态
 */
export async function fetchQueueStatus(): Promise<ActionQueueStatus> {
  return http.get<ActionQueueStatus>("/api/queue");
}

/**
 * 添加到队列
 */
export async function addQueue(pressures: PressureDraft[], rounds = 1): Promise<ActionQueueStatus> {
  return http.post<ActionQueueStatus>("/api/queue/add", { pressures, rounds });
}

/**
 * 清空队列
 */
export async function clearQueue(): Promise<ActionQueueStatus> {
  return http.post<ActionQueueStatus>("/api/queue/clear");
}

