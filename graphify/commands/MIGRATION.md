# Migrating a command out of cli.dispatch_command

`graphify/cli.py`'s `dispatch_command()` is a ~3,100-line `if/elif` chain over
the command name (issue #1212 proposes splitting it into this package, mirroring
the `graphify/extractors/` split). This is the playbook for porting ONE command.
It is written so an AI agent can execute it in a single session.

## Status

| command | migrated |
|---|---|
| merge-chunks | yes |
| (everything else in `dispatch_command`) | no |

## Invariants (non-negotiable)

1. **Verbatim moves only.** Move the body of one `elif cmd == "<name>":` branch
   into a function, dedented one level, with no renames, no docstring edits, no
   reformatting, no added annotations, no "improvements". The handler reads
   `sys.argv` and calls `sys.exit(...)` exactly as the branch did, so the move
   is behavior-preserving. Verify: the command's existing tests pass unchanged.
2. **One command per PR.** Small diffs keep review trivial and avoid conflicts
   with other in-flight ports.
3. **Registry-first dispatch, if/elif fallback.** `dispatch_command` consults
   `COMMANDS` before its remaining chain, so a migrated command must be *removed*
   from the `if/elif` chain in the same PR. `test_commands_registry.py` fails if
   a name is both registered and branched (a dead old body).

## Steps

1. Pick a command that does not share local state with its neighbours (most
   don't — each branch reads `sys.argv` and exits). Note its existing test
   (e.g. `merge-chunks` → `tests/test_merge_chunks_validation.py`).
2. Create `graphify/commands/<name>.py` with `def <name>() -> None:` and paste
   the branch body verbatim, dedented one level. Keep the branch's local imports
   inside the function.
3. Register it in `graphify/commands/__init__.py`: import the function and add
   `"<command-name>": <name>` to `COMMANDS`.
4. Delete the `elif cmd == "<command-name>":` branch (whole block) from
   `dispatch_command` in `cli.py`.
5. Run the command's existing test plus `tests/test_commands_registry.py`. Both
   must pass. Update the status table above.
