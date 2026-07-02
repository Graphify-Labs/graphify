import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";

export type PlatformCandidates = {
  darwin?: string[];
  win32?: string[];
  default: string[];
};

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout> | null;
};

type CdpSendOptions = {
  sessionId?: string;
  timeoutMs?: number;
};

type FetchJsonOptions = {
  timeoutMs?: number;
};

type FindChromeExecutableOptions = {
  candidates: PlatformCandidates;
  envNames?: string[];
};

type ResolveSharedChromeProfileDirOptions = {
  envNames?: string[];
  appDataDirName?: string;
  profileDirName?: string;
  wslWindowsHome?: string | null;
};

type FindExistingChromeDebugPortOptions = {
  profileDir: string;
  timeoutMs?: number;
};

export type ChromeChannel = "stable" | "beta" | "canary" | "dev";

export type DiscoveredChrome = {
  port: number;
  wsUrl: string;
};

type DiscoverRunningChromeOptions = {
  channels?: ChromeChannel[];
  userDataDirs?: string[];
  timeoutMs?: number;
};

type LaunchChromeOptions = {
  chromePath: string;
  profileDir: string;
  port: number;
  url?: string;
  headless?: boolean;
  extraArgs?: string[];
};

type ChromeTargetInfo = {
  targetId: string;
  url: string;
  type: string;
};

type OpenPageSessionOptions = {
  cdp: CdpConnection;
  reusing: boolean;
  url: string;
  matchTarget: (target: ChromeTargetInfo) => boolean;
  enablePage?: boolean;
  enableRuntime?: boolean;
  enableDom?: boolean;
  enableNetwork?: boolean;
  activateTarget?: boolean;
};

export type PageSession = {
  sessionId: string;
  targetId: string;
  createdTarget: boolean;
};

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function getFreePort(fixedEnvName?: string): Promise<number> {
  const fixed = fixedEnvName ? Number.parseInt(process.env[fixedEnvName] ?? "", 10) : NaN;
  if (Number.isInteger(fixed) && fixed > 0) return fixed;

  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close(() => reject(new Error("Unable to allocate a free TCP port.")));
        return;
      }
      const port = address.port;
      server.close((err) => {
        if (err) reject(err);
        else resolve(port);
      });
    });
  });
}

export function findChromeExecutable(options: FindChromeExecutableOptions): string | undefined {
  for (const envName of options.envNames ?? []) {
    const override = process.env[envName]?.trim();
    if (override && fs.existsSync(override)) return override;
  }

  const candidates = process.platform === "darwin"
    ? options.candidates.darwin ?? options.candidates.default
    : process.platform === "win32"
      ? options.candidates.win32 ?? options.candidates.default
      : options.candidates.default;

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return undefined;
}

export function resolveSharedChromeProfileDir(options: ResolveSharedChromeProfileDirOptions = {}): string {
  for (const envName of options.envNames ?? []) {
    const override = process.env[envName]?.trim();
    if (override) return path.resolve(override);
  }

  const appDataDirName = options.appDataDirName ?? "baoyu-skills";
  const profileDirName = options.profileDirName ?? "chrome-profile";

  if (options.wslWindowsHome) {
    return path.join(options.wslWindowsHome, ".local", "share", appDataDirName, profileDirName);
  }

  const base = process.platform === "darwin"
    ? path.join(os.homedir(), "Library", "Application Support")
    : process.platform === "win32"
      ? (process.env.APPDATA ?? path.join(os.homedir(), "AppData", "Roaming"))
      : (process.env.XDG_DATA_HOME ?? path.join(os.homedir(), ".local", "share"));
  return path.join(base, appDataDirName, profileDirName);
}

async function fetchWithTimeout(url: string, timeoutMs?: number): Promise<Response> {
  if (!timeoutMs || timeoutMs <= 0) return await fetch(url, { redirect: "follow" });

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    return await fetch(url, { redirect: "follow", signal: ctl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson<T = unknown>(url: string, options: FetchJsonOptions = {}): Promise<T> {
  const response = await fetchWithTimeout(url, options.timeoutMs);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return await response.json() as T;
}

async function isDebugPortReady(port: number, timeoutMs = 3_000): Promise<boolean> {
  try {
    const version = await fetchJson<{ webSocketDebuggerUrl?: string }>(
      `http://127.0.0.1:${port}/json/version`,
      { timeoutMs }
    );
    return !!version.webSocketDebuggerUrl;
  } catch {
    return false;
  }
}

function isPortListening(port: number, timeoutMs = 3_000): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const timer = setTimeout(() => { socket.destroy(); resolve(false); }, timeoutMs);
    socket.once("connect", () => { clearTimeout(timer); socket.destroy(); resolve(true); });
    socket.once("error", () => { clearTimeout(timer); resolve(false); });
    socket.connect(port, "127.0.0.1");
  });
}

function parseDevToolsActivePort(filePath: string): { port: number; wsPath: string } | null {
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const lines = content.split(/\r?\n/);
    const port = Number.parseInt(lines[0]?.trim() ?? "", 10);
    const wsPath = lines[1]?.trim();
    if (port > 0 && wsPath) return { port, wsPath };
  } catch {}
  return null;
}

export async function findExistingChromeDebugPort(options: FindExistingChromeDebugPortOptions): Promise<number | null> {
  const timeoutMs = options.timeoutMs ?? 3_000;
  const parsed = parseDevToolsActivePort(path.join(options.profileDir, "DevToolsActivePort"));

  if (parsed && parsed.port > 0 && await isDebugPortReady(parsed.port, timeoutMs)) return parsed.port;

  if (process.platform === "win32") return null;

  try {
    const result = spawnSync("ps", ["aux"], { encoding: "utf-8", timeout: 5_000 });
    if (result.status !== 0 || !result.stdout) return null;

    const lines = result.stdout
      .split("\n")
      .filter((line) => line.includes(options.profileDir) && line.includes("--remote-debugging-port="));

    for (const line of lines) {
      const portMatch = line.match(/--remote-debugging-port=(\d+)/);
      const port = Number.parseInt(portMatch?.[1] ?? "", 10);
      if (port > 0 && await isDebugPortReady(port, timeoutMs)) return port;
    }
  } catch {}

  return null;
}

export function getDefaultChromeUserDataDirs(channels: ChromeChannel[] = ["stable"]): string[] {
  const home = os.homedir();
  const dirs: string[] = [];

  const channelDirs: Record<string, { darwin: string; linux: string; win32: string }> = {
    stable: {
      darwin: path.join(home, "Library", "Application Support", "Google", "Chrome"),
      linux: path.join(home, ".config", "google-chrome"),
      win32: path.join(process.env.LOCALAPPDATA ?? path.join(home, "AppData", "Local"), "Google", "Chrome", "User Data"),
    },
    beta: {
      darwin: path.join(home, "Library", "Application Support", "Google", "Chrome Beta"),
      linux: path.join(home, ".config", "google-chrome-beta"),
      win32: path.join(process.env.LOCALAPPDATA ?? path.join(home, "AppData", "Local"), "Google", "Chrome Beta", "User Data"),
    },
    canary: {
      darwin: path.join(home, "Library", "Application Support", "Google", "Chrome Canary"),
      linux: path.join(home, ".config", "google-chrome-canary"),
      win32: path.join(process.env.LOCALAPPDATA ?? path.join(home, "AppData", "Local"), "Google", "Chrome SxS", "User Data"),
    },
    dev: {
      darwin: path.join(home, "Library", "Application Support", "Google", "Chrome Dev"),
      linux: path.join(home, ".config", "google-chrome-dev"),
      win32: path.join(process.env.LOCALAPPDATA ?? path.join(home, "AppData", "Local"), "Google", "Chrome Dev", "User Data"),
    },
  };

  const platform = process.platform === "darwin" ? "darwin" : process.platform === "win32" ? "win32" : "linux";

  for (const ch of channels) {
    const entry = channelDirs[ch];
    if (entry) dirs.push(entry[platform]);
  }

  return dirs;
}

// Best-effort reuse of an already-running local CDP session discovered from
// known Chrome user-data dirs. This is distinct from Chrome DevTools MCP's
// prompt-based --autoConnect flow.
export async function discoverRunningChromeDebugPort(options: DiscoverRunningChromeOptions = {}): Promise<DiscoveredChrome | null> {
  const channels = options.channels ?? ["stable", "beta", "canary", "dev"];
  const timeoutMs = options.timeoutMs ?? 3_000;

  const userDataDirs = (options.userDataDirs ?? getDefaultChromeUserDataDirs(channels))
    .map((dir) => path.resolve(dir));
  for (const dir of userDataDirs) {
    const parsed = parseDevToolsActivePort(path.join(dir, "DevToolsActivePort"));
    if (!parsed) continue;
    if (await isPortListening(parsed.port, timeoutMs)) {
      return { port: parsed.port, wsUrl: `ws://127.0.0.1:${parsed.port}${parsed.wsPath}` };
    }
  }

  if (process.platform !== "win32") {
    try {
      const result = spawnSync("ps", ["aux"], { encoding: "utf-8", timeout: 5_000 });
      if (result.status === 0 && result.stdout) {
        const lines = result.stdout
          .split("\n")
          .filter((line) =>
            line.includes("--remote-debugging-port=") &&
            userDataDirs.some((dir) => line.includes(dir))
          );

        for (const line of lines) {
          const portMatch = line.match(/--remote-debugging-port=(\d+)/);
          const port = Number.parseInt(portMatch?.[1] ?? "", 10);
          if (port > 0 && await isDebugPortReady(port, timeoutMs)) {
            try {
              const version = await fetchJson<{ webSocketDebuggerUrl?: string }>(`http://127.0.0.1:${port}/json/version`, { timeoutMs });
              if (version.webSocketDebuggerUrl) return { port, wsUrl: version.webSocketDebuggerUrl };
            } catch {}
          }
        }
      }
    } catch {}
  }

  return null;
}

export async function waitForChromeDebugPort(
  port: number,
  timeoutMs: number,
  options?: { includeLastError?: boolean }
): Promise<string> {
  const start = Date.now();
  let lastError: unknown = null;

  while (Date.now() - start < timeoutMs) {
    try {
      const version = await fetchJson<{ webSocketDebuggerUrl?: string }>(
        `http://127.0.0.1:${port}/json/version`,
        { timeoutMs: 5_000 }
      );
      if (version.webSocketDebuggerUrl) return version.webSocketDebuggerUrl;
      lastError = new Error("Missing webSocketDebuggerUrl");
    } catch (error) {
      lastError = error;
    }
    await sleep(200);
  }

  if (options?.includeLastError && lastError) {
    throw new Error(
      `Chrome debug port not ready: ${lastError instanceof Error ? lastError.message : String(lastError)}`
    );
  }
  throw new Error("Chrome debug port not ready");
}

export class CdpConnection {
  private ws: WebSocket;
  private nextId = 0;
  private pending = new Map<number, PendingRequest>();
  private eventHandlers = new Map<string, Set<(params: unknown) => void>>();
  private defaultTimeoutMs: number;

  private constructor(ws: WebSocket, defaultTimeoutMs = 15_000) {
    this.ws = ws;
    this.defaultTimeoutMs = defaultTimeoutMs;

    this.ws.addEventListener("message", (event) => {
      try {
        const data = typeof event.data === "string"
          ? event.data
          : new TextDecoder().decode(event.data as ArrayBuffer);
        const msg = JSON.parse(data) as {
          id?: number;
          method?: string;
          params?: unknown;
          result?: unknown;
          error?: { message?: string };
        };

        if (msg.method) {
          const handlers = this.eventHandlers.get(msg.method);
          if (handlers) {
            handlers.forEach((handler) => handler(msg.params));
          }
        }

        if (msg.id) {
          const pending = this.pending.get(msg.id);
          if (pending) {
            this.pending.delete(msg.id);
            if (pending.timer) clearTimeout(pending.timer);
            if (msg.error?.message) pending.reject(new Error(msg.error.message));
            else pending.resolve(msg.result);
          }
        }
      } catch {}
    });

    this.ws.addEventListener("close", () => {
      for (const [id, pending] of this.pending.entries()) {
        this.pending.delete(id);
        if (pending.timer) clearTimeout(pending.timer);
        pending.reject(new Error("CDP connection closed."));
      }
    });
  }

  static async connect(
    url: string,
    timeoutMs: number,
    options?: { defaultTimeoutMs?: number }
  ): Promise<CdpConnection> {
    const ws = new WebSocket(url);
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("CDP connection timeout.")), timeoutMs);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      });
      ws.addEventListener("error", () => {
        clearTimeout(timer);
        reject(new Error("CDP connection failed."));
      });
    });
    return new CdpConnection(ws, options?.defaultTimeoutMs ?? 15_000);
  }

  on(method: string, handler: (params: unknown) => void): void {
    if (!this.eventHandlers.has(method)) {
      this.eventHandlers.set(method, new Set());
    }
    this.eventHandlers.get(method)?.add(handler);
  }

  off(method: string, handler: (params: unknown) => void): void {
    this.eventHandlers.get(method)?.delete(handler);
  }

  async send<T = unknown>(method: string, params?: Record<string, unknown>, options?: CdpSendOptions): Promise<T> {
    const id = ++this.nextId;
    const message: Record<string, unknown> = { id, method };
    if (params) message.params = params;
    if (options?.sessionId) message.sessionId = options.sessionId;

    const timeoutMs = options?.timeoutMs ?? this.defaultTimeoutMs;
    const result = await new Promise<unknown>((resolve, reject) => {
      const timer = timeoutMs > 0
        ? setTimeout(() => {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }, timeoutMs)
        : null;
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify(message));
    });

    return result as T;
  }

  close(): void {
    try {
      this.ws.close();
    } catch {}
  }
}

export async function launchChrome(options: LaunchChromeOptions): Promise<ChildProcess> {
  await fs.promises.mkdir(options.profileDir, { recursive: true });

  const args = [
    `--remote-debugging-port=${options.port}`,
    `--user-data-dir=${options.profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    ...(options.extraArgs ?? []),
  ];
  if (options.headless) args.push("--headless=new");
  if (options.url) args.push(options.url);

  return spawn(options.chromePath, args, { stdio: "ignore" });
}

export function killChrome(chrome: ChildProcess): void {
  try {
    chrome.kill("SIGTERM");
  } catch {}
  setTimeout(() => {
    if (!chrome.killed) {
      try {
        chrome.kill("SIGKILL");
      } catch {}
    }
  }, 2_000).unref?.();
}

export async function openPageSession(options: OpenPageSessionOptions): Promise<PageSession> {
  let targetId: string;
  let createdTarget = false;

  if (options.reusing) {
    const created = await options.cdp.send<{ targetId: string }>("Target.createTarget", { url: options.url });
    targetId = created.targetId;
    createdTarget = true;
  } else {
    const targets = await options.cdp.send<{ targetInfos: ChromeTargetInfo[] }>("Target.getTargets");
    const existing = targets.targetInfos.find(options.matchTarget);
    if (existing) {
      targetId = existing.targetId;
    } else {
      const created = await options.cdp.send<{ targetId: string }>("Target.createTarget", { url: options.url });
      targetId = created.targetId;
      createdTarget = true;
    }
  }

  const { sessionId } = await options.cdp.send<{ sessionId: string }>(
    "Target.attachToTarget",
    { targetId, flatten: true }
  );

  if (options.activateTarget ?? true) {
    await options.cdp.send("Target.activateTarget", { targetId });
  }
  if (options.enablePage) await options.cdp.send("Page.enable", {}, { sessionId });
  if (options.enableRuntime) await options.cdp.send("Runtime.enable", {}, { sessionId });
  if (options.enableDom) await options.cdp.send("DOM.enable", {}, { sessionId });
  if (options.enableNetwork) await options.cdp.send("Network.enable", {}, { sessionId });

  return { sessionId, targetId, createdTarget };
}
