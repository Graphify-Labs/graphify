import { execFile } from "node:child_process";
import { realpathSync } from "node:fs";
import { delimiter, isAbsolute, relative, sep } from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import {
  expandDelimitedPathEntries,
  isInternalUrlPath,
  normalizePathLikeInput,
  resolveReadPathAsync,
  splitPathAndSelPreferringLiteral,
} from "@oh-my-pi/pi-coding-agent/tools/path-utils";

// Mirrors the upstream isReadableUrlPath predicate, kept as a same-named
// local copy (not imported): the wheel ships no node_modules, so this
// extension may import only host-provided packages, and the host provides
// @oh-my-pi/pi-coding-agent alone -- a scoped subpath import of any other
// package is unresolvable at runtime. Named to match so a future reader can
// diff them.
function isReadableUrlPath(value: string): boolean {
  return /^https?:\/\/?/i.test(value) || /^www\./i.test(value);
}

const INPUT_LIMIT = 256 * 1024;
const OUTPUT_LIMIT = 64 * 1024;
const TIMEOUT_MS = 2000;
const TOOL_NAMES = { bash: "Bash", grep: "Grep", read: "Read", glob: "Glob" } as const;
const FILE_URL_RE = /^file:\/\//i;

// isInternalUrlPath/isReadableUrlPath still earn their place even though the
// guard now defends itself against URL-shaped input: resolveReadPathAsync
// below pre-resolves a rootless value to an absolute path
// (`path.resolve(cwd, x)`) before the guard ever sees it, which for a
// *foreign*-scheme value glues it onto cwd into something that looks
// exactly like a real in-project file (`<cwd>/https:/example.com/x`,
// `<cwd>/local:/x`) -- a guard fix the bridge then defeats by mangling its
// input first is not a fix. file:// is the one exception: OMP's own
// resolveReadPathAsync already strips it down to the real local path (its
// resolveToCwd -> expandPath -> stripFileUrl, deliberately excluded from
// the external-URL fast path), so routing it through here yields the
// correct absolute path rather than a mangled one.
function isRemote(path: string): boolean {
  if (FILE_URL_RE.test(path)) return false;
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
  // Claude PreToolUse additionalContext parity: `tool_call` captures the guard's
  // guidance for that call, `tool_result` appends it to the persisted tool
  // result. Every qualifying call carries its own nudge — no dedup — and the
  // text lands inline with the call it belongs to, surviving compaction like
  // any other tool output.
  const pending = new Map<string, string>();
  let generation = 0;
  let controller = new AbortController();
  const reset = () => {
    generation++;
    controller.abort();
    controller = new AbortController();
    pending.clear();
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
        await expandDelimitedPathEntries([rawPath], ctx.cwd);
      for (const path of paths) {
        if (isRemote(path)) continue;
        const input: Record<string, unknown> = { ...event.input };
        if (toolName !== "Bash") {
          const target = toolName === "Glob" ? path : (await splitPathAndSelPreferringLiteral(path, ctx.cwd)).path;
          const resolved = await resolveReadPathAsync(target, ctx.cwd);
          delete input.path;
          if (toolName === "Read") input.file_path = resolved;
          else if (toolName === "Glob") input.pattern = resolved;
          else input.path = resolved;
        }
        const timeout = Math.floor(deadline - performance.now());
        if (current !== generation || !ctx.isProjectTrusted() || timeout <= 0) return;
        const output = await runGuard(command, toolName === "Bash" || toolName === "Grep" ? "search" : "read", JSON.stringify({
          session_id: ctx.sessionManager.getSessionId(), cwd: ctx.cwd, tool_name: toolName, tool_input: input,
        }), ctx.cwd, signal, timeout, OUTPUT_LIMIT);
        if (current !== generation || !ctx.isProjectTrusted()) return;
        if (!output) continue;
        const hook = JSON.parse(output)?.hookSpecificOutput;
        if (hook?.hookEventName !== "PreToolUse") continue;
        if (hook.permissionDecision === "deny" && typeof hook.permissionDecisionReason === "string" && hook.permissionDecisionReason.trim()) {
          return { block: true, reason: hook.permissionDecisionReason };
        }
        if (typeof hook.additionalContext === "string" && hook.additionalContext.trim()) {
          const previous = pending.get(event.toolCallId);
          pending.set(event.toolCallId, previous ? `${previous}\n\n${hook.additionalContext}` : hook.additionalContext);
        }
        // The search CLI does not inspect individual targets; one call suffices.
        if (toolName === "Grep") break;
      }
    } catch {
      // Optional guidance must not break native tools on missing executables,
      // invalid paths, malformed hook output, timeout, or cancellation.
    }
  });

  api.on("tool_result", (event, ctx) => {
    if (!ctx.isProjectTrusted()) { pending.clear(); return; }
    const nudge = pending.get(event.toolCallId);
    if (nudge === undefined) return;
    pending.delete(event.toolCallId);
    return { content: [...event.content, { type: "text" as const, text: nudge }] };
  });
}
