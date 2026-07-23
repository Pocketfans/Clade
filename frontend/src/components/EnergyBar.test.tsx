import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  http: {
    get: apiMocks.get,
  },
}));

import { EnergyBar } from "./EnergyBar";

describe("EnergyBar API boundary", () => {
  beforeEach(() => {
    apiMocks.get.mockReset().mockResolvedValue({
      enabled: true,
      current: 750,
      maximum: 1000,
      regen_per_turn: 50,
      total_spent: 250,
      total_regenerated: 100,
      percentage: 75,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses the shared client and preserves polling cleanup", async () => {
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("EnergyBar must not call browser fetch directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const setIntervalSpy = vi.spyOn(window, "setInterval");
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");

    const { unmount } = render(<EnergyBar />);
    const pollingIntervalId = setIntervalSpy.mock.results[0]?.value;
    expect(pollingIntervalId).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText("750/1000")).toBeInTheDocument();
    });
    expect(apiMocks.get).toHaveBeenCalledWith("/api/energy");
    expect(browserFetch).not.toHaveBeenCalled();

    unmount();
    expect(clearIntervalSpy).toHaveBeenCalledWith(pollingIntervalId);
  });
});
