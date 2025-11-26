import type {
  ActionQueueStatus,
  LineageTree,
  MapOverview,
  PressureDraft,
  PressureTemplate,
  SaveMetadata,
  SpeciesDetail,
  TurnReport,
  UIConfig,
  SpeciesListItem,
  NicheCompareResult,
} from "./api.types";

/**
 * 连接到服务器发送事件流
 */
export function connectToEventStream(onEvent: (event: any) => void): EventSource {
  const eventSource = new EventSource("/api/events/stream");
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onEvent(data);
    } catch (error) {
      console.error("解析事件失败:", error);
    }
  };
  
  eventSource.onerror = (error) => {
    console.error("事件流连接错误:", error);
  };
  
  return eventSource;
}

export async function fetchQueueStatus(): Promise<ActionQueueStatus> {
  const res = await fetch("/api/queue");
  if (!res.ok) throw new Error("queue status failed");
  return res.json();
}

export async function runTurn(pressures: PressureDraft[] = []): Promise<TurnReport[]> {
  console.log("🚀 [演化] 发送推演请求到后端...");
  console.log("📋 [演化] 应用压力数量:", pressures.length);
  
  const res = await fetch("/api/turns/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rounds: 1, pressures }),
  });
  
  if (!res.ok) {
    console.error("❌ [演化] 推演请求失败, 状态码:", res.status);
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `推演请求失败 (${res.status})`);
  }
  
  console.log("📦 [演化] 收到后端响应，正在解析数据...");
  const data = await res.json();
  
  if (data && data.length > 0) {
    const report = data[data.length - 1];
    console.log("📊 [演化] 回合", report.turn_index, "数据:");
    console.log("  - 物种总数:", report.species_summary?.total_species || 0);
    console.log("  - 总人口:", report.species_summary?.total_population?.toLocaleString() || 0);
    console.log("  - 分化事件:", report.speciation_count || 0);
    console.log("  - 灭绝事件:", report.extinctions?.length || 0);
  }
  
  return data;
}

export async function fetchMapOverview(viewMode: string = "terrain", speciesCode?: string): Promise<MapOverview> {
  // 始终请求完整的 126x40 六边形网格 (约5040个)，支持视图模式切换
  let url = `/api/map?limit_tiles=6000&limit_habitats=500&view_mode=${viewMode}`;
  if (speciesCode) {
    url += `&species_code=${speciesCode}`;
  }
  const res = await fetch(url);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `地图请求失败 (${res.status})`);
  }
  return res.json();
}

export async function fetchUIConfig(): Promise<UIConfig> {
  const res = await fetch("/api/config/ui");
  if (!res.ok) throw new Error("config fetch failed");
  return res.json();
}

export async function updateUIConfig(config: UIConfig): Promise<UIConfig> {
  const res = await fetch("/api/config/ui", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error("config save failed");
  return res.json();
}

export async function fetchPressureTemplates(): Promise<PressureTemplate[]> {
  const res = await fetch("/api/pressures/templates");
  if (!res.ok) throw new Error("pressure templates failed");
  return res.json();
}

export async function addQueue(pressures: PressureDraft[], rounds = 1): Promise<ActionQueueStatus> {
  const res = await fetch("/api/queue/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pressures, rounds }),
  });
  if (!res.ok) throw new Error("queue add failed");
  return res.json();
}

export async function clearQueue(): Promise<ActionQueueStatus> {
  const res = await fetch("/api/queue/clear", { method: "POST" });
  if (!res.ok) throw new Error("queue clear failed");
  return res.json();
}

export async function fetchSpeciesDetail(lineageCode: string): Promise<SpeciesDetail> {
  const res = await fetch(`/api/species/${lineageCode}`);
  if (!res.ok) throw new Error("species detail failed");
  return res.json();
}

export async function fetchLineageTree(): Promise<LineageTree> {
  const res = await fetch("/api/lineage");
  if (!res.ok) throw new Error("lineage tree failed");
  return res.json();
}

export async function fetchHistory(limit = 10): Promise<TurnReport[]> {
  const res = await fetch(`/api/history?limit=${limit}`);
  if (!res.ok) throw new Error("history fetch failed");
  return res.json();
}

export interface GameState {
  turn_index: number;
  species_count: number;
  total_species_count: number;
  sea_level: number;
  global_temperature: number;
  tectonic_stage: string;
}

export async function fetchGameState(): Promise<GameState> {
  const res = await fetch("/api/game/state");
  if (!res.ok) throw new Error("game state fetch failed");
  return res.json();
}

export async function fetchExports(): Promise<any[]> {
  const res = await fetch("/api/exports");
  if (!res.ok) throw new Error("exports fetch failed");
  return res.json();
}

export async function editSpecies(lineageCode: string, data: {
  description?: string;
  morphology?: string;
  traits?: string;
  start_new_lineage?: boolean;
}): Promise<SpeciesDetail> {
  const res = await fetch(`/api/species/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lineage_code: lineageCode, ...data }),
  });
  if (!res.ok) throw new Error("species edit failed");
  return res.json();
}

export async function updateWatchlist(lineageCodes: string[]): Promise<any> {
  const res = await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lineage_codes: lineageCodes }),
  });
  if (!res.ok) throw new Error("watchlist update failed");
  return res.json();
}

export async function testApiConnection(params: {
  type: "chat" | "embedding";
  base_url: string;
  api_key: string;
  model: string;
  provider?: string;
}): Promise<{ success: boolean; message: string; details?: string }> {
  const res = await fetch("/api/config/test-api", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("test api failed");
  return res.json();
}

// 存档相关API
export async function listSaves(): Promise<SaveMetadata[]> {
  const res = await fetch("/api/saves/list");
  if (!res.ok) throw new Error("list saves failed");
  return res.json();
}

export async function createSave(params: {
  save_name: string;
  scenario: string;
  species_prompts?: string[];
  map_seed?: number;
}): Promise<any> {
  const res = await fetch("/api/saves/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "create save failed");
  }
  return res.json();
}

export async function saveGame(save_name: string): Promise<any> {
  const res = await fetch("/api/saves/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ save_name }),
  });
  if (!res.ok) throw new Error("save game failed");
  return res.json();
}

export async function loadGame(save_name: string): Promise<any> {
  const res = await fetch("/api/saves/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ save_name }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "load game failed");
  }
  return res.json();
}

export async function deleteSave(save_name: string): Promise<any> {
  const res = await fetch(`/api/saves/${save_name}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("delete save failed");
  return res.json();
}

export async function generateSpecies(prompt: string, lineage_code: string = "A1"): Promise<any> {
  const res = await fetch("/api/species/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, lineage_code }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "generate species failed");
  }
  return res.json();
}

export async function fetchSpeciesList(): Promise<SpeciesListItem[]> {
  const res = await fetch("/api/species/list");
  if (!res.ok) throw new Error("species list failed");
  const data = await res.json();
  return data.species;
}

export async function compareNiche(speciesA: string, speciesB: string): Promise<NicheCompareResult> {
  const res = await fetch("/api/niche/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ species_a: speciesA, species_b: speciesB }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "niche compare failed");
  }
  return res.json();
}

// Admin API
export async function checkHealth(): Promise<any> {
  const res = await fetch("/api/admin/health");
  if (!res.ok) throw new Error("health check failed");
  return res.json();
}

export async function resetWorld(keepSaves: boolean, keepMap: boolean): Promise<any> {
  const res = await fetch("/api/admin/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keep_saves: keepSaves, keep_map: keepMap }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "reset world failed");
  }
  return res.json();
}

export async function fetchLogs(lines = 100): Promise<string[]> {
  const res = await fetch(`/api/system/logs?lines=${lines}`);
  if (!res.ok) throw new Error("logs fetch failed");
  const data = await res.json();
  return data.logs;
}

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
  const res = await fetch("/api/system/ai-diagnostics");
  if (!res.ok) throw new Error("ai diagnostics fetch failed");
  return res.json();
}

export async function resetAIDiagnostics(): Promise<void> {
  const res = await fetch("/api/system/ai-diagnostics/reset", { method: "POST" });
  if (!res.ok) throw new Error("ai diagnostics reset failed");
}

// Rendering API
export async function fetchHeightMap(): Promise<Float32Array> {
  const res = await fetch("/api/render/heightmap");
  if (!res.ok) throw new Error("heightmap fetch failed");
  const buffer = await res.arrayBuffer();
  return new Float32Array(buffer);
}

export async function fetchWaterMask(): Promise<Float32Array> {
  const res = await fetch("/api/render/watermask");
  if (!res.ok) throw new Error("watermask fetch failed");
  const buffer = await res.arrayBuffer();
  return new Float32Array(buffer);
}

export async function fetchErosionMap(): Promise<Float32Array> {
  const res = await fetch("/api/render/erosionmap");
  if (!res.ok) throw new Error("erosionmap fetch failed");
  const buffer = await res.arrayBuffer();
  return new Float32Array(buffer);
}