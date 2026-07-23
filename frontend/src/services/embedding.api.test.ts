import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    http: {
      ...actual.http,
      get: apiMocks.get,
      post: apiMocks.post,
    },
  };
});

import { embeddingApi } from "./embedding.api";

describe("Embedding API boundary", () => {
  beforeEach(() => {
    apiMocks.get.mockReset();
    apiMocks.post.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds taxonomy through the shared HTTP client", async () => {
    const response = {
      success: true,
      tree: {
        root: {
          name: "Life",
          latin_name: "Vita",
          children: [],
        },
      },
      stats: {
        total_species: 2,
        total_clades: 1,
        domain_count: 1,
        max_depth: 1,
        clustering_params: { threshold: 0.8 },
        turn_index: 12,
      },
      species_assignments: { "sp-alpha": ["Life"] },
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.buildTaxonomy(true, { threshold: 0.8 });

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/api/embedding/taxonomy/build",
      { rebuild: true, params: { threshold: 0.8 } },
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads species taxonomy through the shared HTTP client", async () => {
    const response = {
      species_code: "sp-alpha",
      classification: ["Life", "Alpha"],
      related_species: ["sp-beta"],
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getSpeciesTaxonomy("sp-alpha");

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/taxonomy/species/sp-alpha",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("propagates shared-client taxonomy failures", async () => {
    const error = Object.assign(new Error("Taxonomy unavailable"), {
      name: "ApiError",
      status: 503,
      statusText: "Service Unavailable",
      detail: "Taxonomy unavailable",
    });
    apiMocks.post.mockRejectedValue(error);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: error.detail }))),
    );

    await expect(embeddingApi.buildTaxonomy()).rejects.toBe(error);
  });

  it("loads evolution pressures through the shared HTTP client", async () => {
    const response = {
      pressures: [
        {
          name: "warming",
          name_cn: "升温",
          description: "Rising average temperature",
        },
      ],
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.listPressures();

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/evolution/pressures",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("predicts evolution through the shared HTTP client", async () => {
    const request = {
      species_code: "sp-alpha",
      pressure_types: ["warming"],
      pressure_strengths: [0.7],
      generate_description: true,
    };
    const response = {
      success: true,
      species_code: "sp-alpha",
      species_name: "Alpha",
      applied_pressures: ["warming"],
      predicted_trait_changes: { heat_tolerance: 0.2 },
      reference_species: [
        { code: "sp-beta", name: "Beta", similarity: 0.82 },
      ],
      confidence: 0.78,
      predicted_description: "Alpha becomes more heat tolerant.",
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.predictEvolution(request);

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/api/embedding/evolution/predict",
      request,
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("runs semantic search through the shared HTTP client", async () => {
    const response = {
      success: true,
      results: [
        {
          type: "species" as const,
          id: "sp-alpha",
          title: "Alpha",
          description: "Heat-tolerant species",
          similarity: 0.91,
          metadata: { turn: 12 },
        },
      ],
      query: "heat tolerance",
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.search(
      "heat tolerance",
      ["species", "concept"],
      7,
    );

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith("/api/embedding/search", {
      query: "heat tolerance",
      search_types: ["species", "concept"],
      top_k: 7,
    });
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("runs encoded quick search through the shared HTTP client", async () => {
    const response = {
      success: true,
      results: [],
      query: "alpha & beta",
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.quickSearch("alpha & beta", 4);

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/search/quick?q=alpha%20%26%20beta&limit=4",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("asks questions through the shared HTTP client", async () => {
    const response = {
      success: true,
      question: "Why did Alpha adapt?",
      answer: "Alpha adapted to sustained warming.",
      sources: [
        { type: "species", title: "Alpha", similarity: 0.93 },
      ],
      confidence: 0.88,
      follow_up_questions: ["Which trait changed most?"],
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.askQuestion("Why did Alpha adapt?");

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith("/api/embedding/qa", {
      question: "Why did Alpha adapt?",
    });
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("explains species through the shared HTTP client", async () => {
    const response = {
      success: true,
      species_code: "sp-alpha",
      species_name: "Alpha",
      explanation: "Alpha adapted to a warmer habitat.",
      key_factors: ["temperature"],
      trait_explanations: { heat_tolerance: "Selected by warming" },
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.explainSpecies("sp-alpha");

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/api/embedding/explain/species",
      { species_code: "sp-alpha" },
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("compares species through the shared HTTP client", async () => {
    const response = {
      success: true,
      similarity: 0.72,
      relationship: "closely related",
      details: {
        same_habitat: true,
        habitat_a: "temperate_forest",
        habitat_b: "temperate_forest",
        trophic_difference: 1,
        trait_differences: { size: 0.2 },
      },
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.compareSpecies("sp-alpha", "sp-beta");

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith(
      "/api/embedding/compare/species",
      { species_code_a: "sp-alpha", species_code_b: "sp-beta" },
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads embedding hints through the shared HTTP client", async () => {
    const response = {
      hints: [
        {
          type: "opportunity" as const,
          message: "Expand into the northern forest.",
          priority: "medium" as const,
          related_species: ["sp-alpha"],
          suggested_actions: ["migrate"],
        },
      ],
    };
    apiMocks.post.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getHints("sp-alpha");

    expect(result).toEqual(response);
    expect(apiMocks.post).toHaveBeenCalledWith("/api/embedding/hints", {
      species_code: "sp-alpha",
    });
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads turn narratives through the shared HTTP client", async () => {
    const response = {
      success: true,
      turn_index: 12,
      narrative: "Alpha spread through the northern forest.",
      key_events: [
        { title: "Expansion", description: "Alpha entered a new region." },
      ],
      related_species: ["sp-alpha"],
      novelty_info: { migration: 0.8 },
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getTurnNarrative(12);

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/narrative/turn/12",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads a bounded era range through the shared HTTP client", async () => {
    const response = {
      success: true,
      eras: [
        {
          name: "Forest Expansion",
          start_turn: 2,
          end_turn: 12,
          event_count: 5,
          summary: "Species expanded northward.",
        },
      ],
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getEras(2, 12);

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/narrative/eras?start_turn=2&end_turn=12",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("omits an unspecified era end turn", async () => {
    const response = { success: true, eras: [] };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getEras();

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/narrative/eras?start_turn=0",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads species biographies through the shared HTTP client", async () => {
    const response = {
      success: true,
      species_code: "sp-alpha",
      species_name: "Alpha",
      biography: "Alpha emerged in turn two and expanded northward.",
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getSpeciesBiography("sp-alpha");

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith(
      "/api/embedding/narrative/species/sp-alpha/biography",
    );
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("loads embedding statistics through the shared HTTP client", async () => {
    const response = {
      cache_stats: {
        cache_dir: "cache/embeddings",
        file_count: 4,
        memory_cache_count: 2,
        total_size_bytes: 4096,
        total_size_mb: 0.004,
        model_identifier: "local-test-model",
      },
      index_stats: {
        species_count: 12,
        event_count: 30,
        concept_count: 8,
      },
    };
    apiMocks.get.mockResolvedValue(response);
    const browserFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response)));
    vi.stubGlobal("fetch", browserFetch);

    const result = await embeddingApi.getStats();

    expect(result).toEqual(response);
    expect(apiMocks.get).toHaveBeenCalledWith("/api/embedding/stats");
    expect(browserFetch).not.toHaveBeenCalled();
  });
});
