/**
 * 生态系统相关 API
 */

import { http } from "./base";
import type { FoodWebData, SpeciesFoodChain, ExtinctionImpact, FoodWebAnalysis, FoodWebRepairResult } from "../api.types";

/**
 * 获取食物网数据
 */
export async function fetchFoodWeb(): Promise<FoodWebData> {
  return http.get<FoodWebData>("/api/ecosystem/food-web");
}

/**
 * 获取特定物种的食物链
 */
export async function fetchSpeciesFoodChain(lineageCode: string): Promise<SpeciesFoodChain> {
  return http.get<SpeciesFoodChain>(`/api/ecosystem/food-web/${encodeURIComponent(lineageCode)}`);
}

/**
 * 分析物种灭绝影响
 */
export async function analyzeExtinctionImpact(lineageCode: string): Promise<ExtinctionImpact> {
  return http.get<ExtinctionImpact>(`/api/ecosystem/extinction-impact/${encodeURIComponent(lineageCode)}`);
}

/**
 * 获取食物网健康分析
 */
export async function fetchFoodWebAnalysis(): Promise<FoodWebAnalysis> {
  return http.get<FoodWebAnalysis>("/api/ecosystem/food-web/analysis");
}

/**
 * 修复食物网缺陷
 */
export async function repairFoodWeb(): Promise<FoodWebRepairResult> {
  return http.post<FoodWebRepairResult>("/api/ecosystem/food-web/repair");
}



