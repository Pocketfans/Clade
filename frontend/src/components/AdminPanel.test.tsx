import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  checkHealth: vi.fn(),
  dropDatabase: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  checkHealth: apiMocks.checkHealth,
  dropDatabase: apiMocks.dropDatabase,
}));

import { AdminPanel } from "./AdminPanel";

function apiError(status: number) {
  return Object.assign(new Error(`request failed with ${status}`), { status });
}

describe("AdminPanel destructive reset safety gate", () => {
  beforeEach(() => {
    apiMocks.checkHealth.mockReset().mockResolvedValue({
      status: "ok",
      api: "ok",
      database: "ok",
      initial_species: "ok",
    });
    apiMocks.dropDatabase.mockReset();
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true)
    );
    vi.stubGlobal("alert", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("passes the entered administrator token to the destructive API", async () => {
    apiMocks.dropDatabase.mockRejectedValue(apiError(403));
    render(<AdminPanel onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("管理员令牌"), {
      target: { value: "memory-only-token" },
    });
    fireEvent.change(screen.getByPlaceholderText("输入 DELETE 确认"), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "执行重置" }));

    await waitFor(() => {
      expect(apiMocks.dropDatabase).toHaveBeenCalledWith("memory-only-token");
    });
  });

  it("does not write the administrator token to browser storage", async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    render(<AdminPanel onClose={vi.fn()} />);
    await screen.findByText("API 服务");

    fireEvent.change(screen.getByLabelText("管理员令牌"), {
      target: { value: "memory-only-token" },
    });

    expect(setItemSpy).not.toHaveBeenCalled();
    setItemSpy.mockRestore();
  });

  it("enables reset only when both token and exact DELETE confirmation are present", async () => {
    render(<AdminPanel onClose={vi.fn()} />);
    await screen.findByText("API 服务");
    const resetButton = screen.getByRole("button", { name: "执行重置" });
    const tokenInput = screen.getByLabelText("管理员令牌");
    const confirmationInput = screen.getByPlaceholderText("输入 DELETE 确认");

    fireEvent.change(confirmationInput, { target: { value: "DELETE" } });
    expect(resetButton).toBeDisabled();

    fireEvent.change(confirmationInput, { target: { value: "" } });
    fireEvent.change(tokenInput, { target: { value: "memory-only-token" } });
    expect(resetButton).toBeDisabled();

    fireEvent.change(confirmationInput, { target: { value: "delete" } });
    expect(resetButton).toBeDisabled();

    fireEvent.change(confirmationInput, { target: { value: "DELETE" } });
    expect(resetButton).toBeEnabled();
  });

  it.each([
    [503, "服务端未配置管理员令牌"],
    [403, "管理员令牌无效"],
  ])("shows actionable feedback for a %i response", async (status, message) => {
    apiMocks.dropDatabase.mockRejectedValue(apiError(status));
    render(<AdminPanel onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("管理员令牌"), {
      target: { value: "memory-only-token" },
    });
    fireEvent.change(screen.getByPlaceholderText("输入 DELETE 确认"), {
      target: { value: "DELETE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "执行重置" }));

    await waitFor(() => {
      expect(alert).toHaveBeenCalledWith(expect.stringContaining(message));
    });
  });
});
