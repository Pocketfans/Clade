/**
 * 回合相关 API
 */

import { http } from "./base";
import type { TurnReport, PressureDraft, ActionQueueStatus, PressureTemplate } from "../api.types";

// 15分钟超时（回合执行可能很慢）
const TURN_TIMEOUT = 15 * 60 * 1000;

/**
 * 执行推演（支持多回合）
 * @param pressures 压力列表
 * @param rounds 回合数
 * @param autoReports 是否生成详细报告（自动过回合时可设为 false 以提高性能）
 */
export async function runTurn(
  pressures: PressureDraft[] = [], 
  rounds = 1,
  autoReports = true
): Promise<TurnReport[]> {
  console.log("🚀 [演化] 发送推演请求...");
  console.log("📋 [演化] 压力数量:", pressures.length, "生成报告:", autoReports);

  const data = await http.post<TurnReport[]>(
    "/api/turns/run",
    { rounds, pressures, auto_reports: autoReports },
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
 * @param rounds 总回合数
 * @param pressuresPerRound 每回合的压力
 * @param onProgress 进度回调
 * @param autoReports 是否生成详细报告（批量执行默认不生成）
 */
export async function runBatchTurns(
  rounds: number,
  pressuresPerRound?: PressureDraft[],
  onProgress?: (current: number, total: number, report: TurnReport) => void,
  autoReports = false  // 批量执行默认不生成详细报告
): Promise<TurnReport[]> {
  const allReports: TurnReport[] = [];

  for (let i = 0; i < rounds; i++) {
    console.log(`🔄 [批量执行] 回合 ${i + 1}/${rounds}`);
    const reports = await runTurn(pressuresPerRound || [], 1, autoReports);
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





