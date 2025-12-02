/**
 * HybridizationPanel 类型定义
 */

// ============ 物种信息 ============
export interface SpeciesInfo {
  lineage_code: string;
  common_name: string;
  latin_name: string;
  genus_code: string;
}

export interface AllSpecies {
  lineage_code: string;
  common_name: string;
  latin_name: string;
  status: string;
  population: number;
  ecological_role: string;
}

// ============ 杂交候选 ============
export interface HybridCandidate {
  species_a: SpeciesInfo;
  species_b: SpeciesInfo;
  fertility: number;
  genus: string;
}

// ============ 杂交预览 ============
export interface HybridPreview {
  can_hybridize: boolean;
  fertility?: number;
  energy_cost?: number;
  can_afford?: boolean;
  reason?: string;
  preview?: {
    lineage_code: string;
    common_name: string;
    predicted_trophic_level: number;
    combined_capabilities: string[];
  };
}

// ============ 强行杂交预览 ============
export interface ForceHybridPreview {
  can_force_hybridize: boolean;
  reason: string;
  can_normal_hybridize: boolean;
  normal_fertility: number;
  energy_cost: number;
  can_afford: boolean;
  current_energy: number;
  preview: {
    type: string;
    estimated_fertility: number;
    stability: string;
    parent_a: { code: string; name: string; trophic: number };
    parent_b: { code: string; name: string; trophic: number };
    warnings: string[];
  };
}

// ============ 杂交结果 ============
export interface HybridResult {
  success: boolean;
  hybrid?: {
    lineage_code: string;
    common_name: string;
    latin_name: string;
    fertility: number;
  };
  message?: string;
  energy_spent?: number;
}

// ============ 组件 Props ============
export interface HybridizationPanelProps {
  onClose: () => void;
  onSuccess?: () => void;
}

export type HybridMode = "normal" | "forced";



