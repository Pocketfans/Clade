import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProviderConfig, UIConfig } from "@/services/api.types";
import { PerformanceSection } from "./PerformanceSection";

const storedProvider: ProviderConfig = {
  id: "stored",
  name: "Stored Provider",
  type: "openai",
  provider_type: "openai",
  base_url: "https://example.com/v1",
  api_key: "",
  api_key_configured: true,
  models: ["gpt-test"],
};

const pendingClearProvider: ProviderConfig = {
  ...storedProvider,
  id: "pending",
  name: "Pending Clear Provider",
  api_key_clear_requested: true,
};

describe("PerformanceSection provider availability", () => {
  it("offers stored-key providers but excludes providers pending clear", () => {
    const providers = {
      stored: storedProvider,
      pending: pendingClearProvider,
    };
    const config = { providers, capability_routes: {} } satisfies UIConfig;
    const { container } = render(
      <PerformanceSection config={config} providers={providers} dispatch={vi.fn()} />
    );

    const defaultProviderSelect = screen.getAllByRole("combobox")[0];
    expect(
      within(defaultProviderSelect).getByRole("option", { name: /Stored Provider/ })
    ).toBeInTheDocument();
    expect(
      within(defaultProviderSelect).queryByRole("option", { name: /Pending Clear Provider/ })
    ).toBeNull();

    fireEvent.click(container.querySelector<HTMLElement>(".capability-item-header")!);

    const capabilityProviderSelect = screen.getAllByRole("combobox")[2];
    expect(
      within(capabilityProviderSelect).getByRole("option", { name: /Stored Provider/ })
    ).toBeInTheDocument();
    expect(
      within(capabilityProviderSelect).queryByRole("option", { name: /Pending Clear Provider/ })
    ).toBeNull();
  });

  it("uses provider record keys for default and capability route values", () => {
    const dispatch = vi.fn();
    const providers = {
      "canonical-key": { ...storedProvider, id: "stale-id" },
    };
    const config = { providers, capability_routes: {} } satisfies UIConfig;
    const { container } = render(
      <PerformanceSection config={config} providers={providers} dispatch={dispatch} />
    );

    const defaultProviderSelect = screen.getAllByRole("combobox")[0];
    const defaultOption = within(defaultProviderSelect).getByRole<HTMLOptionElement>("option", {
      name: /Stored Provider/,
    });
    expect(defaultOption.value).toBe("canonical-key");
    fireEvent.change(defaultProviderSelect, { target: { value: defaultOption.value } });
    expect(dispatch).toHaveBeenCalledWith({
      type: "UPDATE_GLOBAL",
      field: "default_provider_id",
      value: "canonical-key",
    });

    fireEvent.click(container.querySelector<HTMLElement>(".capability-item-header")!);
    const routeProviderSelect = screen.getAllByRole("combobox")[2];
    const routeOption = within(routeProviderSelect).getByRole<HTMLOptionElement>("option", {
      name: /Stored Provider/,
    });
    expect(routeOption.value).toBe("canonical-key");
    fireEvent.change(routeProviderSelect, { target: { value: routeOption.value } });
    expect(dispatch).toHaveBeenCalledWith({
      type: "UPDATE_ROUTE",
      capKey: "speciation",
      field: "provider_id",
      value: "canonical-key",
    });
  });
});
