"""JSON Schema files must not be mistaken for config manifests.

`_is_config_json()` decides whether a `.json` file is worth AST-walking. It
matches by filename first, then falls back to a root-key probe. But `$schema`
was in that probe's key set, and `$schema` is the *defining marker* of a JSON
Schema -- so every schema document satisfied the probe and got walked in full,
re-opening the keyword-node explosion #1224 closed for data JSON.

One 160 KB contract contributed 362 nodes whose labels were bare schema
keywords (`description`, `type`, `$ref`, `required`, `properties`), plus ~12
schema-only communities that polluted clustering, god-node analysis and
`GRAPH_REPORT.md` -- 13% of a 2,725-node graph (#2255).

These tests pin both directions, because the fix removes keys from the probe and
the risk is over-correcting into skipping real configs:

- a file that *is* a schema (`$schema` plus a schema-definition marker) is
  skipped, not walked
- a root-level `$ref`, which is a schema construct and never a config signal,
  no longer implies config
- every config shape that reaches the probe -- including configs that carry
  `$schema` themselves -- is still extracted

The filename branches run before the probe, so `biome.json`/`renovate.json`/
`package.json` never depended on the probe at all; those are pinned explicitly
anyway, because a fix here must not be able to change them.
"""
from pathlib import Path

from graphify.extractors.json_config import extract_json

# A JSON Schema as a contract file actually looks like: `$id` + `$defs`.
SCHEMA_WITH_DEFS = '''\
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/events-v1.json",
  "title": "Event catalogue",
  "$defs": {
    "dataClassification": {
      "description": "Handling class for the event payload.",
      "type": "string",
      "enum": ["Public", "Internal", "CUI"]
    },
    "event": {
      "description": "One domain event.",
      "type": "object",
      "required": ["id", "kind"],
      "properties": {
        "id": {"description": "Stable id.", "type": "string"},
        "kind": {"description": "Event kind.", "type": "string"},
        "seq": {"description": "Sequence.", "type": "integer", "minimum": 0},
        "tags": {"description": "Tags.", "type": "array",
                 "items": {"type": "string"}},
        "shape": {"description": "One shape.", "oneOf": [{"type": "string"}]}
      },
      "additionalProperties": false
    }
  },
  "$ref": "#/$defs/event"
}
'''

SCHEMA_WITH_LEGACY_DEFS = '''\
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "definitions": {
    "point": {"description": "A point.", "type": "object"}
  },
  "$ref": "#/definitions/point"
}
'''

# A root-level $ref is a schema construct, never a config signal.
SCHEMA_REF_ONLY = '{"$ref": "https://example.com/other.json"}'

# Real configs that carry $schema themselves. These point at their OWN tool's
# schema, not at the JSON Schema meta-schema -- which is exactly why $schema
# cannot be read as "this file is a schema".
BIOME = '''\
{
  "$schema": "https://biomejs.dev/schemas/1.7.0/schema.json",
  "files": {"include": ["src"]},
  "linter": {"enabled": true}
}
'''

RENOVATE = '''\
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:base"]
}
'''

# Arbitrary filename -> only the root-key probe can catch these.
PROBE_EXTENDS = '{"extends": "./base.json", "rules": {"eqeqeq": "error"}}'
PROBE_COMPILER = '{"compilerOptions": {"strict": true, "target": "es2022"}}'
SUFFIX_TSCONFIG = '{"compilerOptions": {"strict": true}}'


def _write(tmp_path, name, body):
    p = Path(tmp_path) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _labels(result):
    return [n["label"] for n in result["nodes"]]


def _is_skipped(result):
    return result.get("skipped") == "data json (not a config/manifest)"


# --- the schema side: these must stop being walked -------------------------

def test_schema_with_defs_is_skipped_not_walked(tmp_path):
    r = extract_json(_write(tmp_path, "events-v1.json", SCHEMA_WITH_DEFS))
    assert _is_skipped(r), r
    assert r["nodes"] == []
    assert r["edges"] == []


def test_schema_with_legacy_definitions_is_skipped(tmp_path):
    # draft-07 schemas spell the same thing `definitions`.
    r = extract_json(_write(tmp_path, "legacy.json", SCHEMA_WITH_LEGACY_DEFS))
    assert _is_skipped(r), r
    assert r["nodes"] == []


def test_schema_with_defs_in_subdirectory_is_skipped(tmp_path):
    # The reporter's file lived at contracts/events-v1.json, i.e. the filename
    # branch could never have matched it -- only the probe could.
    r = extract_json(_write(tmp_path, "contracts/events-v1.json", SCHEMA_WITH_DEFS))
    assert _is_skipped(r), r


def test_root_level_ref_alone_is_skipped(tmp_path):
    r = extract_json(_write(tmp_path, "ref.json", SCHEMA_REF_ONLY))
    assert _is_skipped(r), r
    assert r["nodes"] == []


def test_schema_produces_no_keyword_nodes(tmp_path):
    # The actual symptom: bare schema keywords became graph nodes.
    r = extract_json(_write(tmp_path, "events-v1.json", SCHEMA_WITH_DEFS))
    keywords = {"description", "type", "properties", "required",
                "additionalProperties", "oneOf", "items", "enum"}
    assert not keywords & set(_labels(r)), _labels(r)


# --- the config side: the fix must not over-correct ------------------------

def test_biome_json_with_its_own_schema_key_is_still_extracted(tmp_path):
    # biome.json points $schema at biome's schema, not at the meta-schema. It is
    # filename-matched, so it never depended on the probe -- pinned so this fix
    # provably cannot affect it.
    r = extract_json(_write(tmp_path, "biome.json", BIOME))
    assert not _is_skipped(r), r
    assert "linter" in _labels(r)


def test_renovate_json_with_schema_and_extends_is_still_extracted(tmp_path):
    r = extract_json(_write(tmp_path, "renovate.json", RENOVATE))
    assert not _is_skipped(r), r
    assert "extends" in _labels(r)


def test_package_json_is_still_extracted(tmp_path):
    r = extract_json(_write(tmp_path, "package.json",
                            '{"name": "x", "devDependencies": {"jest": "^29"}}'))
    assert not _is_skipped(r), r
    assert "devDependencies" in _labels(r)


def test_probe_still_recognises_extends_by_arbitrary_filename(tmp_path):
    # `extends` stays in the probe; only $ref left.
    r = extract_json(_write(tmp_path, "custom.config.json", PROBE_EXTENDS))
    assert not _is_skipped(r), r
    assert "extends" in _labels(r)


def test_probe_still_recognises_compileroptions_by_arbitrary_filename(tmp_path):
    r = extract_json(_write(tmp_path, "weird.json", PROBE_COMPILER))
    assert not _is_skipped(r), r
    assert "compilerOptions" in _labels(r)


def test_compound_suffix_match_is_unaffected(tmp_path):
    r = extract_json(_write(tmp_path, "api.tsconfig.json", SUFFIX_TSCONFIG))
    assert not _is_skipped(r), r
    assert "compilerOptions" in _labels(r)


def test_dev_dependencies_probe_still_works(tmp_path):
    r = extract_json(_write(tmp_path, "deps.json", PROBE_COMPILER))
    assert not _is_skipped(r), r


# --- documented boundary, pinned so a future change is deliberate ----------

def test_minimal_schema_without_defs_or_id_is_still_walked(tmp_path):
    """A hand-written schema carrying only `$schema` + `properties` is still walked.

    This is a known, accepted residual: catching it needs a keyword-density
    heuristic, which would risk the opposite error -- skipping a real config
    whose keys happen to overlap schema vocabulary. Pinned here so that closing
    the gap later is a deliberate change with a test, not an accident.

    `$defs`, `$id` and `definitions` are spec-defined and value-independent, so
    they are the markers the fix relies on; this case has none of them.
    """
    body = ('{"$schema": "https://json-schema.org/draft/2020-12/schema",'
            ' "type": "object", "properties": {"a": {"type": "string"}}}')
    r = extract_json(_write(tmp_path, "minimal.schema.json", body))
    assert not _is_skipped(r), r
    assert "properties" in _labels(r)


# --- determinism -----------------------------------------------------------

def test_classification_is_deterministic_across_repeated_calls(tmp_path):
    # Extraction must not depend on ordering or ambient state (CONTRIBUTING #3).
    p = _write(tmp_path, "events-v1.json", SCHEMA_WITH_DEFS)
    first = _labels(extract_json(p))
    for _ in range(5):
        assert _labels(extract_json(p)) == first