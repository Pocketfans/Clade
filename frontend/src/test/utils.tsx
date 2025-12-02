/**
 * 测试工具函数
 *
 * 提供统一的 render 函数，自动包装所需的 Providers
 */

import { ReactElement, ReactNode } from "react";
import { render, RenderOptions } from "@testing-library/react";

// Mock Providers for testing
function MockProviders({ children }: { children: ReactNode }) {
  // 在实际使用时，这里应该包装真正的 Providers
  // 如 QueryProvider, GameProvider 等
  return <>{children}</>;
}

/**
 * 自定义 render 函数
 * 自动包装所有必需的 Providers
 */
function customRender(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, { wrapper: MockProviders, ...options });
}

// 重新导出 testing-library 的所有内容
export * from "@testing-library/react";
export { customRender as render };

// 常用的 mock 数据
export const mockSpecies = {
  lineage_code: "A1",
  latin_name: "Testus speciesus",
  common_name: "测试物种",
  population: 1000,
  population_share: 0.1,
  deaths: 50,
  death_rate: 0.05,
  ecological_role: "herbivore" as const,
  status: "alive" as const,
  notes: [],
};

export const mockTurnReport = {
  turn_index: 1,
  species_summary: {
    total_species: 10,
    total_population: 5000,
    alive: 8,
    extinct: 2,
  },
  species: [mockSpecies],
  extinctions: [],
  speciations: [],
  speciation_count: 0,
};

export const mockMapData = {
  width: 100,
  height: 100,
  turn: 1,
  tiles: [],
  stats: {
    land_area: 5000,
    water_area: 5000,
    avg_elevation: 0.5,
    avg_temperature: 20,
  },
};

/**
 * 等待异步状态更新
 */
export function waitForStateUpdate(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/**
 * Mock fetch 响应
 */
export function mockFetchResponse<T>(data: T, ok = true) {
  return {
    ok,
    status: ok ? 200 : 400,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as Response;
}
