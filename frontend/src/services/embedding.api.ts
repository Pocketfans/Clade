/**
 * Embedding 扩展功能 API 客户端
 * 
 * 提供以下功能：
 * 1. 自动分类学 (Taxonomy)
 * 2. 向量演化预测 (Evolution Prediction)
 * 3. 语义搜索 (Semantic Search)
 * 4. 智能问答 (QA)
 * 5. 物种解释 (Explanation)
 */

const API_BASE = '/api/embedding';

// ==================== 类型定义 ====================

/** 分类树响应 */
export interface TaxonomyResponse {
  success: boolean;
  tree: TaxonomyTree;
  stats: TaxonomyStats;
  species_assignments: Record<string, string[]>;
}

/** 分类树结构 */
export interface TaxonomyTree {
  root: {
    name: string;
    latin_name: string;
    children: CladeNode[];
  };
}

/** 类群节点 */
export interface CladeNode {
  id: number;
  name: string;
  latin_name: string;
  rank: string;
  member_count: number;
  cohesion: number;
  defining_traits: Record<string, any>;
  children: CladeNode[];
}

/** 分类统计 */
export interface TaxonomyStats {
  total_species: number;
  total_clades: number;
  domain_count: number;
  max_depth: number;
  clustering_params: Record<string, any>;
  turn_index: number;
}

/** 演化压力 */
export interface EvolutionPressure {
  name: string;
  name_cn: string;
  description: string;
}

/** 演化预测请求 */
export interface EvolutionPredictionRequest {
  species_code: string;
  pressure_types: string[];
  pressure_strengths?: number[];
  generate_description?: boolean;
}

/** 演化预测响应 */
export interface EvolutionPredictionResponse {
  success: boolean;
  species_code: string;
  species_name: string;
  applied_pressures: string[];
  predicted_trait_changes: Record<string, number>;
  reference_species: Array<{
    code: string;
    name: string;
    similarity: number;
  }>;
  confidence: number;
  predicted_description: string;
}

/** 搜索结果 */
export interface SearchResult {
  type: 'species' | 'event' | 'concept';
  id: string | number;
  title: string;
  description: string;
  similarity: number;
  metadata: Record<string, any>;
}

/** 搜索响应 */
export interface SearchResponse {
  success: boolean;
  results: SearchResult[];
  query: string;
}

/** 问答响应 */
export interface QAResponse {
  success: boolean;
  question: string;
  answer: string;
  sources: Array<{
    type: string;
    title: string;
    similarity: number;
  }>;
  confidence: number;
  follow_up_questions: string[];
}

/** 物种解释响应 */
export interface SpeciesExplanationResponse {
  success: boolean;
  species_code: string;
  species_name: string;
  explanation: string;
  key_factors: string[];
  trait_explanations: Record<string, string>;
}

/** 物种对比响应 */
export interface SpeciesCompareResponse {
  success: boolean;
  similarity: number;
  relationship: string;
  details: {
    same_habitat: boolean;
    habitat_a: string;
    habitat_b: string;
    trophic_difference: number;
    trait_differences: Record<string, any>;
  };
}

/** 游戏提示 */
export interface GameHint {
  type: 'evolution' | 'competition' | 'warning' | 'opportunity';
  message: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  related_species: string[];
  suggested_actions: string[];
}

/** 提示响应 */
export interface HintsResponse {
  hints: GameHint[];
}

/** 叙事响应 */
export interface NarrativeResponse {
  success: boolean;
  turn_index: number;
  narrative: string;
  key_events: Array<{
    title: string;
    description: string;
  }>;
  related_species: string[];
  novelty_info: Record<string, number>;
}

/** 时代信息 */
export interface Era {
  name: string;
  start_turn: number;
  end_turn: number;
  event_count: number;
  summary: string;
}

/** 时代响应 */
export interface ErasResponse {
  success: boolean;
  eras: Era[];
}

/** 物种传记响应 */
export interface BiographyResponse {
  success: boolean;
  species_code: string;
  species_name: string;
  biography: string;
}

/** 统计响应 */
export interface EmbeddingStatsResponse {
  cache_stats: {
    cache_dir: string;
    file_count: number;
    memory_cache_count: number;
    total_size_bytes: number;
    total_size_mb: number;
    model_identifier: string;
  };
  index_stats: {
    species_count: number;
    event_count: number;
    concept_count: number;
  };
}

// ==================== API 客户端 ====================

/**
 * Embedding API 客户端
 */
export const embeddingApi = {
  // ===== 分类学 =====
  
  /** 构建分类树 */
  async buildTaxonomy(rebuild = false, params?: Record<string, any>): Promise<TaxonomyResponse> {
    const response = await fetch(`${API_BASE}/taxonomy/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rebuild, params })
    });
    return response.json();
  },

  /** 获取物种分类信息 */
  async getSpeciesTaxonomy(speciesCode: string): Promise<{
    species_code: string;
    classification: string[];
    related_species: string[];
  }> {
    const response = await fetch(`${API_BASE}/taxonomy/species/${speciesCode}`);
    return response.json();
  },

  // ===== 演化预测 =====

  /** 列出可用的演化压力类型 */
  async listPressures(): Promise<{ pressures: EvolutionPressure[] }> {
    const response = await fetch(`${API_BASE}/evolution/pressures`);
    return response.json();
  },

  /** 预测物种演化方向 */
  async predictEvolution(request: EvolutionPredictionRequest): Promise<EvolutionPredictionResponse> {
    const response = await fetch(`${API_BASE}/evolution/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });
    return response.json();
  },

  // ===== 搜索 =====

  /** 语义搜索 */
  async search(query: string, searchTypes?: string[], topK = 10): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, search_types: searchTypes, top_k: topK })
    });
    return response.json();
  },

  /** 快速搜索 */
  async quickSearch(query: string, limit = 5): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE}/search/quick?q=${encodeURIComponent(query)}&limit=${limit}`);
    return response.json();
  },

  // ===== 问答 =====

  /** 智能问答 */
  async askQuestion(question: string): Promise<QAResponse> {
    const response = await fetch(`${API_BASE}/qa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    return response.json();
  },

  // ===== 解释 =====

  /** 解释物种演化原因 */
  async explainSpecies(speciesCode: string): Promise<SpeciesExplanationResponse> {
    const response = await fetch(`${API_BASE}/explain/species`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ species_code: speciesCode })
    });
    return response.json();
  },

  /** 对比两个物种 */
  async compareSpecies(codeA: string, codeB: string): Promise<SpeciesCompareResponse> {
    const response = await fetch(`${API_BASE}/compare/species`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ species_code_a: codeA, species_code_b: codeB })
    });
    return response.json();
  },

  // ===== 提示 =====

  /** 获取物种游戏提示 */
  async getHints(speciesCode: string): Promise<HintsResponse> {
    const response = await fetch(`${API_BASE}/hints`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ species_code: speciesCode })
    });
    return response.json();
  },

  // ===== 叙事 =====

  /** 获取回合叙事 */
  async getTurnNarrative(turnIndex: number): Promise<NarrativeResponse> {
    const response = await fetch(`${API_BASE}/narrative/turn/${turnIndex}`);
    return response.json();
  },

  /** 获取演化时代划分 */
  async getEras(startTurn = 0, endTurn?: number): Promise<ErasResponse> {
    let url = `${API_BASE}/narrative/eras?start_turn=${startTurn}`;
    if (endTurn !== undefined) {
      url += `&end_turn=${endTurn}`;
    }
    const response = await fetch(url);
    return response.json();
  },

  /** 获取物种传记 */
  async getSpeciesBiography(speciesCode: string): Promise<BiographyResponse> {
    const response = await fetch(`${API_BASE}/narrative/species/${speciesCode}/biography`);
    return response.json();
  },

  // ===== 统计 =====

  /** 获取 Embedding 系统统计 */
  async getStats(): Promise<EmbeddingStatsResponse> {
    const response = await fetch(`${API_BASE}/stats`);
    return response.json();
  }
};

export default embeddingApi;

