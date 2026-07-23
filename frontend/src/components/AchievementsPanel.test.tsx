import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  http: {
    get: apiMocks.get,
  },
}));

import { AchievementsPanel } from "./AchievementsPanel";

describe("AchievementsPanel API boundary", () => {
  beforeEach(() => {
    apiMocks.get.mockReset().mockResolvedValue({
      achievements: [],
      stats: {
        total: 0,
        unlocked: 0,
        percentage: 0,
        by_category: {},
        by_rarity: {},
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads achievements through the shared HTTP client", async () => {
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("AchievementsPanel must not call browser fetch directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<AchievementsPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith("/api/achievements");
    });
    expect(browserFetch).not.toHaveBeenCalled();
  });
});
