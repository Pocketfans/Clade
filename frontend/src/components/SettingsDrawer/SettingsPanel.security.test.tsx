import { useState, type ComponentProps } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { UIConfig } from "@/services/api.types";
import { SettingsPanel } from "./SettingsPanel";

function makeConfig(overrides: Partial<UIConfig> = {}): UIConfig {
  return {
    providers: {
      main: {
        id: "main",
        name: "Main Provider",
        type: "openai",
        provider_type: "openai",
        base_url: "http://localhost:11434/v1",
        api_key: "",
        models: ["local-model"],
        selected_models: ["local-model"],
      },
    },
    capability_routes: {},
    allow_local_ai_endpoints: false,
    ...overrides,
  };
}

function renderPanel(onSave = vi.fn().mockResolvedValue(undefined), onClose = vi.fn()) {
  const config = makeConfig();
  return {
    config,
    onSave,
    onClose,
    ...render(<SettingsPanel config={config} onSave={onSave} onClose={onClose} />),
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

type SettingsOnSave = ComponentProps<typeof SettingsPanel>["onSave"];

function LifecycleHarness({ onSave }: { onSave: SettingsOnSave }) {
  const [open, setOpen] = useState(true);
  return open ? (
    <SettingsPanel config={makeConfig()} onSave={onSave} onClose={() => setOpen(false)} />
  ) : null;
}

async function startDeferredSecuritySave(
  user: ReturnType<typeof userEvent.setup>,
  onSave: SettingsOnSave
) {
  render(<LifecycleHarness onSave={onSave} />);
  await changeSecuritySetting(user);
  await act(async () => {
    await user.type(screen.getByLabelText("管理员令牌"), "admin-secret");
  });
  await save(user);
  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
}

async function changeSecuritySetting(user: ReturnType<typeof userEvent.setup>) {
  await act(async () => {
    await user.click(screen.getByRole("checkbox", { name: "允许访问本机 AI 服务" }));
  });
}

async function save(user: ReturnType<typeof userEvent.setup>) {
  await act(async () => {
    await user.click(screen.getByRole("button", { name: /保存配置/ }));
  });
}

describe("SettingsPanel local AI security lifecycle", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("saves a normal field change without token options", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderPanel(onSave);

    const nameInput = screen.getByPlaceholderText("输入便于识别的名称");
    await act(async () => {
      await user.clear(nameInput);
      await user.type(nameInput, "Renamed Provider");
    });
    await save(user);

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave.mock.calls[0]).toHaveLength(1);
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        providers: expect.objectContaining({
          main: expect.objectContaining({ name: "Renamed Provider" }),
        }),
      })
    );
  });

  it("blocks a security switch save without an administrator token", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderPanel(onSave);

    await changeSecuritySetting(user);
    await save(user);

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("请输入管理员令牌")).toBeInTheDocument();
  });

  it("passes the administrator token only as save options", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderPanel(onSave);

    await changeSecuritySetting(user);
    await act(async () => {
      await user.type(screen.getByLabelText("管理员令牌"), "admin-secret");
    });
    await save(user);

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ allow_local_ai_endpoints: true }),
      { adminToken: "admin-secret" }
    );
    expect(JSON.stringify(onSave.mock.calls[0][0])).not.toContain("admin-secret");
  });

  it("clears the administrator token after a successful save", async () => {
    const user = userEvent.setup();
    renderPanel();

    await changeSecuritySetting(user);
    const tokenInput = screen.getByLabelText("管理员令牌");
    await act(async () => {
      await user.type(tokenInput, "admin-secret");
    });
    await save(user);

    await waitFor(() => expect(tokenInput).toHaveValue(""));
  });

  it.each([
    [403, "admin_token_invalid", "管理员令牌不正确，请重新输入。"],
    [503, "admin_token_unconfigured", "服务端尚未配置 CLADE_ADMIN_TOKEN。"],
  ])(
    "clears the token and preserves the unsaved switch after a %i failure",
    async (status, code, guidance) => {
      const user = userEvent.setup();
      const error = Object.assign(new Error("request failed"), {
        status,
        statusText: "Save failed",
        detail: "unsafe raw detail",
        code,
      });
      const onSave = vi.fn().mockRejectedValue(error);
      renderPanel(onSave);

      await changeSecuritySetting(user);
      const tokenInput = screen.getByLabelText("管理员令牌");
      await act(async () => {
        await user.type(tokenInput, "admin-secret");
      });
      await save(user);

      await waitFor(() => expect(screen.getByText(guidance)).toBeInTheDocument());
      expect(tokenInput).toHaveValue("");
      expect(screen.getByRole("checkbox", { name: "允许访问本机 AI 服务" })).toBeChecked();
    }
  );

  it.each([
    [
      "cancel button",
      async (user: ReturnType<typeof userEvent.setup>) =>
        user.click(screen.getByRole("button", { name: "取消" })),
    ],
    [
      "overlay",
      async (user: ReturnType<typeof userEvent.setup>, container: HTMLElement) =>
        user.click(container.querySelector<HTMLElement>(".settings-panel")!),
    ],
    [
      "close button",
      async (user: ReturnType<typeof userEvent.setup>) =>
        user.click(screen.getByTitle("关闭 (Esc)")),
    ],
    ["Escape", async (user: ReturnType<typeof userEvent.setup>) => user.keyboard("{Escape}")],
  ])("clears the token through the %s close path", async (_name, close) => {
    const user = userEvent.setup();
    const { container, onClose } = renderPanel();
    await changeSecuritySetting(user);
    const tokenInput = screen.getByLabelText("管理员令牌");
    await act(async () => {
      await user.type(tokenInput, "admin-secret");
    });

    await act(async () => {
      await close(user, container);
    });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(tokenInput).toHaveValue("");
  });

  it("never writes the token to browser storage or the serialized config", async () => {
    const user = userEvent.setup();
    const localSetItem = vi.spyOn(window.localStorage, "setItem");
    const sessionSetItem = vi.spyOn(window.sessionStorage, "setItem");
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderPanel(onSave);

    await changeSecuritySetting(user);
    await act(async () => {
      await user.type(screen.getByLabelText("管理员令牌"), "admin-secret");
    });
    await save(user);

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(localSetItem).not.toHaveBeenCalled();
    expect(sessionSetItem).not.toHaveBeenCalled();
    expect(JSON.stringify(onSave.mock.calls[0][0])).not.toContain("admin-secret");
  });

  it("does not update state or schedule success work when a pending save resolves after close", async () => {
    const user = userEvent.setup();
    const pendingSave = deferred<void>();
    const onSave = vi.fn().mockReturnValue(pendingSave.promise);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    await startDeferredSecuritySave(user, onSave);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "取消" }));
    });
    expect(
      screen.queryByRole("checkbox", { name: "允许访问本机 AI 服务" })
    ).not.toBeInTheDocument();

    vi.useFakeTimers();
    await act(async () => {
      pendingSave.resolve();
      await pendingSave.promise;
    });

    expect(vi.getTimerCount()).toBe(0);
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("does not map errors or update state when a pending save rejects after close", async () => {
    const user = userEvent.setup();
    const pendingSave = deferred<void>();
    const onSave = vi.fn().mockReturnValue(pendingSave.promise);
    const statusRead = vi.fn(() => 403);
    const error = Object.assign(new Error("request failed"), {
      statusText: "Forbidden",
      code: "admin_token_invalid",
    });
    Object.defineProperty(error, "status", { get: statusRead });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    await startDeferredSecuritySave(user, onSave);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "取消" }));
    });
    await act(async () => {
      pendingSave.reject(error);
      try {
        await pendingSave.promise;
      } catch {
        // SettingsPanel owns the rejection and must ignore it after unmount.
      }
    });

    expect(statusRead).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
  });

  it("clears the save-success timer when the panel unmounts", async () => {
    const user = userEvent.setup();
    const pendingSave = deferred<void>();
    const onSave = vi.fn().mockReturnValue(pendingSave.promise);
    await startDeferredSecuritySave(user, onSave);

    vi.useFakeTimers();
    await act(async () => {
      pendingSave.resolve();
      await pendingSave.promise;
    });
    expect(vi.getTimerCount()).toBe(1);

    act(() => {
      screen.getByRole("button", { name: "取消" }).click();
    });

    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });
});
