/**
 * 地图相关 API
 */

import { http } from "./base";
import type { MapOverview } from "../api.types";

/**
 * 获取地图概览
 */
export async function fetchMapOverview(
  viewMode: string = "terrain",
  speciesCode?: string
): Promise<MapOverview> {
  let url = `/api/map?limit_tiles=0&limit_habitats=0&view_mode=${viewMode}`;
  if (speciesCode) {
    url += `&species_code=${speciesCode}`;
  }
  // 增加超时到 60 秒，因为地图数据可能很大
  return http.get<MapOverview>(url, { timeout: 60000 });
}

/**
 * 获取高度图（二进制）
 */
export async function fetchHeightMap(): Promise<Float32Array> {
  const buffer = await http.getBinary("/api/render/heightmap");
  return new Float32Array(buffer);
}

/**
 * 获取水域遮罩（二进制）
 */
export async function fetchWaterMask(): Promise<Float32Array> {
  const buffer = await http.getBinary("/api/render/watermask");
  return new Float32Array(buffer);
}

/**
 * 获取侵蚀图（二进制）
 */
export async function fetchErosionMap(): Promise<Float32Array> {
  const buffer = await http.getBinary("/api/render/erosionmap");
  return new Float32Array(buffer);
}




