import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("./base", () => ({
  http: { get: vi.fn(), post: mocks.post },
  isApiError: (error: unknown) => error instanceof Error && typeof (error as { status?: unknown }).status === "number",
}));

import {
  fetchProviderModels,
  getConfigErrorMessage,
  testApiConnection,
  updateUIConfig,
} from "./config";
import type { UIConfig } from "../api.types";

const config = {
  providers: {
    main: {
      id: "main",
      name: "Main",
      type: "openai",
      provider_type: "openai" as const,
      api_key: "",
      api_key_configured: true,
      api_key_clear_requested: true,
      models: [],
    },
  },
  capability_routes: {},
} satisfies UIConfig;

describe("config API credential payloads", () => {
  beforeEach(() => {
    mocks.post.mockReset();
  });

  it("sends explicit provider clear requests outside the persisted config", async () => {
    mocks.post.mockResolvedValue(config);

    await updateUIConfig(config);

    expect(mocks.post).toHaveBeenCalledWith("/api/config/ui", {
      config,
      clear_provider_api_keys: ["main"],
    });
  });

  it("does not clear a stored key when its input is left empty", async () => {
    const keepStoredConfig = {
      ...config,
      providers: {
        main: {
          ...config.providers.main,
          api_key_clear_requested: false,
        },
      },
    } satisfies UIConfig;
    mocks.post.mockResolvedValue(keepStoredConfig);

    await updateUIConfig(keepStoredConfig);

    expect(mocks.post).toHaveBeenCalledWith("/api/config/ui", {
      config: keepStoredConfig,
      clear_provider_api_keys: [],
    });
  });

  it("uses the provider map key as the canonical clear identifier", async () => {
    const mismatchedIdConfig = {
      ...config,
      providers: {
        canonical: {
          ...config.providers.main,
          id: "stale-provider-id",
        },
      },
    } satisfies UIConfig;
    mocks.post.mockResolvedValue(mismatchedIdConfig);

    await updateUIConfig(mismatchedIdConfig);

    expect(mocks.post).toHaveBeenCalledWith("/api/config/ui", {
      config: mismatchedIdConfig,
      clear_provider_api_keys: ["canonical"],
    });
  });

  it("sends the admin token only in the header when the setting changes", async () => {
    mocks.post.mockResolvedValue(config);

    await updateUIConfig(config, { adminToken: "admin-secret" });

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/config/ui",
      expect.not.objectContaining({ adminToken: expect.anything() }),
      { headers: { "X-Clade-Admin-Token": "admin-secret" } },
    );
    expect(JSON.stringify(mocks.post.mock.calls[0][1])).not.toContain("admin-secret");
  });

  it("identifies a provider when testing with its stored key", async () => {
    mocks.post.mockResolvedValue({ success: true, message: "ok" });

    await testApiConnection({
      type: "chat",
      provider_id: "main",
      base_url: "https://example.com/v1",
      api_key: "",
      model: "gpt-test",
      provider_type: "openai",
    });

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/config/test-api",
      expect.objectContaining({ provider_id: "main", api_key: "" }),
      { timeout: 30000 }
    );
  });

  it("identifies a provider when fetching models with its stored key", async () => {
    mocks.post.mockResolvedValue({ success: true, message: "ok", models: [] });

    await fetchProviderModels({
      provider_id: "main",
      base_url: "https://example.com/v1",
      api_key: "",
      provider_type: "openai",
    });

    expect(mocks.post).toHaveBeenCalledWith(
      "/api/config/fetch-models",
      expect.objectContaining({ provider_id: "main", api_key: "" }),
      { timeout: 20000 }
    );
  });

  it("returns safe guidance and the structured code when an API test fails", async () => {
    const error = Object.assign(new Error("request failed"), {
      status: 400,
      statusText: "Bad Request",
      detail: "本地 AI 访问未开启",
      code: "local_ai_disabled",
    });
    mocks.post.mockRejectedValue(error);

    await expect(testApiConnection({
      type: "chat",
      base_url: "http://localhost:11434/v1",
      api_key: "",
      model: "local-model",
    })).resolves.toMatchObject({
      success: false,
      code: "local_ai_disabled",
      message: "配置已保留；请在本页使用管理员令牌开启本地 AI 访问。",
    });
  });

  it("uses a legacy API detail when model discovery fails", async () => {
    const error = Object.assign(new Error("request failed"), {
      status: 502,
      statusText: "Bad Gateway",
      detail: "服务暂时不可用",
    });
    mocks.post.mockRejectedValue(error);

    await expect(fetchProviderModels({
      base_url: "https://example.com/v1",
      api_key: "",
      provider_type: "openai",
    })).resolves.toEqual({
      success: false,
      message: "服务暂时不可用",
      models: [],
    });
  });

  it("does not expose arbitrary non-API error text", () => {
    expect(getConfigErrorMessage(new Error("secret URL https://example.com?q=token"))).toBe("请求失败");
  });
});
