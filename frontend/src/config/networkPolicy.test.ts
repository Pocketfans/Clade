import { spawn, spawnSync } from "child_process";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import path from "path";
import { describe, expect, it } from "vitest";

const NETWORK_ENV_KEYS = ["ALLOW_LAN_ACCESS", "BACKEND_HOST", "FRONTEND_HOST"] as const;

type NetworkEnv = Partial<Record<(typeof NETWORK_ENV_KEYS)[number], string>>;

const LOAD_CONFIG_SCRIPT = `
  import { loadConfigFromFile } from "vite";
  const loaded = await loadConfigFromFile(
    { command: "serve", mode: "test" },
    "vite.config.ts",
  );
  if (!loaded) throw new Error("Vite configuration did not load");
  const server = loaded.config.server;
  console.log(JSON.stringify({
    host: server.host,
    target: server.proxy["/api"].target,
  }));
`;

function loadServerConfig(overrides: NetworkEnv) {
  const env = { ...process.env };
  for (const key of NETWORK_ENV_KEYS) {
    delete env[key];
  }
  Object.assign(env, overrides);

  const result = spawnSync(process.execPath, ["--input-type=module", "-e", LOAD_CONFIG_SCRIPT], {
    cwd: process.cwd(),
    encoding: "utf8",
    env,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout).trim());
  }
  return JSON.parse(result.stdout) as { host: string; target: string };
}

interface ViteCliResult {
  exitCode: number | null;
  output: string;
  startedListening: boolean;
}

type ViteCommand = "dev" | "preview";

function createPreviewFixture(): string {
  const fixtureRoot = mkdtempSync(path.join(tmpdir(), "clade-vite-preview-"));
  try {
    writeFileSync(
      path.join(fixtureRoot, "index.html"),
      "<!doctype html><title>Clade preview test</title>",
      "utf8"
    );
    return fixtureRoot;
  } catch (error) {
    rmSync(fixtureRoot, { recursive: true, force: true });
    throw error;
  }
}

function runViteCli(
  command: ViteCommand,
  hostArgs: string[],
  overrides: NetworkEnv
): Promise<ViteCliResult> {
  const env = { ...process.env };
  for (const key of NETWORK_ENV_KEYS) {
    delete env[key];
  }
  Object.assign(env, overrides);

  const viteCli = path.resolve(process.cwd(), "node_modules/vite/bin/vite.js");
  const testPort = String(40_000 + Math.floor(Math.random() * 10_000));
  const previewFixture = command === "preview" ? createPreviewFixture() : null;
  const previewArgs = previewFixture
    ? ["preview", "--outDir", previewFixture]
    : [];

  return new Promise((resolve, reject) => {
    const cleanupPreviewFixture = () => {
      if (previewFixture) {
        rmSync(previewFixture, { recursive: true, force: true });
      }
    };
    let child;
    try {
      child = spawn(
        process.execPath,
        [
          viteCli,
          ...previewArgs,
          ...hostArgs,
          "--port",
          testPort,
          "--strictPort",
          "--clearScreen",
          "false",
        ],
        {
          cwd: process.cwd(),
          env,
          stdio: ["ignore", "pipe", "pipe"],
        }
      );
    } catch (error) {
      cleanupPreviewFixture();
      reject(error);
      return;
    }
    let output = "";
    let startedListening = false;
    let timedOut = false;

    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, 12_000);

    const capture = (chunk: Buffer) => {
      output += chunk.toString("utf8");
      const plainOutput = output
        .split(String.fromCharCode(27))
        .join("")
        .replace(/\[[0-9;]*m/g, "");
      if (/(?:ready in|Local:)/i.test(plainOutput) && !startedListening) {
        startedListening = true;
        child.kill();
      }
    };

    child.stdout.on("data", capture);
    child.stderr.on("data", capture);
    child.on("error", (error) => {
      clearTimeout(timeout);
      cleanupPreviewFixture();
      reject(error);
    });
    child.on("close", (exitCode) => {
      clearTimeout(timeout);
      cleanupPreviewFixture();
      if (timedOut) {
        reject(new Error(`Vite CLI did not settle before timeout:\n${output}`));
        return;
      }
      resolve({ exitCode, output, startedListening });
    });
  });
}

describe("Vite network policy", () => {
  it("rejects a non-loopback frontend host without LAN opt-in", () => {
    expect(() => loadServerConfig({ FRONTEND_HOST: "0.0.0.0" })).toThrow("ALLOW_LAN_ACCESS=true");
  });

  it("allows a non-loopback frontend host with LAN opt-in", () => {
    const config = loadServerConfig({
      ALLOW_LAN_ACCESS: "true",
      FRONTEND_HOST: "0.0.0.0",
    });

    expect(config.host).toBe("0.0.0.0");
  });

  it.each(["0.0.0.0", "::"])(
    "maps wildcard backend host %s to a loopback proxy target",
    (backendHost) => {
      const config = loadServerConfig({
        ALLOW_LAN_ACCESS: "true",
        BACKEND_HOST: backendHost,
      });

      expect(config.target).toBe("http://127.0.0.1:8022");
    }
  );

  it("uses a specific LAN backend address as the proxy target", () => {
    const config = loadServerConfig({
      ALLOW_LAN_ACCESS: "true",
      BACKEND_HOST: "192.168.1.25",
    });

    expect(config.target).toBe("http://192.168.1.25:8022");
  });

  it.each([
    ["an explicit wildcard", ["--host", "0.0.0.0"]],
    ["the boolean wildcard", ["--host"]],
  ])(
    "rejects %s from the real Vite CLI before listening without LAN opt-in",
    async (_label, hostArgs) => {
      const result = await runViteCli("dev", hostArgs, {});

      expect(result.startedListening).toBe(false);
      expect(result.exitCode).not.toBe(0);
      expect(result.output).toContain("ALLOW_LAN_ACCESS=true");
    },
    15_000
  );

  it(
    "allows a real Vite CLI wildcard when LAN access is explicitly enabled",
    async () => {
      const result = await runViteCli("dev", ["--host", "0.0.0.0"], {
        ALLOW_LAN_ACCESS: "true",
      });

      expect(result.startedListening).toBe(true);
      expect(result.output).not.toContain("Non-loopback binding requires");
    },
    15_000
  );

  it.each([
    ["an explicit wildcard", ["--host", "0.0.0.0"]],
    ["the boolean wildcard", ["--host"]],
  ])(
    "rejects preview %s before listening without LAN opt-in",
    async (_label, hostArgs) => {
      const result = await runViteCli("preview", hostArgs, {});

      expect(result.startedListening).toBe(false);
      expect(result.exitCode).not.toBe(0);
      expect(result.output).toContain("ALLOW_LAN_ACCESS=true");
    },
    15_000
  );

  it(
    "allows a preview wildcard when LAN access is explicitly enabled",
    async () => {
      const result = await runViteCli("preview", ["--host", "0.0.0.0"], {
        ALLOW_LAN_ACCESS: "true",
      });

      expect(result.startedListening).toBe(true);
      expect(result.output).not.toContain("Non-loopback binding requires");
    },
    15_000
  );
});
