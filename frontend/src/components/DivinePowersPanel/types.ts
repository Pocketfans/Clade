/**
 * DivinePowersPanel 类型定义
 * 四大子系统：神格专精、信仰、神迹、预言赌注
 */

// ============ 神格路径 ============
export interface PathInfo {
  path: string;
  name: string;
  icon: string;
  description: string;
  passive_bonus: string;
  color: string;
  skills: string[];
}

export interface CurrentPath extends PathInfo {
  level: number;
  experience: number;
  next_level_exp: number;
  unlocked_skills: string[];
  secondary_path: string | null;
}

// ============ 技能 ============
export interface SkillInfo {
  id: string;
  name: string;
  path: string;
  description: string;
  cost: number;
  cooldown: number;
  unlock_level: number;
  icon: string;
  unlocked: boolean;
  uses: number;
  is_current_path: boolean;
}

// ============ 信仰系统 ============
export interface Follower {
  lineage_code: string;
  common_name: string;
  faith_value: number;
  turns_as_follower: number;
  is_blessed: boolean;
  is_sanctified: boolean;
  contribution_per_turn: number;
  status: string;
}

export interface FaithSummary {
  total_followers: number;
  total_faith: number;
  faith_bonus_per_turn: number;
  followers: Follower[];
}

// ============ 神迹 ============
export interface MiracleInfo {
  id: string;
  name: string;
  icon: string;
  description: string;
  cost: number;
  cooldown: number;
  charge_turns: number;
  one_time: boolean;
  current_cooldown: number;
  is_charging: boolean;
  charge_progress: number;
  available: boolean;
}

// ============ 预言赌注 ============
export interface WagerType {
  type: string;
  name: string;
  icon: string;
  description: string;
  min_bet: number;
  max_bet: number;
  duration: number;
  multiplier: number;
}

export interface ActiveWager {
  id: string;
  wager_type: string;
  target_species: string;
  secondary_species: string | null;
  bet_amount: number;
  start_turn: number;
  end_turn: number;
  predicted_outcome: string;
  current_progress: number;
  status: "active" | "won" | "lost" | "pending";
}

export interface WagerHistory {
  id: string;
  wager_type: string;
  bet_amount: number;
  won_amount: number;
  outcome: string;
  turn_resolved: number;
}

// ============ 组件 Props ============
export interface DivinePowersPanelProps {
  onClose: () => void;
  onSuccess?: () => void;
}

export type TabId = "path" | "faith" | "miracles" | "wagers";

// ============ API 响应 ============
export interface PathsResponse {
  available_paths: PathInfo[];
  current_path: CurrentPath | null;
}

export interface SkillsResponse {
  skills: SkillInfo[];
}

export type FaithResponse = FaithSummary;

export interface MiraclesResponse {
  miracles: MiracleInfo[];
  current_energy: number;
}

export interface WagersResponse {
  wager_types: WagerType[];
  active_wagers: ActiveWager[];
  history: WagerHistory[];
  current_energy: number;
}

