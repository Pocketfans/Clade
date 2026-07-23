import { afterEach, describe, expect, it, vi } from "vitest";

import { http, isApiError } from "./base";

describe("HTTP API errors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses a structured FastAPI detail without object stringification", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: "local_ai_disabled", message: "本地 AI 访问未开启" } }),
      { status: 400, statusText: "Bad Request", headers: { "Content-Type": "application/json" } },
    )));

    await expect(http.get("/probe")).rejects.toMatchObject({
      code: "local_ai_disabled",
      detail: "本地 AI 访问未开启",
    });
  });

  it("keeps supporting a legacy string detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "旧版错误消息" }),
      { status: 400, statusText: "Bad Request", headers: { "Content-Type": "application/json" } },
    )));

    const request = http.get("/probe");

    await expect(request).rejects.toMatchObject({ detail: "旧版错误消息" });
    await expect(request).rejects.not.toHaveProperty("code");
  });

  it.each([
    [{ message: "旧版 message" }, "旧版 message"],
    [{ error: "旧版 error" }, "旧版 error"],
  ])("supports legacy error payload %o", async (payload, expected) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify(payload),
      { status: 400, statusText: "Bad Request", headers: { "Content-Type": "application/json" } },
    )));

    await expect(http.get("/probe")).rejects.toMatchObject({ detail: expected });
  });

  it("falls back to status text when the body has no supported message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { unexpected: true } }),
      { status: 502, statusText: "Bad Gateway", headers: { "Content-Type": "application/json" } },
    )));

    await expect(http.get("/probe")).rejects.toMatchObject({ detail: "Bad Gateway" });
  });

  it("recognizes API errors structurally", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, {
      status: 500,
      statusText: "Internal Server Error",
    })));

    try {
      await http.get("/probe");
      throw new Error("expected request to fail");
    } catch (error) {
      expect(isApiError(error)).toBe(true);
    }

    expect(isApiError(new Error("plain"))).toBe(false);
    expect(isApiError({ status: 400 })).toBe(false);
  });

  it("returns response metadata and accepts explicitly listed statuses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, {
      status: 304,
      headers: { ETag: '"lineage-v1"' },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await http.getResponse("/api/lineage", {
      acceptedStatuses: [304],
      headers: { "If-None-Match": '"lineage-v1"' },
    });

    expect(response.data).toBeUndefined();
    expect(response.status).toBe(304);
    expect(response.headers.get("ETag")).toBe('"lineage-v1"');
    expect(fetchMock).toHaveBeenCalledWith("/api/lineage", expect.objectContaining({
      headers: {
        "Content-Type": "application/json",
        "If-None-Match": '"lineage-v1"',
      },
    }));
  });
});
