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

type Result = { block?: boolean; reason?: string; messages?: { content: string }[] } | undefined;
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

test("real CLI strict denial blocks selector reads; subsequent guidance dedupes and resets", async () => {
  process.env.GRAPHIFY_HOOK_STRICT = "1";
  const api = harness();
  await api.emit("before_agent_start");
  const event = { toolName: "read", input: { path: "source.py:1-5" } };
  const result = await api.emit("tool_call", event);
  expect(result?.block).toBe(true);
  expect(result?.reason).toContain("graphify");
  expect(existsSync(join(cwd, "graphify-out", "cache", "hook_sessions", "omp-test-session.denied"))).toBe(true);
  expect(await api.emit("tool_call", event)).toBeUndefined();
  const first = await api.emit("context", { messages: [] });
  expect(first?.messages).toHaveLength(1);
  await api.emit("tool_call", event);
  const second = await api.emit("context", { messages: first?.messages });
  expect(second?.messages).toHaveLength(1);
  expect(second?.messages?.[0].content).toBe(first?.messages?.[0].content);
  await api.emit("before_agent_start");
  expect((await api.emit("context", { messages: second?.messages }))?.messages).toEqual([]);
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
    expect(await api.emit("tool_call", { toolName, input })).toBeUndefined();
    expect((await api.emit("context", { messages: [] }))?.messages?.[0].content).toBe(expected);
  }
});

test("URLs, internal resources, literal selector-like names and false trust do not run project hooks", async () => {
  const api = harness();
  for (const path of ["https://example.com/source.py", "www.example.com/source.py", "skill://graphify", "local:/source.py", "source.py; ssh://host/source.py"]) {
    await api.emit("tool_call", { toolName: "read", input: { path } });
    expect(existsSync(started)).toBe(false);
  }
  api.trust(false);
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py" } });
  expect(existsSync(started)).toBe(false);
  api.trust(true);
  writeFileSync(join(cwd, "source.py:12"), "a real filename, not a selector");
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py:12" } });
  expect(await api.emit("context", { messages: [] })).toBeUndefined();
});

test("navigation cancels in-flight guidance before the next session's context", async () => {
  for (const navigation of ["session_start", "session_switch", "session_tree", "session_branch", "session_shutdown", "before_agent_start"]) {
    rmSync(started, { force: true });
    writeFileSync(control, JSON.stringify({ mode: "delayed" }));
    const api = harness();
    const pending = api.emit("tool_call", { toolName: "read", input: { path: "source.py" } });
    const deadline = Date.now() + 1500;
    while (!existsSync(started) && Date.now() < deadline) await Bun.sleep(5);
    expect(existsSync(started)).toBe(true);
    await api.emit(navigation);
    expect(await pending).toBeUndefined();
    expect(await api.emit("context", { messages: [] })).toBeUndefined();
  }
});

test("oversized input never spawns, invalid/oversized output fails open, and a hung child is killed", async () => {
  const api = harness();
  await api.emit("tool_call", { toolName: "bash", input: { command: "x".repeat(256 * 1024) } });
  expect(existsSync(started)).toBe(false);
  for (const mode of ["invalid", "overflow", "hung"]) {
    writeFileSync(control, JSON.stringify({ mode }));
    const start = performance.now();
    expect(await api.emit("tool_call", { toolName: "read", input: { path: "source.py" } })).toBeUndefined();
    expect(performance.now() - start).toBeLessThan(3500);
    expect(await api.emit("context", { messages: [] })).toBeUndefined();
  }
}, 10000);

test("missing or project-local executables never fall back to project Python code", async () => {
  process.env.PATH = cwd;
  const api = harness();
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py" } });
  expect(existsSync(started)).toBe(false);
  writeFileSync(join(cwd, "graphify"), readFileSync(fixture));
  chmodSync(join(cwd, "graphify"), 0o755);
  await api.emit("tool_call", { toolName: "read", input: { path: "source.py" } });
  expect(existsSync(started)).toBe(false);
});
