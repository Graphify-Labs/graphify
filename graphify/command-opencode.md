---
description: Build or query a graphify knowledge graph
---

Invoke the `graphify` skill immediately, using the skill tool with name `graphify`.

Arguments: $ARGUMENTS

If no arguments were supplied, treat the target path as `.`.

Examples:
- `/graphify`
- `/graphify src --update`
- `/graphify query "what connects auth to billing?"`

Do not answer from raw files before handing off to the `graphify` skill.
