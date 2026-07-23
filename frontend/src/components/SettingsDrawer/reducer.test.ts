import { describe, expect, it } from "vitest";
import { createInitialState, settingsReducer } from "./reducer";
import type { UIConfig } from "@/services/api.types";

const config = {
  providers: {
    main: {
      id: "main",
      name: "Main",
      type: "openai",
      provider_type: "openai" as const,
      api_key: "",
      api_key_configured: true,
      models: [],
    },
  },
  capability_routes: {},
} satisfies UIConfig;

describe("credential reducer actions", () => {
  it("marks an existing key for explicit clearing", () => {
    const state = settingsReducer(createInitialState(config), {
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "main",
    });

    expect(state.form.providers.main.api_key).toBe("");
    expect(state.form.providers.main.api_key_configured).toBe(false);
    expect(state.form.providers.main.api_key_clear_requested).toBe(true);
  });

  it("typing a replacement cancels a pending clear", () => {
    const cleared = settingsReducer(createInitialState(config), {
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "main",
    });
    const replaced = settingsReducer(cleared, {
      type: "UPDATE_PROVIDER_API_KEY",
      providerId: "main",
      apiKey: "sk-new",
    });

    expect(replaced.form.providers.main.api_key).toBe("sk-new");
    expect(replaced.form.providers.main.api_key_clear_requested).toBe(false);
  });

  it("normalizes provider identity from the record key during initialization and import", () => {
    const mismatchedConfig = {
      ...config,
      providers: {
        "canonical-key": {
          ...config.providers.main,
          id: "stale-id",
        },
      },
      capability_routes: {
        speciation: {
          timeout: 60,
          provider_id: "stale-id",
          provider_ids: ["stale-id", "canonical-key", "unknown-id", "unknown-id"],
        },
      },
    };
    const initialized = createInitialState(mismatchedConfig);

    expect(initialized.form.providers["canonical-key"].id).toBe("canonical-key");
    expect(initialized.form.capability_routes.speciation.provider_ids).toEqual([
      "canonical-key",
      "unknown-id",
    ]);

    const imported = settingsReducer(createInitialState(config), {
      type: "SET_FORM",
      form: mismatchedConfig,
    });

    expect(imported.form.providers["canonical-key"].id).toBe("canonical-key");
    expect(imported.form.capability_routes.speciation.provider_ids).toEqual([
      "canonical-key",
      "unknown-id",
    ]);

    const loadBalanced = settingsReducer(imported, {
      type: "TOGGLE_ROUTE_PROVIDER",
      capKey: "speciation",
      providerId: "canonical-key",
    });

    expect(loadBalanced.form.capability_routes.speciation.provider_ids).toEqual(["unknown-id"]);
    expect(loadBalanced.form.capability_routes.speciation.provider_ids).not.toContain("stale-id");
  });
});
