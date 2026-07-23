import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("./base", () => ({ http: { post: mocks.post } }));

import { dropDatabase, resetWorld } from "./admin";

const adminHeaders = {
  headers: { "X-Clade-Admin-Token": "memory-only-token" },
};

describe("admin API token transport", () => {
  beforeEach(() => mocks.post.mockReset());

  it("sends the administrator token in the drop-database request header", async () => {
    await dropDatabase("memory-only-token");

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/admin/drop-database",
      { confirm: true },
      adminHeaders
    );
  });

  it("does not serialize the administrator token in the request body", async () => {
    await dropDatabase("memory-only-token");

    expect(JSON.stringify(mocks.post.mock.calls[0]?.[1])).not.toContain("memory-only-token");
  });

  it("sends the administrator token in the reset request header", async () => {
    await resetWorld("memory-only-token", true, false);

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/admin/reset",
      { keep_saves: true, keep_map: false },
      adminHeaders
    );
  });
});
