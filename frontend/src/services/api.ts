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

export async function fetchQueueStatus(): Promise<ActionQueueStatus> {
  const res = await fetch("/api/queue");
  if (!res.ok) throw new Error("queue status failed");
  return res.json();
}

export async function runTurn(pressures: PressureDraft[] = []): Promise<TurnReport[]> {
  const res = await fetch("/api/turns/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rounds: 1, pressures }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `推演请求失败 (${res.status})`);
  }
  return res.json();
}

export async function fetchMapOverview(viewMode: string = "terrain"): Promise<MapOverview> {
  // 始终请求完整的 80x40 六边形网格，支持视图模式切换
  const res = await fetch(`/api/map?limit_tiles=3200&limit_habitats=500&view_mode=${viewMode}`);
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
