## Kilo-specific rules

- Use the native `Task` tool for semantic extraction fan-out.
- Launch all chunk tasks in the same response so they run in parallel.
- Default to `subagent_type="general"` for extraction chunks; it needs Write and Bash access, so if a dispatch policy restricts `general`, use any permitted type with both tools instead.
- After modifying code files during the session, run `graphify update .`.

---
