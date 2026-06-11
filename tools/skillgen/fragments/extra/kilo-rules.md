## Kilo-specific rules

- Use the native `Task` tool for semantic extraction fan-out.
- Launch all chunk tasks in the same response so they run in parallel.
- Always use `subagent_type="general"` for extraction chunks.
- After modifying code files during the session, run `graphify update .`.

---
