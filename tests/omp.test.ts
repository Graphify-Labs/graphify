import { afterEach, beforeEach, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import graphify from "../graphify/omp/index.ts";

// Use the real installed Python CLI for policy tests. No mock of OMP path helpers.
const realCLI = process.env.GRAPHIFY_TEST_CLI ?? Bun.which("graphify");
if (!realCLI) throw new Error("Install graphifyy or set GRAPHIFY_TEST_CLI to its executable before running this test");
const savedPath = process.env.PATH;
const savedStrict = process.env.GRAPHIFY_HOOK_STRICT;
let root: string;
let cwd: string;
let control: string;
let started: string;
let fixture: string;

type Result = { block?: boolean; reason?: string; content?: { type: string; text: string }[] } | undefined;
type Handler = (event: Record<string, unknown>, ctx: object) => Result | Promise<Result>;
function harness() {
  const handlers = new Map<string, Handler>();
  let trusted = true;
  const ctx = { cwd, isProjectTrusted: () => trusted, sessionManager: { getSessionId: () => "omp-test-session" } };
  // Only the event registry is needed; every callback is the real extension's.
  const api = { on: (event: string, handler: Handler) => handlers.set(event, handler) } as unknown as ExtensionAPI;
  graphify(api);
  return {
    trust(value: boolean) { trusted = value; },
    async emit(event: string, payload: Record<string, unknown> = {}) { return await handlers.get(event)?.({ type: event, ...payload }, ctx); },
  };
}

// Claude Code delivers PreToolUse additionalContext as a system reminder that names the
// hook, never as tool output. Assert that shape: the guidance leads the result as one
// labelled reminder block, and the tool's own output follows unchanged.
function guidanceOf(result: Result, output: { type: string; text: string }[]): string {
  expect(result?.content).toEqual([expect.objectContaining({ type: "text" }), ...output]);
  const match = result!.content![0].text.match(/^<system-reminder source="graphify">\n([\s\S]*)\n<\/system-reminder>$/);
  expect(match).not.toBeNull();
  return match![1];
}
const ok = [{ type: "text", text: "ok" }];

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "graphify-omp-"));
  cwd = join(root, "project");
  mkdirSync(cwd);
  mkdirSync(join(root, "bin"));
  control = join(root, "control.json");
  started = join(root, "started");
  fixture = join(root, "bin", "graphify");
  writeFileSync(control, JSON.stringify({ mode: "real" }));
  // A controlled installed executable outside the project exercises the real
  // subprocess boundary (including cancellation and output limits).
  // Real subprocess timeouts cannot be advanced by the parent test's fake clock.
  writeFileSync(fixture, `#!${process.execPath}\nimport {execFileSync} from "node:child_process";
import {readFileSync,writeFileSync,existsSync} from "node:fs";
const input = await Bun.stdin.text();
const config = JSON.parse(readFileSync(${JSON.stringify(control)}, "utf8"));
writeFileSync(${JSON.stringify(started)}, input);
if (config.mode === "real") process.stdout.write(execFileSync(${JSON.stringify(realCLI)}, process.argv.slice(2), {input}));
else if (config.mode === "invalid") process.stdout.write("not json");
else if (config.mode === "overflow") process.stdout.write("x".repeat(65537));
else if (config.mode === "delayed") {
  while (!existsSync(${JSON.stringify(join(root, "release"))})) await Bun.sleep(5);
  process.stdout.write(JSON.stringify({hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: "stale guidance"}}));
} else if (config.mode === "varying") {
  const counterFile = ${JSON.stringify(join(root, "count"))};
  const n = existsSync(counterFile) ? Number(readFileSync(counterFile, "utf8")) || 0 : 0;
  writeFileSync(counterFile, String(n + 1));
  process.stdout.write(JSON.stringify({hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: "guidance " + (n + 1)}}));
} else if (config.mode === "hung") {
  process.on("SIGTERM", () => {});
  await Bun.sleep(60000);
}
`);
  chmodSync(fixture, 0o755);
  process.env.PATH = dirname(fixture);
  delete process.env.GRAPHIFY_HOOK_STRICT;
  writeFileSync(join(cwd, "source.py"), "def example(): pass\n");
  mkdirSync(join(cwd, "graphify-out"));
  writeFileSync(join(cwd, "graphify-out", "graph.json"), JSON.stringify({ nodes: [], links: [] }));
  writeFileSync(join(cwd, "graphify-out", "manifest.json"), JSON.stringify({ "source.py": {} }));
  const fresh = new Date(Date.now() + 1000);
  utimesSync(join(cwd, "graphify-out", "graph.json"), fresh, fresh);
});

afterEach(() => {
  process.env.PATH = savedPath;
  if (savedStrict === undefined) delete process.env.GRAPHIFY_HOOK_STRICT;
  else process.env.GRAPHIFY_HOOK_STRICT = savedStrict;
  rmSync(root, { recursive: true, force: true });
});

test("real CLI strict denial blocks selector reads; every later call nudges via its tool result and resets", async () => {
  process.env.GRAPHIFY_HOOK_STRICT = "1";
  const api = harness();
  await api.emit("before_agent_start");
  const event = { toolName: "read", input: { path: "source.py:1-5" }, toolCallId: "call-1" };
  const result = await api.emit("tool_call", event);
  expect(result?.block).toBe(true);
  expect(result?.reason).toContain("graphify");
  expect(existsSync(join(cwd, "graphify-out", "cache", "hook_sessions", "omp-test-session.denied"))).toBe(true);
  // After the one-time deny, every qualifying call still carries its own guidance.
  expect(await api.emit("tool_call", { ...event, toolCallId: "call-2" })).toBeUndefined();
  const second = await api.emit("tool_result", { toolCallId: "call-2", content: ok });
  expect(guidanceOf(second, ok)).toContain("graphify");
  expect(await api.emit("tool_call", { ...event, toolCallId: "call-3" })).toBeUndefined();
  const third = await api.emit("tool_result", { toolCallId: "call-3", content: ok });
  expect(guidanceOf(third, ok)).toContain("graphify");
  // Navigation resets pending guidance: a result arriving after the reset is untouched.
  await api.emit("before_agent_start");
  expect(await api.emit("tool_result", { toolCallId: "call-3", content: [{ type: "text", text: "ok" }] })).toBeUndefined();
});

test("native grep, bash search, and glob expose the installed CLI's actual guidance", async () => {
  for (const [toolName, input, kind, legacyInput] of [
    ["grep", { pattern: "example", path: "source.py:1" }, "search", { pattern: "example" }],
    ["bash", { command: "rg example ." }, "search", { command: "rg example ." }],
    ["glob", { path: "**/*.py" }, "read", { pattern: "**/*.py" }],
  ] as const) {
    const api = harness();
    const expected = JSON.parse(execFileSync(realCLI!, ["hook-guard", kind], {
      cwd, input: JSON.stringify({ tool_input: legacyInput }), encoding: "utf8",
    })).hookSpecificOutput.additionalContext;
    const toolCallId = `${toolName}-1`;
    expect(await api.emit("tool_call", { toolName, input, toolCallId })).toBeUndefined();
    const result = await api.emit("tool_result", { toolCallId, content: ok });
    expect(guidanceOf(result, ok)).toBe(expected);
  }
});

test("multi-target glob calls surface every target's guidance", async () => {
  // The real CLI returns identical fresh text per glob target (its stale check
  // keys on file_path, which glob payloads do not carry), so a varying fixture
  // mode distinguishes the per-target guard invocations the extension must join.
  writeFileSync(control, JSON.stringify({ mode: "varying" }));
  const api = harness();
  expect(await api.emit("tool_call", { toolName: "glob", input: { path: "source.py;stale.py" }, toolCallId: "call-1" })).toBeUndefined();
  const result = await api.emit("tool_result", { toolCallId: "call-1", content: ok });
  const guidance = guidanceOf(result, ok);
  expect(guidance).toContain("guidance 1");
  expect(guidance).toContain("guidance 2");
});

test("URLs, internal resources, literal selector-like names and false trust do not run project hooks", async () => {
  const api = harness();
  for (const path of ["https://example.com/source.py", "www.example.com/source.py", "skill://graphify", "local:/source.py", "source.py; ssh://host/source.py"]) {
    await api.emit("tool_call", { toolName: "read", input: { path }, toolCallId: "call-1" });
    expect(existsSync(started)).toBe(false);
    expect(await api.emit("tool_result", { toolCallId: "call-1", content: [] })).toBeUndefined();
  }
  api.trust(false);
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-2" });
  expect(existsSync(started)).toBe(false);
  api.trust(true);
  writeFileSync(join(cwd, "source.py:12"), "a real filename, not a selector");
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py:12" }, toolCallId: "call-3" });
  expect(await api.emit("tool_result", { toolCallId: "call-3", content: [] })).toBeUndefined();
});

test("a file:// read target resolves to the real local path and still reaches the guard", async () => {
  // file:// is the one scheme isRemote lets through to resolveReadPathAsync
  // (which OMP's own path pipeline also resolves down to a local path, not
  // an external URL) -- an in-project file:// target must still nudge...
  const api = harness();
  await api.emit("tool_call", { toolName: "read", input: { path: `file://${join(cwd, "source.py")}` }, toolCallId: "call-1" });
  const inProject = await api.emit("tool_result", { toolCallId: "call-1", content: [] });
  expect(guidanceOf(inProject, [])).toContain("graphify");
  // ...while one outside the project still resolves (the CLI subprocess
  // runs), but the guard's own containment check stays silent, same as any
  // other out-of-project absolute path.
  await api.emit("tool_call", { toolName: "read", input: { path: `file://${join(root, "outside.py")}` }, toolCallId: "call-2" });
  expect(await api.emit("tool_result", { toolCallId: "call-2", content: [] })).toBeUndefined();
});

test("a file:// read target with a non-local authority never reaches the guard", async () => {
  // VALID #2: RFC 8089 / Node's url.fileURLToPath (ERR_INVALID_FILE_URL_HOST)
  // -- only an empty or `localhost` authority names a local file. Any other
  // authority names a remote host and must not alias an in-project file
  // merely by sharing its path component.
  const api = harness();
  await api.emit("tool_call", { toolName: "read", input: { path: `file://evil.com${join(cwd, "source.py")}` }, toolCallId: "call-1" });
  expect(existsSync(started)).toBe(false);
  expect(await api.emit("tool_result", { toolCallId: "call-1", content: [] })).toBeUndefined();
});

test("a file:// read target with an explicit localhost authority still reaches the guard", async () => {
  const api = harness();
  await api.emit("tool_call", { toolName: "read", input: { path: `file://localhost${join(cwd, "source.py")}` }, toolCallId: "call-1" });
  const result = await api.emit("tool_result", { toolCallId: "call-1", content: [] });
  expect(guidanceOf(result, [])).toContain("graphify");
});

test("navigation cancels in-flight guidance before the next session's tool results", async () => {
  for (const navigation of ["session_start", "session_switch", "session_tree", "session_branch", "session_shutdown", "before_agent_start"]) {
    rmSync(started, { force: true });
    writeFileSync(control, JSON.stringify({ mode: "delayed" }));
    const api = harness();
    const pending = api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
    const deadline = Date.now() + 1500;
    while (!existsSync(started) && Date.now() < deadline) await Bun.sleep(5);
    expect(existsSync(started)).toBe(true);
    await api.emit(navigation);
    expect(await pending).toBeUndefined();
    expect(await api.emit("tool_result", { toolCallId: "call-1", content: [] })).toBeUndefined();
  }
});

test("oversized input never spawns, invalid/oversized output fails open, and a hung child is killed", async () => {
  const api = harness();
  await api.emit("tool_call", { toolName: "bash", input: { command: "x".repeat(256 * 1024) }, toolCallId: "call-1" });
  expect(existsSync(started)).toBe(false);
  for (const mode of ["invalid", "overflow", "hung"]) {
    writeFileSync(control, JSON.stringify({ mode }));
    const start = performance.now();
    expect(await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-2" })).toBeUndefined();
    expect(performance.now() - start).toBeLessThan(3500);
    expect(await api.emit("tool_result", { toolCallId: "call-2", content: [] })).toBeUndefined();
  }
}, 10000);

test("missing or project-local executables never fall back to project Python code", async () => {
  process.env.PATH = cwd;
  const api = harness();
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
  expect(existsSync(started)).toBe(false);
  writeFileSync(join(cwd, "graphify"), readFileSync(fixture));
  chmodSync(join(cwd, "graphify"), 0o755);
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-2" });
  expect(existsSync(started)).toBe(false);
});

test("index.ts imports only packages the host actually provides -- no dependency the wheel's node_modules-less install can never resolve", () => {
  // The extension loads from a site-packages install with no node_modules at
  // all (see graphify/omp/package.json's "files" list). The host supplies
  // exactly @oh-my-pi/pi-coding-agent to legacy extensions; anything else
  // bare-imported here -- however cleanly `bun test` resolves it via this
  // repo's own dev node_modules -- is unresolvable in production.
  const source = readFileSync(join(import.meta.dir, "../graphify/omp/index.ts"), "utf8");
  const specifiers = [...source.matchAll(/from\s+"([^"]+)"/g)].map(m => m[1]);
  const allowed = (specifier: string) =>
    specifier.startsWith("node:") || specifier === "@oh-my-pi/pi-coding-agent" || specifier.startsWith("@oh-my-pi/pi-coding-agent/");
  expect(specifiers.length).toBeGreaterThan(0);
  expect(specifiers.filter(specifier => !allowed(specifier))).toEqual([]);
});

test("every named import from @oh-my-pi/pi-coding-agent/tools/path-utils is exported by the oldest host-provided copy", () => {
  // Being on the allow-list above is not enough: @oh-my-pi/pi-coding-agent
  // itself is allow-listed, but a symbol added to the bridge's import list
  // can still be missing from an older copy the live host actually binds
  // (see resolveReadPathAsync, absent from 18.1.17). Parse the real import
  // list out of index.ts -- never hardcode it -- so a future added symbol
  // is checked automatically.
  const oldestRoot = "/root/.omp/plugins/node_modules/@oh-my-pi/pi-coding-agent";
  const oldestPathUtils = join(oldestRoot, "src/tools/path-utils.ts");
  if (!existsSync(oldestPathUtils)) {
    console.warn(`skipping: oldest pi-coding-agent copy not found at ${oldestPathUtils}`);
    return;
  }
  const source = readFileSync(join(import.meta.dir, "../graphify/omp/index.ts"), "utf8");
  const importBlock = source.match(/import\s*{([^}]+)}\s*from\s*"@oh-my-pi\/pi-coding-agent\/tools\/path-utils"/);
  expect(importBlock).not.toBeNull();
  const imported = importBlock![1].split(",").map(name => name.trim()).filter(Boolean);
  expect(imported.length).toBeGreaterThan(0);
  const exportedSource = readFileSync(oldestPathUtils, "utf8");
  const exported = new Set(
    [...exportedSource.matchAll(/^export\s+(?:async\s+function|function)\s+(\w+)/gm)].map(m => m[1]),
  );
  expect(imported.filter(name => !exported.has(name))).toEqual([]);
});
