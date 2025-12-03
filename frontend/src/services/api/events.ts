/**
 * 事件流 API
 */

import { createEventSource, type SSEEventHandler } from "./base";

// ============ 事件类型定义 ============

// 基础事件类型（严格类型）
export type StrictEventType =
  | "turn_started"
  | "turn_completed"
  | "species_created"
  | "species_extinct"
  | "achievement_unlocked"
  | "energy_changed"
  | "error";

// 扩展事件类型（允许任意字符串，用于动态事件）
export type EventType = StrictEventType | string;

export interface GameEvent {
  type: EventType;
  data?: unknown;
  timestamp?: string;
  // 通用字段（后端 SSE 发送的格式）
  message?: string;
  category?: string;
  // AI 相关字段
  task?: string;
  chunks?: number;
  chunks_received?: number;
  total?: number;
  completed?: number;
  current_task?: string;
}

export interface TurnStartedEvent {
  type: "turn_started";
  data: { turn_index: number };
}

export interface TurnCompletedEvent {
  type: "turn_completed";
  data: { turn_index: number; species_count: number };
}

export interface SpeciesCreatedEvent {
  type: "species_created";
  data: { lineage_code: string; common_name: string };
}

export interface SpeciesExtinctEvent {
  type: "species_extinct";
  data: { lineage_code: string; common_name: string };
}

export interface AchievementUnlockedEvent {
  type: "achievement_unlocked";
  data: { name: string; icon: string; description: string; rarity: string };
}

export interface EnergyChangedEvent {
  type: "energy_changed";
  data: { current: number; max: number };
}

// ============ 类型守卫 ============

export function isTurnStartedEvent(event: GameEvent): event is TurnStartedEvent {
  return event.type === "turn_started";
}

export function isTurnCompletedEvent(event: GameEvent): event is TurnCompletedEvent {
  return event.type === "turn_completed";
}

export function isSpeciesCreatedEvent(event: GameEvent): event is SpeciesCreatedEvent {
  return event.type === "species_created";
}

export function isSpeciesExtinctEvent(event: GameEvent): event is SpeciesExtinctEvent {
  return event.type === "species_extinct";
}

export function isAchievementUnlockedEvent(event: GameEvent): event is AchievementUnlockedEvent {
  return event.type === "achievement_unlocked";
}

export function isEnergyChangedEvent(event: GameEvent): event is EnergyChangedEvent {
  return event.type === "energy_changed";
}

// ============ 事件流连接 ============

/**
 * 连接到游戏事件流
 */
export function connectToEventStream(onEvent: (event: GameEvent) => void): EventSource {
  const handler: SSEEventHandler<GameEvent> = {
    onMessage: onEvent,
    onError: (error) => {
      console.error("事件流连接错误:", error);
    },
    onOpen: () => {
      console.log("事件流已连接");
    },
  };

  return createEventSource<GameEvent>("/api/events/stream", handler);
}




