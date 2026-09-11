import { execFile } from "node:child_process";
import { realpathSync } from "node:fs";
import { delimiter, isAbsolute, relative, sep } from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import {
  expandDelimitedPathEntries,
  isInternalUrlPath,
  isReadableUrlPath,
  normalizePathLikeInput,
  parseSearchPath,
  resolveReadPath,
  splitPathAndSelPreferringLiteral,
} from "@oh-my-pi/pi-coding-agent/tools/path-utils";

const INPUT_LIMIT = 256 * 1024;
const OUTPUT_LIMIT = 64 * 1024;
const TIMEOUT_MS = 2000;
const CONTEXT_TYPE = "graphify-guard";
const TOOL_NAMES = { bash: "Bash", grep: "Grep", read: "Read", glob: "Glob" } as const;

function isRemote(path: string): boolean {
  return isInternalUrlPath(path) || isReadableUrlPath(path) || path.includes("://");
}

function installedCommand(cwd: string): string | undefined {
  // Never resolve a bare/relative PATH entry against the project or use a
  // project-supplied Python module as a fallback for an absent installation.
  const path = (process.env.PATH ?? "").split(delimiter).filter(isAbsolute).join(delimiter);
  const found = path ? Bun.which("graphify", { PATH: path }) : null;
  if (!found) return;
  const command = realpathSync(found);
  const within = relative(realpathSync(cwd), command);
  if (!within || (!within.startsWith(`..${sep}`) && !isAbsolute(within))) return;
  return command;
}

function runGuard(command: string, kind: string, payload: string, cwd: string, signal: AbortSignal, timeout: number, maxBuffer: number): Promise<string | undefined> {
  if (Buffer.byteLength(payload) > INPUT_LIMIT || signal.aborted) return Promise.resolve(undefined);
  const { promise, resolve } = Promise.withResolvers<string | undefined>();
  const child = execFile(command, ["hook-guard", kind], {
    cwd, encoding: "utf8", timeout, killSignal: "SIGKILL", maxBuffer, signal,
    env: { ...process.env, CLAUDE_PROJECT_DIR: cwd },
  }, (error, stdout) => resolve(error ? undefined : stdout.trim() || undefined));
  child.stdin?.on("error", () => {});
  child.stdin?.end(payload);
  return promise;
}

export default function graphify(api: ExtensionAPI): void {
  const guidance = new Set<string>();
  let guidanceBytes = 0;
  let generation = 0;
  let controller = new AbortController();
  const reset = () => {
    generation++;
    controller.abort();
    controller = new AbortController();
    guidance.clear();
    guidanceBytes = 0;
  };
  api.on("session_start", reset);
  api.on("session_switch", reset);
  api.on("session_branch", reset);
  api.on("session_tree", reset);
  api.on("session_shutdown", reset);
  api.on("before_agent_start", reset);

  api.on("tool_call", async (event, ctx) => {
    if (!ctx.isProjectTrusted()) { reset(); return; }
    if (!Object.hasOwn(TOOL_NAMES, event.toolName)) return;
    const current = generation;
    const signal = controller.signal;
    const deadline = performance.now() + TIMEOUT_MS;
    try {
      if (Buffer.byteLength(JSON.stringify(event.input)) > INPUT_LIMIT) return;
      const command = installedCommand(ctx.cwd);
      if (!command) return;
      const toolName = TOOL_NAMES[event.toolName as keyof typeof TOOL_NAMES];
      const rawPath = typeof event.input.path === "string" ? normalizePathLikeInput(event.input.path) : ".";
      if (isRemote(rawPath)) return;
      const paths = toolName === "Read" || toolName === "Bash" ? [rawPath] :
        await expandDelimitedPathEntries([rawPath], ctx.cwd, { splitter: parseSearchPath });
      let remainingOutput = OUTPUT_LIMIT;
      for (const path of paths) {
        if (isRemote(path)) continue;
        const input: Record<string, unknown> = { ...event.input };
        if (toolName !== "Bash") {
          const target = toolName === "Glob" ? path : (await splitPathAndSelPreferringLiteral(path, ctx.cwd)).path;
          const resolved = resolveReadPath(target, ctx.cwd);
          delete input.path;
          if (toolName === "Read") input.file_path = resolved;
          else if (toolName === "Glob") input.pattern = resolved;
          else input.path = resolved;
        }
        const timeout = Math.floor(deadline - performance.now());
        if (current !== generation || !ctx.isProjectTrusted() || timeout <= 0 || remainingOutput <= 0) return;
        const output = await runGuard(command, toolName === "Bash" || toolName === "Grep" ? "search" : "read", JSON.stringify({
          session_id: ctx.sessionManager.getSessionId(), cwd: ctx.cwd, tool_name: toolName, tool_input: input,
        }), ctx.cwd, signal, timeout, remainingOutput);
        if (current !== generation || !ctx.isProjectTrusted()) return;
        if (!output) continue;
        remainingOutput -= Buffer.byteLength(output);
        const hook = JSON.parse(output)?.hookSpecificOutput;
        if (hook?.hookEventName !== "PreToolUse") continue;
        if (hook.permissionDecision === "deny" && typeof hook.permissionDecisionReason === "string" && hook.permissionDecisionReason.trim()) {
          return { block: true, reason: hook.permissionDecisionReason };
        }
        if (typeof hook.additionalContext === "string" && hook.additionalContext.trim() && !guidance.has(hook.additionalContext)) {
          const bytes = Buffer.byteLength(hook.additionalContext) + 2;
          if (guidanceBytes + bytes <= OUTPUT_LIMIT) {
            guidance.add(hook.additionalContext);
            guidanceBytes += bytes;
          }
        }
        // The search CLI does not inspect individual targets; one call suffices.
        if (toolName === "Grep") break;
      }
    } catch {
      // Optional guidance must not break native tools on missing executables,
      // invalid paths, malformed hook output, timeout, or cancellation.
    }
  });

  api.on("context", (event, ctx) => {
    if (!ctx.isProjectTrusted()) reset();
    // Context transforms are not persisted. Keep one current-run message across
    // provider requests, and discard any prior generation's injected message.
    const messages = event.messages.filter(message => message.role !== "custom" || message.customType !== CONTEXT_TYPE);
    if (guidance.size) messages.push({
      role: "custom", customType: CONTEXT_TYPE, content: [...guidance].join("\n\n"), display: false, timestamp: Date.now(),
    });
    if (guidance.size || messages.length !== event.messages.length) return { messages };
  });
}
