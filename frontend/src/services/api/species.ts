/**
 * 物种相关 API
 */

import { http } from "./base";
import type {
  SpeciesDetail,
  SpeciesListItem,
  LineageTree,
  LineageQueryParams,
  NicheCompareResult,
  DormantGeneData,
} from "../api.types";

/**
 * 获取物种列表
 */
export async function fetchSpeciesList(): Promise<SpeciesListItem[]> {
  // 增加超时到 60 秒
  const data = await http.get<{ species: SpeciesListItem[] }>("/api/species/list", { timeout: 60000 });
  return data.species;
}

/**
 * 获取物种详情
 */
export async function fetchSpeciesDetail(lineageCode: string): Promise<SpeciesDetail> {
  return http.get<SpeciesDetail>(`/api/species/${encodeURIComponent(lineageCode)}`);
}

/**
 * 编辑物种
 */
export async function editSpecies(
  lineageCode: string,
  data: {
    description?: string;
    morphology?: string;
    traits?: string;
    start_new_lineage?: boolean;
  }
): Promise<SpeciesDetail> {
  return http.post<SpeciesDetail>("/api/species/edit", { lineage_code: lineageCode, ...data });
}

/**
 * 生成物种（简单版）
 */
export async function generateSpecies(prompt: string, lineageCode: string = "A1"): Promise<SpeciesDetail> {
  return http.post<SpeciesDetail>("/api/species/generate", { prompt, lineage_code: lineageCode });
}

/**
 * 生成物种（高级版）
 */
export interface GenerateSpeciesAdvancedParams {
  prompt: string;
  lineage_code?: string;
  habitat_type?: string;
  diet_type?: string;
  prey_species?: string[];
  parent_code?: string;
  is_plant?: boolean;
  plant_stage?: number;
}

export async function generateSpeciesAdvanced(params: GenerateSpeciesAdvancedParams): Promise<SpeciesDetail> {
  return http.post<SpeciesDetail>("/api/species/generate/advanced", params);
}

/**
 * 比较生态位
 */
export async function compareNiche(speciesA: string, speciesB: string): Promise<NicheCompareResult> {
  return http.post<NicheCompareResult>("/api/niche/compare", { species_a: speciesA, species_b: speciesB });
}

// ============ 族谱 API ============

// 族谱缓存（支持 ETag）
let _lineageCache: { data: LineageTree; etag: string; params: string } | null = null;

/**
 * 获取族谱树
 */
export async function fetchLineageTree(params?: LineageQueryParams): Promise<LineageTree> {
  const searchParams = new URLSearchParams();

  if (params?.status) searchParams.set("status", params.status);
  if (params?.prefix) searchParams.set("prefix", params.prefix);
  if (params?.include_genetic_distances) searchParams.set("include_genetic_distances", "true");
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));

  const paramsKey = searchParams.toString();
  const url = paramsKey ? `/api/lineage?${paramsKey}` : "/api/lineage";

  // 构建请求头（支持条件请求）
  const headers: Record<string, string> = {};
  if (_lineageCache && _lineageCache.params === paramsKey && _lineageCache.etag) {
    headers["If-None-Match"] = _lineageCache.etag;
  }

  const response = await http.getResponse<LineageTree>(url, {
    acceptedStatuses: [304],
    headers,
  });

  // 304 Not Modified: 使用缓存
  if (response.status === 304) {
    if (_lineageCache && _lineageCache.params === paramsKey) {
      return _lineageCache.data;
    }
    throw new Error("获取族谱数据失败");
  }

  const data = response.data;
  const etag = response.headers.get("ETag") || "";

  // 更新缓存
  _lineageCache = { data, etag, params: paramsKey };

  return data;
}

/**
 * 清除族谱缓存
 */
export function invalidateLineageCache(): void {
  _lineageCache = null;
}

// ============ 关注列表 ============

/**
 * 获取关注列表
 */
export async function fetchWatchlist(): Promise<string[]> {
  const data = await http.get<{ watching: string[] }>("/api/watchlist");
  return data.watching;
}

/**
 * 更新关注列表
 */
export async function updateWatchlist(lineageCodes: string[]): Promise<void> {
  await http.post("/api/watchlist", { lineage_codes: lineageCodes });
}

// ============ 基因编辑 API ============

/**
 * 添加休眠基因请求参数
 */
export interface AddDormantGeneParams {
  gene_type: "trait" | "organ";
  name: string;
  potential_value?: number;           // 特质潜力值 (0-15)
  pressure_types?: string[];          // 触发压力类型
  organ_data?: {                      // 器官数据
    category: string;
    type: string;
    parameters: Record<string, number>;
  };
}

/**
 * 添加休眠基因
 */
export async function addDormantGene(
  lineageCode: string,
  params: AddDormantGeneParams
): Promise<SpeciesDetail> {
  return http.post<SpeciesDetail>(
    `/api/species/${encodeURIComponent(lineageCode)}/genes`,
    params
  );
}

/**
 * 激活休眠基因
 */
export async function activateDormantGene(
  lineageCode: string,
  geneType: "trait" | "organ",
  geneName: string
): Promise<SpeciesDetail> {
  return http.post<SpeciesDetail>(
    `/api/species/${encodeURIComponent(lineageCode)}/genes/activate`,
    { gene_type: geneType, name: geneName }
  );
}

/**
 * 删除休眠基因
 */
export async function removeDormantGene(
  lineageCode: string,
  geneType: "trait" | "organ",
  geneName: string
): Promise<SpeciesDetail> {
  return http.delete<SpeciesDetail>(
    `/api/species/${encodeURIComponent(lineageCode)}/genes/${geneType}/${encodeURIComponent(geneName)}`
  );
}




