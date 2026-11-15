import { execFile } from "node:child_process";
import { accessSync, constants, existsSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

// One extension for both Pi and Oh My Pi (OMP). It imports only Node built-ins:
// the wheel ships no node_modules, and the two hosts provide different packages
// (@earendil-works/pi-coding-agent vs @oh-my-pi/pi-coding-agent), so path and
// URL handling are implemented locally below.

const INPUT_LIMIT = 256 * 1024;
const OUTPUT_LIMIT = 64 * 1024;
const TIMEOUT_MS = 2000;
// Host tool name -> the Claude Code tool name hook-guard expects. OMP has `glob`
// (its `path` is the pattern); Pi has `find` (`pattern` relative to `path`). OMP's
// own `find` is a semantic search without `pattern`, so it is left alone.
const TOOL_NAMES = { bash: "Bash", grep: "Grep", read: "Read", glob: "Glob", find: "Glob" } as const;
const FILE_URL_RE = /^file:\/\//i;
// A URL or host-internal resource (https://, skill://, local:/, artifact://):
// a scheme of 2+ characters followed by a slash. Two characters keep a Windows
// drive (C:/) out; the slash keeps a read selector (source.py:12) out.
const SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]+:\//;
// OMP read selectors after a path: `:50`, `:50-80`, `:5-16,960-973`, `:raw`, `:-60`.
const SELECTOR_RE = /^(.+?)((?::[^:\\/]+)+)$/;

type HostEvent = { toolName: string; input: Record<string, unknown> };
type HostContext = {
  cwd: string;
  signal?: AbortSignal;
  isProjectTrusted?: () => boolean;
  sessionManager: { getSessionId(): string };
};
type HostAPI = {
  on(event: string, handler: (event: never, ctx: HostContext) => unknown): void;
  sendMessage?(message: { customType: string; content: string; display: boolean }, options: { deliverAs: "steer" }): void;
  // Present only on OMP, which hands extensions its own module.
  pi?: unknown;
};

// RFC 8089 / Node's url.fileURLToPath: a file:// URL is local only when its
// authority is empty or `localhost`. Any other authority names a remote host,
// so `file://evil.com/<in-project path>` cannot alias a real local file.
function isRemote(path: string): boolean {
  if (FILE_URL_RE.test(path)) {
    try {
      const { hostname } = new URL(path);
      return !(hostname === "" || hostname.toLowerCase() === "localhost");
    } catch {
      return true;
    }
  }
  return SCHEME_RE.test(path) || /^www\./i.test(path) || path.includes("://");
}

// A local target as an absolute path, normalized the way Pi's tools do (leading
// `@` dropped, `~` expanded). A literal file wins over a selector reading, so a
// file really named `source.py:12` is not truncated.
function localPath(value: string, cwd: string, selectors: boolean): string {
  if (value.startsWith("@")) value = value.slice(1);
  if (value === "~" || value.startsWith("~/")) value = join(homedir(), value.slice(2));
  if (FILE_URL_RE.test(value)) return fileURLToPath(value.replace(/^file:\/\/localhost/i, "file://"));
  const literal = resolve(cwd, value);
  if (!selectors || existsSync(literal)) return literal;
  const match = SELECTOR_RE.exec(value);
  return match ? resolve(cwd, match[1]) : literal;
}

function which(name: string, path: string): string | undefined {
  const exts = process.platform === "win32" ? (process.env.PATHEXT ?? ".EXE;.CMD;.BAT").split(";") : [""];
  for (const dir of path.split(delimiter)) {
    for (const ext of exts) {
      const candidate = join(dir, name + ext);
      try {
        if (!statSync(candidate).isFile()) continue;
        accessSync(candidate, constants.X_OK);
        return candidate;
      } catch {
        // not here, or not executable
      }
    }
  }
}

// The first absolute PATH entry whose `graphify` lives outside the project. The
// PATH entry itself is returned, not its realpath: a shim may dispatch on argv[0].
function installedCommand(cwd: string): string | undefined {
  const project = realpathSync(cwd);
  for (const dir of (process.env.PATH ?? "").split(delimiter).filter(isAbsolute)) {
    const found = which("graphify", dir);
    if (!found) continue;
    const within = relative(project, realpathSync(found));
    if (within.startsWith(`..${sep}`) || isAbsolute(within)) return found;
  }
}

function runGuard(command: string, kind: string, payload: string, cwd: string, signal: AbortSignal, timeout: number, maxBuffer: number): Promise<string | undefined> {
  if (Buffer.byteLength(payload) > INPUT_LIMIT || signal.aborted) return Promise.resolve(undefined);
  const { promise, resolve: done } = Promise.withResolvers<string | undefined>();
  const child = execFile(command, ["hook-guard", kind], {
    cwd, encoding: "utf8", timeout, killSignal: "SIGKILL", maxBuffer, signal,
    env: { ...process.env, CLAUDE_PROJECT_DIR: cwd },
  }, (error, stdout) => done(error ? undefined : stdout.trim() || undefined));
  child.stdin?.on("error", () => {});
  child.stdin?.end(payload);
  return promise;
}

export default function graphify(api: HostAPI): void {
  // OMP delivers `additionalContext` from tool_call as a separate passive
  // developer message after the batch: deduplicated, dropped for denied or
  // failed calls, and shown on the tool card. Pi has no such channel, so it
  // gets the same text as a steering message, delivered after the tool batch
  // and before the next model call. Either way raw tool output stays untouched,
  // so a file or command cannot forge this instruction channel. Both hosts send
  // it as unlabelled user text, so it is wrapped the way Claude Code labels
  // PreToolUse context; bare text reads as noise and agents ignore it.
  const passive = typeof api.pi === "object" && api.pi !== null;
  let controller = new AbortController();
  const reset = () => {
    controller.abort();
    controller = new AbortController();
  };
  // session_switch and session_branch exist only on OMP; Pi reloads extensions
  // and emits session_shutdown + session_start instead.
  for (const event of ["session_start", "session_switch", "session_branch", "session_tree", "session_shutdown", "before_agent_start"]) {
    api.on(event, reset);
  }

  api.on("tool_call", async (event: HostEvent, ctx: HostContext) => {
    const trusted = () => ctx.isProjectTrusted?.() ?? true;
    const signal = ctx.signal ? AbortSignal.any([controller.signal, ctx.signal]) : controller.signal;
    const deadline = performance.now() + TIMEOUT_MS;
    const contexts: string[] = [];
    try {
      if (!trusted()) { reset(); return; }
      if (!Object.hasOwn(TOOL_NAMES, event.toolName)) return;
      if (event.toolName === "find" && typeof event.input.pattern !== "string") return;
      const command = installedCommand(ctx.cwd);
      if (!command) return;
      const toolName = TOOL_NAMES[event.toolName as keyof typeof TOOL_NAMES];
      const kind = toolName === "Bash" || toolName === "Grep" ? "search" : "read";
      // The search CLI reads only `command`/`pattern`, so its input goes through unchanged.
      let inputs = [event.input];
      if (kind === "read") {
        const rawPath = typeof event.input.path === "string" ? event.input.path.trim() : ".";
        // OMP's glob accepts `;`-separated targets; Pi paths never contain one.
        const paths = event.toolName === "glob" ?
          rawPath.split(";").map(entry => entry.trim()).filter(Boolean) : [rawPath];
        inputs = [];
        for (const path of paths) {
          if (isRemote(path)) continue;
          const input: Record<string, unknown> = { ...event.input };
          const resolved = localPath(path, ctx.cwd, toolName === "Read");
          delete input.path;
          if (toolName === "Read") input.file_path = resolved;
          // OMP's glob target is a pattern; the CLI containment-checks only `path`.
          else if (event.toolName === "glob") { input.pattern = resolved; input.path = resolved; }
          else input.path = resolved;
          inputs.push(input);
        }
      }
      for (const input of inputs) {
        const timeout = Math.floor(deadline - performance.now());
        if (signal.aborted || !trusted() || timeout <= 0) return;
        const output = await runGuard(command, kind, JSON.stringify({
          session_id: ctx.sessionManager.getSessionId(), cwd: ctx.cwd, tool_name: toolName, tool_input: input,
        }), ctx.cwd, signal, timeout, OUTPUT_LIMIT);
        if (signal.aborted || !trusted()) return;
        if (!output) continue;
        let hook;
        try { hook = JSON.parse(output)?.hookSpecificOutput; } catch { continue; }
        if (hook?.hookEventName !== "PreToolUse") continue;
        if (hook.permissionDecision === "deny" && typeof hook.permissionDecisionReason === "string" && hook.permissionDecisionReason.trim()) {
          return { block: true, reason: hook.permissionDecisionReason };
        }
        if (typeof hook.additionalContext === "string" && hook.additionalContext.trim()) {
          contexts.push(hook.additionalContext);
        }
      }
    } catch {
      // Optional guidance must not break native tools on missing executables,
      // invalid paths, malformed hook output, timeout, or cancellation.
    }
    if (contexts.length === 0) return;
    const reminder = `<system-reminder source="graphify">\n${contexts.join("\n\n")}\n</system-reminder>`;
    if (passive) return { additionalContext: reminder };
    api.sendMessage?.({ customType: "graphify", content: reminder, display: true }, { deliverAs: "steer" });
  });
}
