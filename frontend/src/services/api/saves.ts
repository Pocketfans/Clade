/**
 * 存档相关 API
 */

import { http } from "./base";
import type { SaveMetadata } from "../api.types";

/**
 * 游戏状态
 */
export interface GameState {
  turn_index: number;
  species_count: number;
  total_species_count: number;
  sea_level: number;
  global_temperature: number;
  tectonic_stage: string;
  backend_session_id?: string;
}

/**
 * 获取游戏状态
 */
export async function fetchGameState(): Promise<GameState> {
  return http.get<GameState>("/api/game/state");
}

/**
 * 获取存档列表
 */
export async function listSaves(): Promise<SaveMetadata[]> {
  return http.get<SaveMetadata[]>("/api/saves/list");
}

/**
 * 创建新存档
 */
export async function createSave(params: {
  save_name: string;
  scenario: string;
  species_prompts?: string[];
  map_seed?: number;
}): Promise<{ success: boolean; message: string }> {
  return http.post("/api/saves/create", params);
}

/**
 * 保存游戏
 */
export async function saveGame(saveName: string): Promise<{ success: boolean; message: string }> {
  return http.post("/api/saves/save", { save_name: saveName });
}

/**
 * 加载游戏
 */
export async function loadGame(saveName: string): Promise<{ success: boolean; message: string }> {
  return http.post("/api/saves/load", { save_name: saveName });
}

/**
 * 删除存档
 */
export async function deleteSave(saveName: string): Promise<{ success: boolean }> {
  return http.delete(`/api/saves/${encodeURIComponent(saveName)}`);
}



