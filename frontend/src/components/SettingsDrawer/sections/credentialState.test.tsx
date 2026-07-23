import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ProviderConfig } from "@/services/api.types";
import { ConnectionSection } from "./ConnectionSection";
import { EmbeddingSection } from "./EmbeddingSection";

const apiMocks = vi.hoisted(() => ({
  testApiConnection: vi.fn(),
  fetchProviderModels: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  testApiConnection: apiMocks.testApiConnection,
  fetchProviderModels: apiMocks.fetchProviderModels,
}));

const storedProvider: ProviderConfig = {
  id: "main",
  name: "Main",
  type: "openai",
  provider_type: "openai",
  base_url: "https://example.com/v1",
  api_key: "",
  api_key_configured: true,
  models: ["gpt-test"],
  selected_models: ["gpt-test"],
};

describe("stored provider credential behavior", () => {
  beforeEach(() => {
    apiMocks.testApiConnection.mockReset();
    apiMocks.fetchProviderModels.mockReset();
    apiMocks.testApiConnection.mockResolvedValue({ success: true, message: "ok" });
    apiMocks.fetchProviderModels.mockResolvedValue({ success: true, message: "ok", models: [] });
  });

  it("keeps test and model fetch usable with only a stored key", async () => {
    const dispatch = vi.fn();
    const { container } = render(
      <ConnectionSection
        providers={{ main: storedProvider }}
        selectedProviderId="main"
        testResults={{}}
        testingProviderId={null}
        showApiKeys={{}}
        dispatch={dispatch}
      />
    );
    const actionButtons = container.querySelectorAll<HTMLButtonElement>(".form-actions button");

    expect(actionButtons).toHaveLength(2);
    expect(actionButtons[0]).toBeEnabled();
    expect(actionButtons[1]).toBeEnabled();

    fireEvent.click(actionButtons[0]);
    fireEvent.click(actionButtons[1]);

    await waitFor(() => {
      expect(apiMocks.testApiConnection).toHaveBeenCalledWith(
        expect.objectContaining({ provider_id: "main", api_key: "" })
      );
      expect(apiMocks.fetchProviderModels).toHaveBeenCalledWith(
        expect.objectContaining({ provider_id: "main", api_key: "" })
      );
    });
  });

  it("requests confirmation before clearing a stored key", () => {
    const dispatch = vi.fn();
    render(
      <ConnectionSection
        providers={{ main: storedProvider }}
        selectedProviderId="main"
        testResults={{}}
        testingProviderId={null}
        showApiKeys={{}}
        dispatch={dispatch}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "清除已保存密钥" }));

    const confirmation = dispatch.mock.calls.find(
      ([action]) => action.type === "SET_CONFIRM_DIALOG"
    )?.[0];
    expect(confirmation).toBeDefined();
    expect(dispatch).not.toHaveBeenCalledWith({
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "main",
    });

    confirmation.dialog.onConfirm();

    expect(dispatch).toHaveBeenCalledWith({ type: "CLEAR_PROVIDER_API_KEY", providerId: "main" });
  });

  it("clears by the selected provider map key when the embedded id is stale", () => {
    const dispatch = vi.fn();
    render(
      <ConnectionSection
        providers={{
          "canonical-key": { ...storedProvider, id: "stale-id" },
        }}
        selectedProviderId="canonical-key"
        testResults={{}}
        testingProviderId={null}
        showApiKeys={{}}
        dispatch={dispatch}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "清除已保存密钥" }));
    const confirmation = dispatch.mock.calls.find(
      ([action]) => action.type === "SET_CONFIRM_DIALOG"
    )?.[0];

    confirmation.dialog.onConfirm();

    expect(dispatch).toHaveBeenCalledWith({
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "canonical-key",
    });
    expect(dispatch).not.toHaveBeenCalledWith({
      type: "CLEAR_PROVIDER_API_KEY",
      providerId: "stale-id",
    });
  });

  it("uses the provider record key for connection selection, edits, tests, and model fetches", async () => {
    const dispatch = vi.fn();
    const { container } = render(
      <ConnectionSection
        providers={{
          "canonical-key": { ...storedProvider, id: "stale-id" },
        }}
        selectedProviderId="canonical-key"
        testResults={{}}
        testingProviderId={null}
        showApiKeys={{}}
        dispatch={dispatch}
      />
    );

    fireEvent.click(container.querySelector<HTMLElement>(".provider-item")!);
    fireEvent.change(screen.getByDisplayValue("Main"), { target: { value: "Renamed" } });
    const actionButtons = container.querySelectorAll<HTMLButtonElement>(".form-actions button");
    fireEvent.click(actionButtons[0]);
    fireEvent.click(actionButtons[1]);

    expect(dispatch).toHaveBeenCalledWith({ type: "SELECT_PROVIDER", id: "canonical-key" });
    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "UPDATE_PROVIDER", id: "canonical-key", value: "Renamed" })
    );
    await waitFor(() => {
      expect(apiMocks.testApiConnection).toHaveBeenCalledWith(
        expect.objectContaining({ provider_id: "canonical-key" })
      );
      expect(apiMocks.fetchProviderModels).toHaveBeenCalledWith(
        expect.objectContaining({ provider_id: "canonical-key" })
      );
    });
  });

  it("routes replacement input through the credential action", () => {
    const dispatch = vi.fn();
    render(
      <ConnectionSection
        providers={{ main: storedProvider }}
        selectedProviderId="main"
        testResults={{}}
        testingProviderId={null}
        showApiKeys={{}}
        dispatch={dispatch}
      />
    );

    fireEvent.change(screen.getByPlaceholderText("已配置；留空会保留现有密钥"), {
      target: { value: "sk-new" },
    });

    expect(dispatch).toHaveBeenCalledWith({
      type: "UPDATE_PROVIDER_API_KEY",
      providerId: "main",
      apiKey: "sk-new",
    });
  });

  it("disables connection actions while a clear is pending", () => {
    const { container } = render(
      <ConnectionSection
        providers={{
          main: { ...storedProvider, api_key_configured: false, api_key_clear_requested: true },
        }}
        selectedProviderId="main"
        testResults={{}}
        testingProviderId={null}
        showApiKeys={{}}
        dispatch={vi.fn()}
      />
    );
    const actionButtons = container.querySelectorAll<HTMLButtonElement>(".form-actions button");

    expect(actionButtons[0]).toBeDisabled();
    expect(actionButtons[1]).toBeDisabled();
  });

  it("lets embedding test use a stored provider key", async () => {
    const { container } = render(
      <EmbeddingSection
        providers={{ main: storedProvider }}
        embeddingProvider={null}
        embeddingProviderId="main"
        embeddingModel="embedding-test"
        dispatch={vi.fn()}
      />
    );
    const testButton = container.querySelector<HTMLButtonElement>(".card .btn-primary");

    expect(screen.getByRole("option", { name: /Main/ })).toBeInTheDocument();
    expect(testButton).toBeEnabled();
    fireEvent.click(testButton!);

    await waitFor(() => {
      expect(apiMocks.testApiConnection).toHaveBeenCalledWith(
        expect.objectContaining({ type: "embedding", provider_id: "main", api_key: "" })
      );
    });
  });

  it("uses the provider record key for embedding selection and requests", async () => {
    const dispatch = vi.fn();
    const { container } = render(
      <EmbeddingSection
        providers={{
          "canonical-key": { ...storedProvider, id: "stale-id" },
        }}
        embeddingProvider={null}
        embeddingProviderId="canonical-key"
        embeddingModel="embedding-test"
        dispatch={dispatch}
      />
    );
    const providerSelect = screen.getAllByRole("combobox")[0];
    const providerOption = screen.getByRole<HTMLOptionElement>("option", { name: /Main/ });

    expect(providerOption.value).toBe("canonical-key");
    fireEvent.change(providerSelect, { target: { value: providerOption.value } });
    fireEvent.click(container.querySelector<HTMLButtonElement>(".card .btn-primary")!);

    expect(dispatch).toHaveBeenCalledWith({
      type: "UPDATE_GLOBAL",
      field: "embedding_provider_id",
      value: "canonical-key",
    });
    await waitFor(() => {
      expect(apiMocks.testApiConnection).toHaveBeenCalledWith(
        expect.objectContaining({ type: "embedding", provider_id: "canonical-key" })
      );
    });
  });

  it("keeps an embedding provider pending clear unavailable", () => {
    const { container } = render(
      <EmbeddingSection
        providers={{
          main: { ...storedProvider, api_key_clear_requested: true },
        }}
        embeddingProvider={null}
        embeddingProviderId="main"
        embeddingModel="embedding-test"
        dispatch={vi.fn()}
      />
    );
    const testButton = container.querySelector<HTMLButtonElement>(".card .btn-primary");

    expect(screen.queryByRole("option", { name: /Main/ })).toBeNull();
    expect(testButton).toBeDisabled();
    fireEvent.click(testButton!);
    expect(apiMocks.testApiConnection).not.toHaveBeenCalled();
  });
});
