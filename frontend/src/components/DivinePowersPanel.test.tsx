import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("@/services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/services/api")>();
  return {
    ...actual,
    http: {
      ...actual.http,
      get: apiMocks.get,
      post: apiMocks.post,
    },
  };
});

import { DivinePowersPanel } from "./DivinePowersPanel";

const selectedStatusResponse = {
  path: {
    path: "creator",
    name: "Creator",
    icon: "creator",
    description: "Create life",
    passive_bonus: "Lower creation cost",
    color: "#22c55e",
    skills: ["life_spark"],
    level: 1,
    experience: 10,
    next_level_exp: 100,
    unlocked_skills: ["life_spark"],
    secondary_path: null,
  },
  available_paths: null,
  faith: {
    total_followers: 0,
    total_faith: 0,
    faith_bonus_per_turn: 0,
    followers: [],
  },
  miracles: [],
  charging_miracle: null,
  wagers: {
    active_wagers: [],
    total_bet: 0,
    total_won: 0,
    total_lost: 0,
    net_profit: 0,
    consecutive_wins: 0,
    consecutive_losses: 0,
    faith_shaken_turns: 0,
    wager_types: [],
  },
  stats: {
    total_skills_used: 0,
    total_miracles_cast: 0,
  },
};

const skillsResponse = {
  skills: [
    {
      id: "life_spark",
      name: "Life Spark",
      path: "creator",
      description: "Create new life",
      cost: 10,
      cooldown: 1,
      unlock_level: 1,
      icon: "spark",
      unlocked: true,
      uses: 0,
      is_current_path: true,
    },
  ],
  current_path: "creator",
};

const miracleResponse = {
  id: "great_prosperity",
  name: "Great Prosperity",
  icon: "sparkle",
  description: "Boost global productivity",
  cost: 50,
  cooldown: 15,
  charge_turns: 1,
  one_time: false,
  current_cooldown: 0,
  is_charging: false,
  charge_progress: 0,
  available: true,
};

const miracleStatusResponse = {
  ...selectedStatusResponse,
  miracles: [miracleResponse],
};

const wagerTypeResponse = {
  type: "dominance",
  name: "Dominance",
  icon: "crown",
  description: "Predict ecological dominance",
  min_bet: 10,
  max_bet: 60,
  duration: 5,
  multiplier: 2,
};

const wagerStatusResponse = {
  ...selectedStatusResponse,
  wagers: {
    ...selectedStatusResponse.wagers,
    wager_types: [wagerTypeResponse],
  },
};

const activeWagerResponse = {
  id: "wager_5_0",
  wager_type: "dominance",
  target_species: "sp-alpha",
  secondary_species: null,
  bet_amount: 20,
  start_turn: 5,
  end_turn: 10,
  predicted_outcome: "",
  initial_state: { population: 1000 },
};

const activeWagerStatusResponse = {
  ...wagerStatusResponse,
  wagers: {
    ...wagerStatusResponse.wagers,
    active_wagers: [activeWagerResponse],
  },
};

const followerResponse = {
  lineage_code: "sp-alpha",
  common_name: "Alpha",
  faith_value: 12,
  contribution_per_turn: 2,
  turns_as_follower: 4,
  is_blessed: false,
  is_sanctified: false,
};

const blessStatusResponse = {
  ...selectedStatusResponse,
  faith: {
    ...selectedStatusResponse.faith,
    total_followers: 1,
    total_faith: 12,
    faith_bonus_per_turn: 2,
    followers: [followerResponse],
  },
};

const sanctifyStatusResponse = {
  ...blessStatusResponse,
  faith: {
    ...blessStatusResponse.faith,
    followers: [{ ...followerResponse, is_blessed: true }],
  },
};

function mockSelectedPathRequests(
  statusResponse: unknown = selectedStatusResponse,
) {
  apiMocks.get.mockImplementation(async (path: string) => {
    if (path === "/api/divine/status") {
      return statusResponse;
    }
    if (path === "/api/divine/skills") {
      return skillsResponse;
    }
    throw new Error(`Unexpected shared request: ${path}`);
  });
}

describe("DivinePowersPanel API boundary", () => {
  beforeEach(() => {
    apiMocks.post.mockReset();
    apiMocks.get.mockReset().mockResolvedValue({
      path: null,
      available_paths: [
        {
          path: "creator",
          name: "创造之神",
          icon: "🌱",
          description: "通过创造生命塑造世界",
          passive_bonus: "创造消耗降低",
          color: "#22c55e",
          skills: ["生命萌发"],
        },
      ],
      faith: {
        total_followers: 0,
        total_faith: 0,
        faith_bonus_per_turn: 0,
        followers: [],
      },
      miracles: [],
      charging_miracle: null,
      wagers: {
        active_wagers: [],
        total_bet: 0,
        total_won: 0,
        total_lost: 0,
        net_profit: 0,
        consecutive_wins: 0,
        consecutive_losses: 0,
        faith_shaken_turns: 0,
        wager_types: [],
      },
      stats: {
        total_skills_used: 0,
        total_miracles_cast: 0,
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads divine status through the shared HTTP client", async () => {
    const browserFetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/divine/status") {
        throw new Error("DivinePowersPanel must not fetch divine status directly");
      }
      if (url === "/api/divine/skills") {
        return {
          ok: true,
          json: async () => ({ skills: [] }),
        } as Response;
      }
      throw new Error(`Unexpected browser request: ${url}`);
    });
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith("/api/divine/status");
    });
    expect(await screen.findByText("选择你的神格")).toBeInTheDocument();
    const requestedUrls = browserFetch.mock.calls.map(([input]) => String(input));
    expect(requestedUrls).not.toContain("/api/divine/status");
  });

  it("loads divine skills through the shared HTTP client", async () => {
    mockSelectedPathRequests();
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not fetch divine skills directly"),
      );
    vi.stubGlobal("fetch", browserFetch);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith("/api/divine/status");
      expect(apiMocks.get).toHaveBeenCalledWith("/api/divine/skills");
    });
    expect(await screen.findByText("Life Spark")).toBeInTheDocument();
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("chooses a divine path through the shared HTTP client", async () => {
    apiMocks.post.mockResolvedValue({
      success: true,
      message: "Path chosen",
      path_info: {
        path: "creator",
        name: "Creator",
        icon: "creator",
        description: "Create life",
        passive_bonus: "Lower creation cost",
        color: "#22c55e",
        level: 1,
        experience: 0,
        next_level_exp: 100,
        unlocked_skills: ["life_spark"],
        secondary_path: null,
      },
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not choose a path directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("选择此神格"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/path/choose", {
        path: "creator",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Path chosen");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a divine path rejection returned by the shared HTTP client", async () => {
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Path already chosen"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "Path already chosen",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not choose a path directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("选择此神格"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/path/choose", {
        path: "creator",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Path already chosen");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("uses a divine skill through the shared HTTP client", async () => {
    mockSelectedPathRequests();
    apiMocks.post.mockResolvedValue({
      success: true,
      skill: "Life Spark",
      cost: 10,
      result: {
        effect: "executed",
        details: "Skill released",
      },
      energy_remaining: 90,
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not use a skill directly"),
      );
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("释放"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/skill/use", {
        skill_id: "life_spark",
        target: null,
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Skill released");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a divine skill rejection returned by the shared HTTP client", async () => {
    mockSelectedPathRequests();
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Not enough energy"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "Not enough energy",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not use a skill directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("释放"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/skill/use", {
        skill_id: "life_spark",
        target: null,
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Not enough energy");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("executes a divine miracle through the shared HTTP client", async () => {
    mockSelectedPathRequests(miracleStatusResponse);
    apiMocks.post.mockResolvedValue({
      success: true,
      message: "Miracle triggered",
      effect: {
        miracle_id: "great_prosperity",
        miracle_name: "Great Prosperity",
        miracle_icon: "sparkle",
        description: "Boost global productivity",
        cost: 50,
        turn_executed: 12,
      },
      miracle_summary: {
        all_miracles: [miracleResponse],
        miracles_cast: 1,
        charging: null,
        charge_progress: 0,
      },
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not execute a miracle directly"),
      );
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("神迹"));
    fireEvent.click(await screen.findByText("释放神迹"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/miracle/execute", {
        miracle_id: "great_prosperity",
        target: null,
      });
    });
    expect(alertMock).toHaveBeenCalledWith("神迹释放成功");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a divine miracle rejection returned by the shared HTTP client", async () => {
    mockSelectedPathRequests(miracleStatusResponse);
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Miracle is cooling down"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "Miracle is cooling down",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not execute a miracle directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("神迹"));
    fireEvent.click(await screen.findByText("释放神迹"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/miracle/execute", {
        miracle_id: "great_prosperity",
        target: null,
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Miracle is cooling down");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("places a divine wager through the shared HTTP client", async () => {
    mockSelectedPathRequests(wagerStatusResponse);
    apiMocks.post.mockResolvedValue({
      success: true,
      message: "Wager placed",
      wager_id: "wager_12_0",
      wager_type: "Dominance",
      potential_return: 40,
      energy_bet: 20,
      energy_remaining: 80,
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not place a wager directly"),
      );
    const promptMock = vi
      .fn()
      .mockReturnValueOnce("sp-alpha")
      .mockReturnValueOnce("20");
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("prompt", promptMock);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("预言"));
    fireEvent.click(await screen.findByText("下注"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/wager/place", {
        wager_type: "dominance",
        target_species: "sp-alpha",
        bet_amount: 20,
        secondary_species: null,
        predicted_outcome: "",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Wager placed\n潜在回报: 40 能量");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a divine wager placement rejection from the shared HTTP client", async () => {
    mockSelectedPathRequests(wagerStatusResponse);
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Not enough energy"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "Not enough energy",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not place a wager directly"),
      );
    vi.stubGlobal(
      "prompt",
      vi.fn().mockReturnValueOnce("sp-alpha").mockReturnValueOnce("20"),
    );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("预言"));
    fireEvent.click(await screen.findByText("下注"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/wager/place", {
        wager_type: "dominance",
        target_species: "sp-alpha",
        bet_amount: 20,
        secondary_species: null,
        predicted_outcome: "",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Not enough energy");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("adds a divine follower through the shared HTTP client", async () => {
    mockSelectedPathRequests();
    apiMocks.post.mockResolvedValue({
      success: true,
      message: "Follower added",
      faith_summary: selectedStatusResponse.faith,
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not add a follower directly"),
      );
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("sp-alpha"));
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("信仰"));
    fireEvent.click(await screen.findByText("添加信徒"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/faith/add", {
        lineage_code: "sp-alpha",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Follower added");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows an add-follower rejection from the shared HTTP client", async () => {
    mockSelectedPathRequests();
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Species not found"), {
        name: "ApiError",
        status: 404,
        statusText: "Not Found",
        detail: "Species not found",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not add a follower directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("missing"));
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("信仰"));
    fireEvent.click(await screen.findByText("添加信徒"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/faith/add", {
        lineage_code: "missing",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Species not found");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("blesses a divine follower through the shared HTTP client", async () => {
    mockSelectedPathRequests(blessStatusResponse);
    apiMocks.post.mockResolvedValue({
      success: true,
      message: "Follower blessed",
      reward: 5,
      faith_summary: {
        ...blessStatusResponse.faith,
        followers: [{ ...followerResponse, is_blessed: true }],
      },
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not bless a follower directly"),
      );
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("信仰"));
    fireEvent.click(await screen.findByText("显圣"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/faith/bless", {
        lineage_code: "sp-alpha",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Follower blessed");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a bless-follower rejection from the shared HTTP client", async () => {
    mockSelectedPathRequests(blessStatusResponse);
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Blessing unavailable"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "Blessing unavailable",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not bless a follower directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("信仰"));
    fireEvent.click(await screen.findByText("显圣"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/faith/bless", {
        lineage_code: "sp-alpha",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Blessing unavailable");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("sanctifies a blessed follower through the shared HTTP client", async () => {
    mockSelectedPathRequests(sanctifyStatusResponse);
    apiMocks.post.mockResolvedValue({
      success: true,
      message: "Species sanctified",
      faith_summary: {
        ...sanctifyStatusResponse.faith,
        followers: [
          { ...followerResponse, is_blessed: true, is_sanctified: true },
        ],
      },
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not sanctify a follower directly"),
      );
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("信仰"));
    fireEvent.click(await screen.findByText("圣化"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/faith/sanctify", {
        lineage_code: "sp-alpha",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Species sanctified");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a sanctify-follower rejection from the shared HTTP client", async () => {
    mockSelectedPathRequests(sanctifyStatusResponse);
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Sanctification unavailable"), {
        name: "ApiError",
        status: 400,
        statusText: "Bad Request",
        detail: "Sanctification unavailable",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not sanctify a follower directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("信仰"));
    fireEvent.click(await screen.findByText("圣化"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/faith/sanctify", {
        lineage_code: "sp-alpha",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Sanctification unavailable");
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("checks a divine wager through the shared HTTP client", async () => {
    mockSelectedPathRequests(activeWagerStatusResponse);
    apiMocks.post.mockResolvedValue({
      status: "resolved",
      success: true,
      reason: "已成为霸主",
      reward: 40,
      current_energy: 120,
      wager_summary: {
        ...activeWagerStatusResponse.wagers,
        active_wagers: [],
        total_won: 40,
        net_profit: 20,
      },
    });
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not check a wager directly"),
      );
    const alertMock = vi.fn();
    const energyChanged = vi.fn();
    window.addEventListener("energy-changed", energyChanged, { once: true });
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("预言"));
    fireEvent.click(await screen.findByText("检查"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/wager/check", {
        wager_id: "wager_5_0",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("预言成功！已成为霸主\n获得 40 能量");
    const statusRequests = apiMocks.get.mock.calls.filter(
      ([path]) => path === "/api/divine/status",
    );
    expect(statusRequests).toHaveLength(2);
    expect(energyChanged).toHaveBeenCalledTimes(1);
    expect(browserFetch).not.toHaveBeenCalled();
  });

  it("shows a wager-check rejection from the shared HTTP client", async () => {
    mockSelectedPathRequests(activeWagerStatusResponse);
    apiMocks.post.mockRejectedValue(
      Object.assign(new Error("Request failed: Wager not found"), {
        name: "ApiError",
        status: 404,
        statusText: "Not Found",
        detail: "Wager not found",
      }),
    );
    const browserFetch = vi
      .fn()
      .mockRejectedValue(
        new Error("DivinePowersPanel must not check a wager directly"),
      );
    const alertMock = vi.fn();
    vi.stubGlobal("fetch", browserFetch);
    vi.stubGlobal("alert", alertMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(<DivinePowersPanel onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText("预言"));
    fireEvent.click(await screen.findByText("检查"));
    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith("/api/divine/wager/check", {
        wager_id: "wager_5_0",
      });
    });
    expect(alertMock).toHaveBeenCalledWith("Wager not found");
    expect(browserFetch).not.toHaveBeenCalled();
  });
});
