import { afterEach, beforeEach, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, relative } from "node:path";
import graphify from "../graphify/pi/index.ts";

// Use the real installed Python CLI for policy tests. No mock of host path helpers.
const realCLI = process.env.GRAPHIFY_TEST_CLI ?? Bun.which("graphify");
if (!realCLI) throw new Error("Install graphifyy or set GRAPHIFY_TEST_CLI to its executable before running this test");
const savedPath = process.env.PATH;
const savedStrict = process.env.GRAPHIFY_HOOK_STRICT;
let root: string;
let cwd: string;
let control: string;
let started: string;
let fixture: string;

type Result = { block?: boolean; reason?: string; additionalContext?: string } | undefined;
type Handler = (event: Record<string, unknown>, ctx: object) => Result | Promise<Result>;
type Sent = { message: { customType: string; content: string; display: boolean }; options: { deliverAs: string } };
// `omp` hands the extension its own module as `api.pi` and takes passive context
// from tool_call; `pi` has no such channel and gets a steering message instead.
function harness(host: "omp" | "pi" = "omp") {
  const handlers = new Map<string, Handler>();
  const sent: Sent[] = [];
  let trusted = true;
  const ctx = { cwd, isProjectTrusted: () => trusted, sessionManager: { getSessionId: () => "omp-test-session" } };
  // Only the event registry and message sink are needed; every callback is the real extension's.
  const api = {
    on: (event: string, handler: Handler) => handlers.set(event, handler),
    sendMessage: (message: Sent["message"], options: Sent["options"]) => sent.push({ message, options }),
    ...(host === "omp" ? { pi: {} } : {}),
  };
  graphify(api);
  return {
    sent,
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
else if (config.mode === "overflow") process.stdout.write(JSON.stringify({hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: "overflow guidance"}}) + " ".repeat(65537));
else if (config.mode === "delayed") {
  while (!existsSync(${JSON.stringify(join(root, "release"))})) await Bun.sleep(5);
  process.stdout.write(JSON.stringify({hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: "stale guidance"}}));
} else if (config.mode === "varying") {
  const counterFile = ${JSON.stringify(join(root, "count"))};
  const n = existsSync(counterFile) ? Number(readFileSync(counterFile, "utf8")) || 0 : 0;
  writeFileSync(counterFile, String(n + 1));
  if (config.invalidFirst && n === 0) process.stdout.write("not json");
  else process.stdout.write(JSON.stringify({hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: "guidance " + (n + 1)}}));
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

test("real CLI strict denial blocks once; later calls return trusted passive context", async () => {
  process.env.GRAPHIFY_HOOK_STRICT = "1";
  const api = harness();
  await api.emit("before_agent_start");
  const event = { toolName: "read", input: { path: "source.py:1-5" }, toolCallId: "call-1" };
  const result = await api.emit("tool_call", event);
  expect(result?.block).toBe(true);
  expect(result?.reason).toContain("graphify");
  expect(existsSync(join(cwd, "graphify-out", "cache", "hook_sessions", "omp-test-session.denied"))).toBe(true);
  // After the one-time deny, every qualifying call carries its own guidance.
  const second = await api.emit("tool_call", { ...event, toolCallId: "call-2" });
  expect(second?.additionalContext).toContain("graphify");
  await api.emit("before_agent_start");
  const third = await api.emit("tool_call", { ...event, toolCallId: "call-3" });
  expect(third?.additionalContext).toContain("graphify");
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
    const result = await api.emit("tool_call", { toolName, input, toolCallId: `${toolName}-1` });
    expect(result?.additionalContext).toBe(`<system-reminder source="graphify">\n${expected}\n</system-reminder>`);
  }
});

test("multi-target glob calls surface every target's guidance", async () => {
  // The real CLI returns identical fresh text per glob target (its stale check
  // keys on file_path, which glob payloads do not carry), so a varying fixture
  // mode distinguishes the per-target guard invocations the extension must join.
  writeFileSync(control, JSON.stringify({ mode: "varying" }));
  const api = harness();
  const result = await api.emit("tool_call", { toolName: "glob", input: { path: "source.py;stale.py" }, toolCallId: "call-1" });
  expect(result?.additionalContext).toContain("guidance 1");
  expect(result?.additionalContext).toContain("guidance 2");
});

test("malformed output from one glob target does not stop later targets", async () => {
  writeFileSync(control, JSON.stringify({ mode: "varying", invalidFirst: true }));
  const api = harness();
  const result = await api.emit("tool_call", { toolName: "glob", input: { path: "source.py;stale.py" }, toolCallId: "call-1" });
  expect(result?.additionalContext).toContain("guidance 2");
});

test("URLs, internal resources, literal selector-like names and false trust do not run project hooks", async () => {
  const api = harness();
  for (const path of ["https://example.com/source.py", "www.example.com/source.py", "skill://graphify", "local:/source.py", "source.py; ssh://host/source.py"]) {
    expect(await api.emit("tool_call", { toolName: "read", input: { path }, toolCallId: "call-1" })).toBeUndefined();
    expect(existsSync(started)).toBe(false);
  }
  api.trust(false);
  expect(await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-2" })).toBeUndefined();
  expect(existsSync(started)).toBe(false);
  api.trust(true);
  writeFileSync(join(cwd, "source.py:12"), "a real filename, not a selector");
  expect(await api.emit("tool_call", { toolName: "read", input: { path: "source.py:12" }, toolCallId: "call-3" })).toBeUndefined();
});

test("a file:// read target resolves to the real local path and still reaches the guard", async () => {
  // file:// is the one scheme isRemote lets through to localPath
  // (which OMP's own path pipeline also resolves down to a local path, not
  // an external URL) -- an in-project file:// target must still nudge...
  const api = harness();
  const inProject = await api.emit("tool_call", { toolName: "read", input: { path: `file://${join(cwd, "source.py")}` }, toolCallId: "call-1" });
  expect(inProject?.additionalContext).toContain("graphify");
  // ...while one outside the project still resolves (the CLI subprocess
  // runs), but the guard's own containment check stays silent, same as any
  // other out-of-project absolute path.
  expect(await api.emit("tool_call", { toolName: "read", input: { path: `file://${join(root, "outside.py")}` }, toolCallId: "call-2" })).toBeUndefined();
});

test("file:// read targets distinguish remote authorities from localhost", async () => {
  const api = harness();
  expect(await api.emit("tool_call", {
    toolName: "read",
    input: { path: `file://evil.com${join(cwd, "source.py")}` },
    toolCallId: "call-1",
  })).toBeUndefined();
  expect(existsSync(started)).toBe(false);

  const local = await api.emit("tool_call", {
    toolName: "read",
    input: { path: `file://localhost${join(cwd, "source.py")}` },
    toolCallId: "call-2",
  });
  expect(local?.additionalContext).toContain("graphify");
});

test("navigation cancels in-flight guidance promptly, for every reset event", async () => {
  for (const navigation of ["session_start", "session_switch", "session_tree", "session_branch", "session_shutdown", "before_agent_start"]) {
    rmSync(started, { force: true });
    writeFileSync(control, JSON.stringify({ mode: "delayed" }));
    const api = harness();
    const pending = api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
    const deadline = Date.now() + 1500;
    while (!existsSync(started) && Date.now() < deadline) await Bun.sleep(5);
    expect(existsSync(started)).toBe(true);
    const navigated = performance.now();
    await api.emit(navigation);
    expect(await pending).toBeUndefined();
    // Without the abort the child would only be killed by the 2s timeout.
    expect(performance.now() - navigated).toBeLessThan(1000);
  }
}, 15000);

test("output that finishes after navigation is discarded", async () => {
  writeFileSync(control, JSON.stringify({ mode: "delayed" }));
  const api = harness("pi");
  const pending = api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
  const deadline = Date.now() + 1500;
  while (!existsSync(started) && Date.now() < deadline) await Bun.sleep(5);
  expect(existsSync(started)).toBe(true);
  // Release the child and block the event loop until it has exited, so its
  // output is ready before the session navigates.
  writeFileSync(join(root, "release"), "");
  Bun.sleepSync(300);
  await api.emit("session_start");
  expect(await pending).toBeUndefined();
  expect(api.sent).toEqual([]);
});

test("oversized input never spawns, invalid/oversized output fails open, and a hung child is killed", async () => {
  const api = harness();
  expect(await api.emit("tool_call", { toolName: "bash", input: { command: "x".repeat(256 * 1024) }, toolCallId: "call-1" })).toBeUndefined();
  expect(existsSync(started)).toBe(false);
  for (const mode of ["invalid", "overflow", "hung"]) {
    writeFileSync(control, JSON.stringify({ mode }));
    const start = performance.now();
    expect(await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-2" })).toBeUndefined();
    expect(performance.now() - start).toBeLessThan(3500);
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

test("a project-local graphify earlier on PATH does not shadow an installed one", async () => {
  const local = join(cwd, ".venv", "bin");
  mkdirSync(local, { recursive: true });
  writeFileSync(join(local, "graphify"), `#!/bin/sh\ntouch ${JSON.stringify(join(root, "local-ran"))}\n`);
  chmodSync(join(local, "graphify"), 0o755);
  process.env.PATH = [local, dirname(fixture)].join(delimiter);
  const result = await harness().emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
  expect(result?.additionalContext).toContain("graphify");
  expect(existsSync(join(root, "local-ran"))).toBe(false);
});

test("the executable is spawned through its PATH entry, not the symlink's target", async () => {
  // A shim that dispatches on argv[0] must see the name it was installed under.
  const multicall = join(root, "multicall");
  writeFileSync(multicall, `#!/bin/sh\necho "$0" > ${JSON.stringify(join(root, "argv0"))}\nexec ${JSON.stringify(fixture)} "$@"\n`);
  chmodSync(multicall, 0o755);
  const shim = join(root, "shim");
  mkdirSync(shim);
  symlinkSync(multicall, join(shim, "graphify"));
  process.env.PATH = shim;
  const result = await harness().emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
  expect(result?.additionalContext).toContain("graphify");
  expect(readFileSync(join(root, "argv0"), "utf8").trim()).toBe(join(shim, "graphify"));
});

test("a relative PATH entry is never searched", async () => {
  process.env.PATH = relative(process.cwd(), dirname(fixture));
  await harness().emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
  expect(existsSync(started)).toBe(false);
});

test("tools the guard does not map never spawn it", async () => {
  process.env.GRAPHIFY_HOOK_STRICT = "1";
  const api = harness();
  for (const [toolName, input] of [
    ["edit", { path: "source.py" }],
    ["write", { path: "source.py", content: "" }],
    ["ls", { path: "source.py" }],
    // OMP's `find` is a semantic search, not Pi's pattern-based `find`.
    ["find", { query: "example", path: "source.py" }],
  ] as const) {
    expect(await api.emit("tool_call", { toolName, input, toolCallId: "call-1" })).toBeUndefined();
    expect(existsSync(started)).toBe(false);
  }
});

test("OMP glob targets outside the project stay silent; in-project ones still nudge", async () => {
  const api = harness();
  for (const path of [join(root, "outside", "**", "*.py"), "../outside/*.py"]) {
    expect(await api.emit("tool_call", { toolName: "glob", input: { path }, toolCallId: "call-1" })).toBeUndefined();
  }
  const inside = await api.emit("tool_call", { toolName: "glob", input: { path: "src/**/*.py" }, toolCallId: "call-2" });
  expect(inside?.additionalContext).toContain("graphify");
});

test("`@` and `~` prefixes are normalized like Pi's tools do", async () => {
  // ~/source.py is outside the project (and would match the manifest by basename
  // if it were mistaken for <cwd>/~/source.py); @source.py is the in-project file.
  const savedHome = process.env.HOME;
  process.env.HOME = join(root, "home");
  mkdirSync(process.env.HOME);
  writeFileSync(join(process.env.HOME, "source.py"), "def other(): pass\n");
  process.env.GRAPHIFY_HOOK_STRICT = "1";
  try {
    const api = harness();
    expect(await api.emit("tool_call", { toolName: "read", input: { path: "~/source.py" }, toolCallId: "call-1" })).toBeUndefined();
    const result = await api.emit("tool_call", { toolName: "read", input: { path: "@source.py" }, toolCallId: "call-2" });
    expect(result?.block).toBe(true);
  } finally {
    if (savedHome === undefined) delete process.env.HOME;
    else process.env.HOME = savedHome;
  }
});

test("on Pi, guidance goes out as one steering message and tool_call returns nothing", async () => {
  const api = harness("pi");
  const expected = JSON.parse(execFileSync(realCLI!, ["hook-guard", "search"], {
    cwd, input: JSON.stringify({ tool_input: { pattern: "example" } }), encoding: "utf8",
  })).hookSpecificOutput.additionalContext;
  expect(await api.emit("tool_call", { toolName: "grep", input: { pattern: "example", path: "." }, toolCallId: "call-1" })).toBeUndefined();
  expect(api.sent).toEqual([{
    message: { customType: "graphify", content: `<system-reminder source="graphify">\n${expected}\n</system-reminder>`, display: true },
    options: { deliverAs: "steer" },
  }]);
});

test("Pi's find tool reaches the read guard with its pattern and a resolved path", async () => {
  const api = harness("pi");
  await api.emit("tool_call", { toolName: "find", input: { pattern: "*.py", path: "." }, toolCallId: "call-1" });
  const payload = JSON.parse(readFileSync(started, "utf8"));
  expect(payload.tool_name).toBe("Glob");
  expect(payload.tool_input).toEqual({ pattern: "*.py", path: cwd });
  expect(api.sent).toHaveLength(1);
});

test("Pi strict denial still blocks through tool_call", async () => {
  process.env.GRAPHIFY_HOOK_STRICT = "1";
  const api = harness("pi");
  const result = await api.emit("tool_call", { toolName: "read", input: { path: "source.py" }, toolCallId: "call-1" });
  expect(result?.block).toBe(true);
  expect(api.sent).toEqual([]);
});
