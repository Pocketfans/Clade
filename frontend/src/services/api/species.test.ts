import { afterEach, describe, expect, it, vi } from "vitest";

const baseMocks = vi.hoisted(() => ({
  getResponse: vi.fn(),
}));

vi.mock("./base", () => ({
  http: {
    getResponse: baseMocks.getResponse,
  },
}));

import { fetchLineageTree, invalidateLineageCache } from "./species";

describe("lineage API transport", () => {
  afterEach(() => {
    invalidateLineageCache();
    baseMocks.getResponse.mockReset();
    vi.unstubAllGlobals();
  });

  it("uses the shared HTTP client while preserving ETag cache reuse", async () => {
    const lineage = { nodes: [], total_count: 0 };
    baseMocks.getResponse
      .mockResolvedValueOnce({
        data: lineage,
        status: 200,
        headers: new Headers({ ETag: '"lineage-v1"' }),
      })
      .mockResolvedValueOnce({
        data: undefined,
        status: 304,
        headers: new Headers(),
      });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve(
        new Response(JSON.stringify({ nodes: [], total_count: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json", ETag: '"direct"' },
        }),
      )),
    );

    const first = await fetchLineageTree();
    const second = await fetchLineageTree();

    expect(baseMocks.getResponse).toHaveBeenCalledTimes(2);
    expect(baseMocks.getResponse).toHaveBeenNthCalledWith(2, "/api/lineage", {
      acceptedStatuses: [304],
      headers: { "If-None-Match": '"lineage-v1"' },
    });
    expect(first).toBe(lineage);
    expect(second).toBe(lineage);
  });

  it("rejects a not-modified response when no matching cache exists", async () => {
    baseMocks.getResponse.mockResolvedValue({
      data: undefined,
      status: 304,
      headers: new Headers(),
    });

    await expect(fetchLineageTree()).rejects.toThrow("获取族谱数据失败");
  });
});
