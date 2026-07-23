import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GameEvent } from "@/services/api";

const apiMocks = vi.hoisted(() => ({
  connectToEventStream: vi.fn(),
  abortCurrentTasks: vi.fn(),
  skipCurrentAIStep: vi.fn(),
}));

vi.mock("@/services/api", () => apiMocks);

import { TurnProgressOverlay } from "./TurnProgressOverlay";

let eventCallback: ((event: GameEvent) => void) | undefined;

function emitEvent(event: GameEvent) {
  if (!eventCallback) {
    throw new Error("Event stream callback was not registered");
  }
  eventCallback(event);
}

describe("TurnProgressOverlay interrupted AI stream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    apiMocks.connectToEventStream.mockImplementation(
      (callback: (event: GameEvent) => void) => {
        eventCallback = callback;
        return { close: vi.fn() } as unknown as EventSource;
      }
    );
  });

  afterEach(() => {
    cleanup();
    eventCallback = undefined;
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("keeps partial text and shows an interrupted stream as a fallback warning", () => {
    render(<TurnProgressOverlay />);

    act(() => {
      emitEvent({ type: "narrative_token", message: "已经显示的片段" });
      emitEvent({
        type: "ai_progress",
        total: 2,
        completed: 1,
        current_task: "回合报告",
      });
      emitEvent({
        type: "ai_stream_interrupted",
        task: "回合报告",
        message: "回合报告 interrupted",
        category: "AI",
      });
    });

    expect(screen.getByText("AI 生成中断，已使用备用结果")).toBeInTheDocument();
    expect(screen.getByText("已经显示的片段")).toBeInTheDocument();
    expect(screen.getByText("1/2")).toBeInTheDocument();
    expect(screen.queryByText("✅ 完成: 回合报告")).not.toBeInTheDocument();
    expect(screen.getByText("等待响应")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2_500);
    });
    expect(screen.getByText("等待响应")).toBeInTheDocument();
  });
});
