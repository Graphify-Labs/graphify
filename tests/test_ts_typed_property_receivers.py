"""Calls on local aliases of explicitly typed TypeScript object properties."""

import pytest

from graphify.extract import extract


def _calls(tmp_path, source, *, incremental=False):
    paths = [tmp_path / name for name in ("ports.ts", "other.ts", "caller.ts")]
    paths[0].write_text(
        "export type Port = Readonly<{ inspect(): number; redeem(): number }>;\n"
        "export interface OtherPort { inspect(): number }\n",
        encoding="utf-8",
    )
    paths[1].write_text("export interface Port { inspect(): number }\n", encoding="utf-8")
    paths[2].write_text(source, encoding="utf-8")
    cache = tmp_path / "cache"
    if incremental:
        baseline = extract(paths[:2], root=tmp_path, cache_root=cache, parallel=False)
        result = extract(
            paths[2:], root=tmp_path, cache_root=cache, parallel=False,
            resolution_context_nodes=baseline["nodes"], resolution_context_edges=baseline["edges"],
        )
        nodes = {node["id"]: node for node in baseline["nodes"] + result["nodes"]}
        ownership_edges = baseline["edges"]
    else:
        result = extract(paths, root=tmp_path, cache_root=cache, parallel=False)
        nodes = {node["id"]: node for node in result["nodes"]}
        ownership_edges = result["edges"]
    owners = {edge["target"]: nodes[edge["source"]]["label"]
              for edge in ownership_edges if edge["relation"] == "method"}
    return {
        (nodes[edge["source"]]["label"], nodes[edge["target"]]["source_file"],
         owners.get(edge["target"]), nodes[edge["target"]]["label"], edge["source_location"])
        for edge in result["edges"] if edge["relation"] == "calls"
    }


@pytest.mark.parametrize("annotation", ["{ authority: Port }", "Readonly<{ authority: Port }>", "Ports"])
@pytest.mark.parametrize("incremental", [False, True])
def test_property_alias_resolves_calls_in_callback(tmp_path, annotation, incremental):
    calls = _calls(tmp_path, f"""\
import type {{ Port }} from './ports';
type Ports = Readonly<{{ authority: Port }}>;
export const acquire = (ports: {annotation}) => {{
  const label = 'acquirer', authority = ports.authority;
  const run = trace(function* () {{
    yield* effect(() => authority.inspect());
    yield* effect(() => authority.redeem());
  }});
  return {{ label, run }};
}};
""", incremental=incremental)
    assert calls == {
        ("acquire()", "ports.ts", "Port", ".inspect()", "L6"),
        ("acquire()", "ports.ts", "Port", ".redeem()", "L7"),
    }


def test_property_alias_uses_lexical_bindings_at_declaration_and_call(tmp_path):
    calls = _calls(tmp_path, """\
import type { Port, OtherPort } from './ports';
function first(ports: { authority: Port }) {
  const authority = ports.authority;
  function shadowed(authority) { authority.inspect(); }
  {
    const authority = {};
    authority.inspect();
  }
  function inner(ports: { authority: OtherPort }) {
    const authority = ports.authority;
    authority.inspect();
  }
  authority.inspect();
}
function second(ports) {
  const authority = ports.authority;
  authority.inspect();
}
function shadowedSource(ports: { authority: Port }) {
  {
    const ports = { authority: {} };
    const authority = ports.authority;
    authority.inspect();
  }
}
""")
    assert calls == {
        ("inner()", "ports.ts", "OtherPort", ".inspect()", "L11"),
        ("first()", "ports.ts", "Port", ".inspect()", "L13"),
    }


def test_property_alias_takes_precedence_over_file_wide_receiver_type(tmp_path):
    calls = _calls(tmp_path, """\
import type { OtherPort } from './ports';
type LocalPort = { inspect(): number };
function direct(authority: OtherPort) { return authority.inspect(); }
function acquire(ports: { authority: LocalPort }) {
  const authority = ports.authority;
  return authority.inspect();
}
""")
    assert calls == {
        ("direct()", "ports.ts", "OtherPort", ".inspect()", "L3"),
        ("acquire()", "caller.ts", "LocalPort", ".inspect()", "L6"),
    }


def test_unsupported_shapes_do_not_guess_from_property_or_method_name(tmp_path):
    calls = _calls(tmp_path, """\
import type { OtherPort } from './ports';
function noImport(ports: { authority: Port }) {
  const authority = ports.authority;
  authority.inspect();
}
function typeParameter<OtherPort>(ports: { authority: OtherPort }) {
  const authority = ports.authority;
  authority.inspect();
}
function shadowedReadonly<Readonly>(ports: Readonly<{ authority: OtherPort }>) {
  const authority = ports.authority;
  authority.inspect();
}
function mutable(ports: { authority: OtherPort }) {
  let authority = ports.authority;
  authority.inspect();
}
function missingMember(ports: { authority: OtherPort }) {
  const authority = ports.authority;
  authority._inspect();
}
function beforeDeclaration(ports: { authority: OtherPort }) {
  authority.inspect();
  const authority = ports.authority;
}
""")
    assert calls == set()
