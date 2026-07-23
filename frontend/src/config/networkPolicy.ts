const LOOPBACK_HOST = "127.0.0.1";

interface NetworkEnvironment {
  ALLOW_LAN_ACCESS?: string;
  BACKEND_HOST?: string;
  FRONTEND_HOST?: string;
}

export interface FrontendNetworkPolicy {
  backendProxyHost: string;
  frontendHost: string;
  lanEnabled: boolean;
}

function normalizedHost(host: string): string {
  return host
    .trim()
    .toLowerCase()
    .replace(/^\[|\]$/g, "");
}

function isValidLoopbackIpv4(host: string): boolean {
  const octets = host.split(".");
  return (
    octets.length === 4 &&
    octets[0] === "127" &&
    octets.every((octet) => {
      if (!/^\d+$/.test(octet)) return false;
      const value = Number(octet);
      return value >= 0 && value <= 255;
    })
  );
}

export function isLoopbackHost(host: string): boolean {
  const normalized = normalizedHost(host);
  return (
    normalized === "localhost" ||
    normalized === "::1" ||
    normalized === "0:0:0:0:0:0:0:1" ||
    isValidLoopbackIpv4(normalized)
  );
}

export function assertFrontendBindHostAllowed(
  host: string | boolean | undefined,
  lanEnabled: boolean
): void {
  const isLoopback = host === undefined || host === false || (typeof host === "string" && isLoopbackHost(host));
  if (!lanEnabled && !isLoopback) {
    throw new Error(`Non-loopback binding requires ALLOW_LAN_ACCESS=true: ${String(host)}`);
  }
}

function readHost(value: string | undefined, name: string): string {
  if (value === undefined) return LOOPBACK_HOST;
  const host = value.trim();
  if (!host) throw new Error(`${name} must not be empty`);
  return host;
}

function proxyHostFor(backendHost: string): string {
  const normalized = normalizedHost(backendHost);
  if (normalized === "0.0.0.0" || normalized === "::") {
    return LOOPBACK_HOST;
  }
  return normalized.includes(":") ? `[${normalized}]` : backendHost;
}

export function resolveFrontendNetworkPolicy(env: NetworkEnvironment): FrontendNetworkPolicy {
  const backendHost = readHost(env.BACKEND_HOST, "BACKEND_HOST");
  const frontendHost = readHost(env.FRONTEND_HOST, "FRONTEND_HOST");
  const lanEnabled = env.ALLOW_LAN_ACCESS?.trim().toLowerCase() === "true";

  if (!lanEnabled) {
    assertFrontendBindHostAllowed(frontendHost, lanEnabled);
    if (!isLoopbackHost(backendHost)) {
      throw new Error(`Non-loopback binding requires ALLOW_LAN_ACCESS=true: ${backendHost}`);
    }
  }

  return {
    backendProxyHost: proxyHostFor(backendHost),
    frontendHost,
    lanEnabled,
  };
}
