"""Subcommand handlers split out of ``graphify.cli.dispatch_command`` (#2474).

``registry.COMMANDS`` names a handler for each migrated command and
``dispatch_command`` consults it before its remaining ``elif`` chain, so
commands move here one slice at a time without changing behavior.

Porting a command:

- Move the ``elif cmd == ...`` body verbatim into a zero-argument function.
  It keeps reading ``sys.argv`` and calling ``sys.exit`` exactly as the branch
  did; argument parsing changes belong in a separate PR.
- Keep the branch's lazy imports inside the handler. Helpers that still live
  in ``graphify.cli`` are imported at call time, which also avoids a cycle.
- Add the command to ``registry.COMMANDS`` and delete its branch;
  ``tests/test_commands_registry.py`` fails if both exist.
- Aliases (``god-nodes``/``god_nodes``) stay explicit entries in the table.
"""
