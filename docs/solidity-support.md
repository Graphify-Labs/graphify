# Solidity (.sol) support for graphify

Proposal for adding `.sol` files to graphify's code detection and AST extraction pipeline. Written after running graphify on Foundry/Hardhat repos and finding contracts silently skipped.

## The gap

Graphify picks up code in two places:

1. `graphify/detect.py` — `CODE_EXTENSIONS` decides what counts as code
2. `graphify/extract.py` — `_DISPATCH` maps a suffix to an extractor

`.sol` is in neither. Solidity files never enter the AST pass, so a web3 repo's contracts, interfaces, and import graph are invisible even when the rest of the project indexes fine.

The fix follows the same path as every other language in `ARCHITECTURE.md`: register the extension, add an extractor, wire tests.

## Recommended approach: tree-sitter-solidity

Use the existing `_extract_generic` framework with [tree-sitter-solidity](https://pypi.org/project/tree-sitter-solidity/) (v1.2.13 on PyPI, pre-built wheels, works with graphify's `tree-sitter>=0.23`).

Regex-only extraction (like Apex `.cls`) is a fallback option but a bad default for Solidity. Modifiers, NatSpec, assembly blocks, and multi-line headers break naive line parsers fast. The grammar already handles the constructs we care about.

A sample contract parses cleanly. Relevant node types from a quick probe:

- Declarations: `contract_declaration`, `interface_declaration`, `library_declaration`, `struct_declaration`, `enum_declaration`
- Members: `function_definition`, `constructor_definition`, `modifier_definition`, `event_definition`, `fallback_receive_definition`, `state_variable_declaration`
- Structure: `import_directive`, `inheritance_specifier`, `using_directive`, `pragma_directive`
- Behavior: `call_expression`, `new_expression`, `emit_statement`, `member_expression`

## What the extractor should emit

Every extractor returns `{nodes, edges}` (plus `raw_calls` for the cross-file second pass). Solidity should match that schema and the confidence rules in `validate.py`: structural facts are `EXTRACTED`, reasonable guesses are `INFERRED`.

### Nodes

| Solidity source | AST node | Graph label | Attached via |
|---------------|----------|-------------|--------------|
| `contract Foo` | `contract_declaration` | `Foo` | `contains` from file |
| `abstract contract Foo` | same + `abstract` child | `Foo` | `contains` |
| `interface IBar` | `interface_declaration` | `IBar` | `contains` |
| `library Lib` | `library_declaration` | `Lib` | `contains` |
| `struct Point` | `struct_declaration` | `Point` | `contains` |
| `enum Status` | `enum_declaration` | `Status` | `contains` |
| `function transfer()` | `function_definition` | `.transfer()` | `method` on parent |
| `constructor()` | `constructor_definition` | `.constructor()` | `method` |
| `modifier onlyOwner` | `modifier_definition` | `.onlyOwner()` | `method` |
| `event Transfer` | `event_definition` | `Transfer` | `contains` |
| `receive()` / `fallback()` | `fallback_receive_definition` | `.receive()` / `.fallback()` | `method` |

File-level node ID must use `_file_node_id()` / `_make_id(str(path))` so AST nodes line up with semantic subagent IDs (see #1033).

### Edges

**Inheritance.** Solidity uses one keyword for everything:

```solidity
contract Token is Base, IToken { }
```

Walk `inheritance_specifier` children on `contract_declaration`. Pre-scan the file (or corpus) for `interface_declaration` names so we can split relations correctly:

- Parent is a known interface → `implements`
- Parent is a contract or library → `inherits`
- Unknown name with `I` prefix → `implements` as a weak fallback only

Do not rely on the `I` prefix alone. Some codebases name interfaces without it.

**Imports.** Two common forms:

```solidity
import "./interfaces/IERC20.sol";
import {SafeMath, IERC721} from "@openzeppelin/contracts/utils/math/SafeMath.sol";
```

Add `_import_solidity()` modeled on `_import_c()`:

- Quoted relative paths (`./foo/Bar.sol`): resolve on disk relative to the importing file. If the target exists, emit `imports` to `_make_id(str(resolved_path))` so the edge lands on the real file node.
- Named brace imports: emit `imports` stubs for each symbol (`SafeMath`, `IERC721`).
- Bare or npm-style paths (`@openzeppelin/...`): stub by filename stem. Edge survives only if that file is in the corpus.

**Foundry remappings.** Real projects import via aliases like `@openzeppelin/contracts/...` while sources live under `lib/openzeppelin-contracts/contracts/...`. Without remapping resolution those imports become orphan stubs. Parse `remappings.txt` and `foundry.toml` `[profile.default.remappings]` (and per-profile overrides if cheap to read) to rewrite import paths before resolving. Same idea applies to Hardhat `paths` in config when present.

**Calls.** `call_expression` uses an `expression` field. Patterns:

| Pattern | Resolution |
|---------|------------|
| `transfer(to, amt)` | Same-contract function via `raw_calls` second pass |
| `Lib.add(1, 2)` | Library call; receiver is `Lib` |
| `IERC20(token).transfer(...)` | Nested `member_expression`; interface method stub |
| `new Token()` | `new_expression` → `instantiates` edge |
| `emit Transfer(...)` | `emit_statement` → `emits` edge to event node |
| `require(...)`, `assert(...)`, `revert(...)` | Filter as builtins; do not create god nodes |

Add Solidity builtins to a filter list (same idea as `_LANGUAGE_BUILTIN_GLOBALS` for JS): `require`, `assert`, `revert`, `keccak256`, `abi`, `msg`, `block`, `tx`, `type`, `gasleft`, etc.

**Using directives.**

```solidity
using SafeMath for uint256;
```

Emit `uses` or `references` from the enclosing contract to the `SafeMath` library node.

**State variables and mappings.**

```solidity
mapping(address => uint256) public balances;
```

Optional `field` / `references` edges from contract to type names. Lower priority than contracts, imports, and calls, but cheap if `state_variable_declaration` is already in the walk.

**NatSpec.** `/// @dev` and `/** @notice */` blocks could feed a rationale pass like Python docstrings (`rationale_for` edges). Nice to have if the walk already sees comment-adjacent nodes; otherwise defer.

**Config and artifact files (web3 ecosystem).** These are not `.sol` but show up in the same repos:

- `foundry.toml`, `remappings.txt`, `hardhat.config.ts/js`: config nodes for sources path, remappings, dependencies (similar to `.tf` / `.csproj` extractors)
- `broadcast/` / `deployments/` JSON: deployment records linking contracts to addresses (optional; noisy)
- ABI JSON in `out/` or `artifacts/`: external interface stubs

Treat config parsing as part of the same contribution if scope allows; otherwise note it in the issue and ship `.sol` first.

## Edge cases and how to handle them

**OpenZeppelin and other deps in `lib/` or `node_modules/`.** A full `graphify .` on a Foundry repo can pull in thousands of vendor files. `node_modules` is already skipped. `lib/` is not. Users should rely on `.graphifyignore` (e.g. `lib/`, `out/`, `cache/`). Document that in the PR or README snippet. Do not silently exclude `lib/` by default; some teams vendor only a few packages there.

**Multiple contracts per file.** Common for interfaces. One file node, multiple `contains` edges. Same pattern as other languages.

**`assembly { }` blocks.** Grammar may parse partially or fail on edge syntax. `_safe_extract` already catches per-file errors; partial graph is fine.

**Solidity version spread (0.4.x through 0.8.x).** tree-sitter-solidity targets most versions in active use. Test fixtures should use `pragma solidity ^0.8.0` and a second file with older syntax if we find gaps.

**Interface names without `I` prefix.** Pre-scan is the source of truth for `implements` vs `inherits`. Prefix heuristic is backup only.

**Diamond proxies (EIP-2535).** Facet routing is not visible from static AST alone. Semantic extraction or manual docs may be needed. Do not pretend the AST resolves delegatecall targets.

**Proxy patterns (UUPS, transparent, beacon).** `delegatecall` to implementation contracts can be detected as calls if the target is a literal contract name; opaque storage slots will not be. Mark uncertain edges `AMBIGUOUS` if we add them at all.

**Import paths that only resolve with remappings.** Without remapping support, `@openzeppelin/...` imports point at stubs. This is the main gap for real Foundry repos and should be in the initial implementation, not a follow-up.

**Cross-file contract extensions.** Solidity has no `extension Foo` split across files like Swift. Inheritance and imports cover the usual cases.

**Generated files in `out/` and `cache/`.** Foundry compiler output. Recommend ignoring via `.graphifyignore` template; optionally add `out/` and `cache/` to noise dirs if the project agrees (check issue discussion first).

**SCIP / external indexers.** graphify has `scip_ingest` for other languages. No standard Solidity SCIP indexer in most repos. AST path is the right default.

## Implementation checklist

### Dependencies

`pyproject.toml`:

```
tree-sitter-solidity>=1.2,<2.0
```

Add to main `dependencies` (grammar has wheels; not optional like `tree-sitter-dm`).

### Code changes

| File | Change |
|------|--------|
| `graphify/detect.py` | Add `'.sol'` to `CODE_EXTENSIONS` |
| `graphify/extract.py` | `_SOLIDITY_CONFIG`, `_import_solidity()`, `_solidity_inheritance_hook()` in `_extract_generic` walk, `extract_solidity()`, `".sol": extract_solidity` in `_DISPATCH` |
| `graphify/watch.py` | Picks up `CODE_EXTENSIONS` automatically |
| `graphify/__main__.py` | Extension list in help text if maintained manually |
| Skill `update.md` fragments / `tools/skillgen` | Add `.sol` to `code_exts` sets |
| `CHANGELOG.md` | Entry under next release |

### `_SOLIDITY_CONFIG` sketch

```python
_SOLIDITY_CONFIG = LanguageConfig(
    ts_module="tree_sitter_solidity",
    class_types=frozenset({
        "contract_declaration",
        "interface_declaration",
        "library_declaration",
        "struct_declaration",
        "enum_declaration",
    }),
    function_types=frozenset({
        "function_definition",
        "constructor_definition",
        "modifier_definition",
        "fallback_receive_definition",
    }),
    import_types=frozenset({"import_directive"}),
    call_types=frozenset({"call_expression", "new_expression"}),
    call_function_field="expression",
    call_accessor_node_types=frozenset({"member_expression"}),
    call_accessor_field="identifier",
    name_fallback_child_types=("identifier",),
    body_fallback_child_types=("contract_body", "function_body"),
    function_boundary_types=frozenset({
        "function_definition",
        "constructor_definition",
        "modifier_definition",
    }),
    import_handler=_import_solidity,
)

def extract_solidity(path: Path) -> dict:
    return _extract_generic(path, _SOLIDITY_CONFIG)
```

Solidity-specific logic (inheritance split, `emit_statement`, remapping-aware import resolution) lives in dedicated helpers called from the `_extract_generic` walk when `config.ts_module == "tree_sitter_solidity"`.

### Tests

| File | Purpose |
|------|---------|
| `tests/fixtures/sample.sol` | One file with contract, interface, library, imports, inheritance, events, calls |
| `tests/fixtures/solidity/Base.sol` | Parent contract for cross-file import test |
| `tests/fixtures/solidity/interfaces/IERC20.sol` | Relative import target |
| `tests/fixtures/foundry.toml` + `remappings.txt` | Remapping resolution test (if implemented) |
| `tests/test_solidity.py` | Dispatch, CODE_EXTENSIONS, entities, imports, inherits/implements, calls, emits, new, no dangling edges |

Follow patterns in `tests/test_languages.py` and `tests/test_astro_extraction.py` (extension registered in detect + dispatch).

### Validation

```bash
uv sync --all-extras
uv run pytest tests/test_solidity.py tests/test_detect.py -q
uv run graphify extract /path/to/foundry-project --no-cluster
```

## Prior art in this repo

Similar landings:

- `.psm1` PowerShell (#1315): `CODE_EXTENSIONS` + `_DISPATCH` gap
- `.astro` (#850): extension + regex/AST hybrid
- `.cls` Apex: regex extractor when no PyPI grammar exists
- `.tf` / HCL: optional extra with tree-sitter grammar

Solidity is closer to Java/C# (tree-sitter + `_extract_generic` + import handler + inheritance hook).

## Open questions

1. Should `lib/` be added to `_SKIP_DIRS`? Leaning no; `.graphifyignore` is enough and more flexible.
2. Optional `[solidity]` extra vs main dependency? Grammar has wheels on all major platforms; main deps is simpler.
3. Include `hardhat.config` / `foundry.toml` parsing in the same PR or a fast follow-up?

## References

- [tree-sitter-solidity on PyPI](https://pypi.org/project/tree-sitter-solidity/)
- [graphify ARCHITECTURE.md](../ARCHITECTURE.md) — adding a language extractor
- [Foundry remappings](https://book.getfoundry.sh/projects/project-layout#remappings)
