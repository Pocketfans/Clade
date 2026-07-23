import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  fetchSpeciesList: vi.fn(),
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  fetchSpeciesList: apiMocks.fetchSpeciesList,
  isApiError: (error: unknown) =>
    error instanceof Error &&
    typeof (error as Error & { status?: unknown }).status === "number",
  http: {
    get: apiMocks.get,
    post: apiMocks.post,
  },
}));

import { HybridizationPanel } from "./HybridizationPanel";

describe("HybridizationPanel species API boundary", () => {
  beforeEach(() => {
    apiMocks.fetchSpeciesList.mockReset().mockResolvedValue([
      {
        lineage_code: "alive-species",
        latin_name: "Species viva",
        common_name: "存活物种",
        population: 120,
        status: "alive",
        ecological_role: "herbivore",
      },
      {
        lineage_code: "extinct-species",
        latin_name: "Species extincta",
        common_name: "灭绝物种",
        population: 0,
        status: "extinct",
        ecological_role: "herbivore",
      },
    ]);
    apiMocks.get.mockReset().mockResolvedValue({ candidates: [] });
    apiMocks.post.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function mockForcedExecutionSelection() {
    apiMocks.fetchSpeciesList.mockResolvedValue([
      {
        lineage_code: "force-execute-a",
        latin_name: "Species fortis",
        common_name: "强制执行甲",
        population: 90,
        status: "alive",
        ecological_role: "herbivore",
      },
      {
        lineage_code: "force-execute-b",
        latin_name: "Species mixta",
        common_name: "强制执行乙",
        population: 75,
        status: "alive",
        ecological_role: "carnivore",
      },
    ]);
    const previewPath =
      "/api/hybridization/force/preview?species_a=force-execute-a&species_b=force-execute-b";
    apiMocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/hybridization/candidates") {
        return { candidates: [], total: 0 };
      }
      if (path === previewPath) {
        return {
          can_force_hybridize: true,
          reason: "可以强行杂交",
          can_normal_hybridize: false,
          normal_fertility: 0,
          energy_cost: 50,
          can_afford: true,
          current_energy: 100,
          preview: {
            type: "chimera",
            estimated_fertility: 0.12,
            stability: "unstable",
            parent_a: {
              code: "force-execute-a",
              name: "强制执行甲",
              trophic: 1,
            },
            parent_b: {
              code: "force-execute-b",
              name: "强制执行乙",
              trophic: 2,
            },
            warnings: [
              "嵌合体通常不育或极低可育性",
              "基因不稳定可能导致寿命缩短",
              "可能出现意想不到的能力或缺陷",
            ],
          },
          warnings: [
            "嵌合体通常不育或极低可育性",
            "基因不稳定可能导致寿命缩短",
            "可能出现意想不到的能力或缺陷",
          ],
        };
      }
      throw new Error(`Unexpected shared HTTP request: ${path}`);
    });
  }

  async function selectForcedExecutionPair() {
    fireEvent.click(screen.getByRole("button", { name: /强行杂交/ }));
    fireEvent.click((await screen.findAllByText("强制执行甲"))[0]);
    fireEvent.click(await screen.findByText("强制执行乙"));
    expect(await screen.findByText("嵌合体预览")).toBeInTheDocument();
  }

  it("loads the living species list through the shared API service", async () => {
    const browserFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/species/list") {
        throw new Error("HybridizationPanel must not fetch the species list directly");
      }
      if (url === "/api/hybridization/candidates") {
        return {
          ok: true,
          json: async () => ({ candidates: [] }),
        } as Response;
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);

    render(<HybridizationPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(apiMocks.fetchSpeciesList).toHaveBeenCalledOnce();
    });
    fireEvent.click(screen.getByRole("button", { name: /强行杂交/ }));

    expect(await screen.findByText("1 个可用物种")).toBeInTheDocument();
    const requestedUrls = browserFetch.mock.calls.map(([input]) => String(input));
    expect(requestedUrls).not.toContain("/api/species/list");
  });

  it("loads hybrid candidates through the shared HTTP client", async () => {
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("HybridizationPanel must not fetch candidates directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);

    render(<HybridizationPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith("/api/hybridization/candidates");
    });
    expect(await screen.findByText("暂无可杂交物种对")).toBeInTheDocument();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads the normal hybrid preview through the shared HTTP client", async () => {
    const candidate = {
      species_a: {
        lineage_code: "alpha-a",
        common_name: "候选甲",
        latin_name: "Species alpha",
        genus_code: "alpha",
      },
      species_b: {
        lineage_code: "alpha-b",
        common_name: "候选乙",
        latin_name: "Species beta",
        genus_code: "alpha",
      },
      fertility: 0.42,
      genus: "alpha",
    };
    const previewPath =
      "/api/hybridization/preview?species_a=alpha-a&species_b=alpha-b";
    apiMocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/hybridization/candidates") {
        return { candidates: [candidate], total: 1 };
      }
      if (path === previewPath) {
        return {
          can_hybridize: true,
          fertility: 0.42,
          energy_cost: 10,
          can_afford: true,
          preview: {
            lineage_code: "alpha-a×alpha-b",
            common_name: "甲乙杂交种",
            predicted_trophic_level: 2,
            combined_capabilities: [],
            parent_traits_merged: true,
          },
        };
      }
      throw new Error(`Unexpected shared HTTP request: ${path}`);
    });
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("HybridizationPanel must not fetch the normal preview directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);

    render(<HybridizationPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("候选甲"));

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith(previewPath);
    });
    expect(await screen.findByText("甲乙杂交种")).toBeInTheDocument();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads the forced hybrid preview through the shared HTTP client", async () => {
    apiMocks.fetchSpeciesList.mockResolvedValue([
      {
        lineage_code: "force-a",
        latin_name: "Species fortis",
        common_name: "强制甲",
        population: 90,
        status: "alive",
        ecological_role: "herbivore",
      },
      {
        lineage_code: "force-b",
        latin_name: "Species mixta",
        common_name: "强制乙",
        population: 75,
        status: "alive",
        ecological_role: "carnivore",
      },
    ]);
    const previewPath =
      "/api/hybridization/force/preview?species_a=force-a&species_b=force-b";
    apiMocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/hybridization/candidates") {
        return { candidates: [], total: 0 };
      }
      if (path === previewPath) {
        return {
          can_force_hybridize: true,
          reason: "可以强行杂交",
          can_normal_hybridize: false,
          normal_fertility: 0,
          energy_cost: 50,
          can_afford: true,
          current_energy: 100,
          preview: {
            type: "chimera",
            estimated_fertility: 0.12,
            stability: "unstable",
            parent_a: { code: "force-a", name: "强制甲", trophic: 1 },
            parent_b: { code: "force-b", name: "强制乙", trophic: 2 },
            warnings: [
              "嵌合体通常不育或极低可育性",
              "基因不稳定可能导致寿命缩短",
              "可能出现意想不到的能力或缺陷",
            ],
          },
        };
      }
      throw new Error(`Unexpected shared HTTP request: ${path}`);
    });
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("HybridizationPanel must not fetch the forced preview directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);

    render(<HybridizationPanel onClose={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /强行杂交/ }));
    fireEvent.click((await screen.findAllByText("强制甲"))[0]);
    fireEvent.click(await screen.findByText("强制乙"));

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith(previewPath);
    });
    expect(await screen.findByText("嵌合体预览")).toBeInTheDocument();
    expect(screen.getByText("12.0%")).toBeInTheDocument();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("executes a normal hybrid through the shared HTTP client", async () => {
    const candidate = {
      species_a: {
        lineage_code: "execute-a",
        common_name: "执行甲",
        latin_name: "Species agens",
        genus_code: "agens",
      },
      species_b: {
        lineage_code: "execute-b",
        common_name: "执行乙",
        latin_name: "Species acta",
        genus_code: "agens",
      },
      fertility: 0.55,
      genus: "agens",
    };
    const previewPath =
      "/api/hybridization/preview?species_a=execute-a&species_b=execute-b";
    apiMocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/hybridization/candidates") {
        return { candidates: [candidate], total: 1 };
      }
      if (path === previewPath) {
        return {
          can_hybridize: true,
          fertility: 0.55,
          energy_cost: 10,
          can_afford: true,
          preview: {
            lineage_code: "execute-a×execute-b",
            common_name: "执行杂交预览",
            predicted_trophic_level: 2,
            combined_capabilities: [],
            parent_traits_merged: true,
          },
        };
      }
      throw new Error(`Unexpected shared HTTP request: ${path}`);
    });
    apiMocks.post.mockResolvedValue({
      success: true,
      hybrid: {
        lineage_code: "execute-hybrid",
        latin_name: "Species hybrida",
        common_name: "执行杂交种",
        description: "测试杂交种",
        fertility: 0.55,
        parent_codes: ["execute-a", "execute-b"],
      },
      energy_spent: 10,
      energy_remaining: 90,
    });
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("HybridizationPanel must not execute a normal hybrid directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const onSuccess = vi.fn();

    render(<HybridizationPanel onClose={vi.fn()} onSuccess={onSuccess} />);

    fireEvent.click(await screen.findByText("执行甲"));
    expect(await screen.findByText("执行杂交预览")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "执行杂交" }));

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/hybridization/execute", {
        species_a: "execute-a",
        species_b: "execute-b",
      });
    });
    expect(
      await screen.findByText("成功创建杂交种：执行杂交种！消耗 10 能量"),
    ).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("preserves the normal hybrid server error detail", async () => {
    const candidate = {
      species_a: {
        lineage_code: "error-a",
        common_name: "错误甲",
        latin_name: "Species errora",
        genus_code: "error",
      },
      species_b: {
        lineage_code: "error-b",
        common_name: "错误乙",
        latin_name: "Species errorb",
        genus_code: "error",
      },
      fertility: 0.5,
      genus: "error",
    };
    const previewPath =
      "/api/hybridization/preview?species_a=error-a&species_b=error-b";
    apiMocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/hybridization/candidates") {
        return { candidates: [candidate], total: 1 };
      }
      if (path === previewPath) {
        return {
          can_hybridize: true,
          fertility: 0.5,
          energy_cost: 10,
          can_afford: true,
          preview: {
            lineage_code: "error-a×error-b",
            common_name: "错误预览",
            predicted_trophic_level: 2,
            combined_capabilities: [],
            parent_traits_merged: true,
          },
        };
      }
      throw new Error(`Unexpected shared HTTP request: ${path}`);
    });
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("请求失败: 能量不足"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "能量不足",
      }),
    );
    const browserFetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "能量不足" }),
    } as Response);
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);

    render(<HybridizationPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("错误甲"));
    expect(await screen.findByText("错误预览")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "执行杂交" }));

    expect(await screen.findByText("能量不足")).toBeInTheDocument();
    expect(screen.queryByText("请求失败: 能量不足")).not.toBeInTheDocument();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("executes a forced hybrid through the shared HTTP client", async () => {
    mockForcedExecutionSelection();
    apiMocks.post.mockResolvedValue({
      success: true,
      chimera: {
        lineage_code: "forced-chimera",
        latin_name: "Chimaera probata",
        common_name: "测试嵌合体",
        description: "测试强行杂交生成的嵌合体",
        fertility: 0.12,
        parent_codes: ["force-execute-a", "force-execute-b"],
        is_chimera: true,
      },
      energy_spent: 50,
      energy_remaining: 50,
    });
    const browserFetch = vi.fn().mockRejectedValue(
      new Error("HybridizationPanel must not execute a forced hybrid directly"),
    );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    const onSuccess = vi.fn();

    render(<HybridizationPanel onClose={vi.fn()} onSuccess={onSuccess} />);

    await selectForcedExecutionPair();
    fireEvent.click(screen.getByRole("button", { name: /执行强行杂交/ }));

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith(
        "/api/hybridization/force/execute",
        {
          species_a: "force-execute-a",
          species_b: "force-execute-b",
        },
      );
    });
    expect(
      await screen.findByText("🧬 成功创造嵌合体：测试嵌合体！消耗 50 能量"),
    ).toBeInTheDocument();
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("preserves the forced hybrid server error detail", async () => {
    mockForcedExecutionSelection();
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("请求失败: 强行杂交能量不足"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "强行杂交能量不足",
      }),
    );
    const browserFetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "强行杂交能量不足" }),
    } as Response);
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);

    render(<HybridizationPanel onClose={vi.fn()} />);

    await selectForcedExecutionPair();
    fireEvent.click(screen.getByRole("button", { name: /执行强行杂交/ }));

    expect(await screen.findByText("强行杂交能量不足")).toBeInTheDocument();
    expect(
      screen.queryByText("请求失败: 强行杂交能量不足"),
    ).not.toBeInTheDocument();
    expect(browserFetch).not.toHaveBeenCalled();
  });
});
