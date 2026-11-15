from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from graphify_semantic_providers.contracts import ProviderStatus
from graphify_semantic_providers.contracts import ProviderSpec
from graphify_semantic_providers.lsp import (
    _provider_environment,
    discover_files,
    resolve_command,
    run_provider,
)
from graphify_semantic_providers.registry import builtin_registry


class FakeTransport:
    instances: list["FakeTransport"] = []

    def __init__(self, command: tuple[str, ...], root: Path) -> None:
        self.command = command
        self.root = root
        self.notifications: list[dict[str, Any]] = []
        self.closed = False
        self.requests: list[str] = []
        FakeTransport.instances.append(self)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.notifications.append({"method": method, "params": params})

    def request(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        self.requests.append(method)
        source_uri = (self.root / "src" / "lib.rs").as_uri()
        if method == "initialize":
            return {
                "serverInfo": {"version": "test-1"},
                "capabilities": {
                    "referencesProvider": True,
                    "implementationProvider": True,
                    "callHierarchyProvider": True,
                },
            }
        if method == "textDocument/documentSymbol":
            return [
                {
                    "name": "App",
                    "kind": 5,
                    "range": _range(0),
                    "selectionRange": _range(0),
                    "children": [
                        {
                            "name": "run",
                            "kind": 6,
                            "range": _range(1),
                            "selectionRange": _range(1),
                        }
                    ],
                }
            ]
        if method == "textDocument/references":
            return [{"uri": source_uri, "range": _range(2)}]
        if method == "textDocument/implementation":
            return []
        if method == "textDocument/prepareCallHierarchy":
            return [
                {"name": "run", "uri": source_uri, "range": _range(1), "selectionRange": _range(1)}
            ]
        if method == "callHierarchy/outgoingCalls":
            return [
                {
                    "to": {
                        "name": "helper",
                        "kind": 12,
                        "uri": source_uri,
                        "range": _range(4),
                        "selectionRange": _range(4),
                    },
                    "fromRanges": [_range(2)],
                }
            ]
        if method == "shutdown":
            return None
        raise AssertionError(f"unexpected request: {method}")

    def close(self, timeout: float = 2.0) -> None:
        self.closed = True


def _range(line: int) -> dict[str, dict[str, int]]:
    return {
        "start": {"line": line, "character": 0},
        "end": {"line": line, "character": 4},
    }


def test_generic_lsp_runner_emits_symbols_calls_references_and_containment(tmp_path: Path) -> None:
    source = tmp_path / "src" / "lib.rs"
    source.parent.mkdir()
    source.write_text("struct App;\nfn run() {}\n", encoding="utf-8")
    spec = builtin_registry().get("rust-analyzer")

    run = run_provider(
        spec,
        tmp_path,
        max_relationship_requests=20,
        transport_factory=FakeTransport,
    )

    assert run.status is ProviderStatus.COMPLETED
    assert run.version == "test-1"
    assert run.files_processed == 1
    assert {node["label"] for node in run.nodes} >= {"App", "run", "helper", "lib.rs"}
    assert {edge["relation"] for edge in run.edges} >= {"contains", "references", "calls"}
    assert all(node.get("source_file") == "src/lib.rs" for node in run.nodes)
    assert all(node["metadata"]["evidence_provider"] == "rust-analyzer" for node in run.nodes)
    assert all(node["metadata"]["evidence_run_id"] == run.run_id for node in run.nodes)
    assert all(node["metadata"]["evidence_timestamp"] == run.timestamp for node in run.nodes)
    assert FakeTransport.instances[-1].closed is True


class PortableTransport:
    """Small capability-neutral server used to prove every profile's LSP shape."""

    instances: list["PortableTransport"] = []

    def __init__(self, command: tuple[str, ...], root: Path) -> None:
        self.command = command
        self.root = root
        self.notifications: list[dict[str, Any]] = []
        self.current_uri = ""
        PortableTransport.instances.append(self)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.notifications.append({"method": method, "params": params})
        if method == "textDocument/didOpen":
            self.current_uri = params["textDocument"]["uri"]

    def request(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        if method == "initialize":
            return {"serverInfo": {"version": "portable-test"}, "capabilities": {}}
        if method == "textDocument/documentSymbol":
            return [
                {
                    "name": "EntryPoint",
                    "kind": 12,
                    "range": _range(0),
                    "selectionRange": _range(0),
                }
            ]
        if method == "shutdown":
            return None
        raise AssertionError(f"unexpected request: {method}")

    def close(self, timeout: float = 2.0) -> None:
        return None


@pytest.mark.parametrize(
    ("provider_name", "relative_path", "language_id"),
    [
        ("rust-analyzer", "src/lib.rs", "rust"),
        ("typescript-language-server", "src/app.ts", "typescript"),
        ("typescript-language-server", "src/app.jsx", "javascriptreact"),
        ("eclipse-jdtls", "src/App.java", "java"),
        ("kotlin-lsp", "src/App.kt", "kotlin"),
        ("csharp-ls", "src/App.cs", "csharp"),
        ("pyright", "src/app.py", "python"),
        ("gopls", "src/app.go", "go"),
        ("phpactor", "src/App.php", "php"),
        ("ruby-lsp", "src/app.rb", "ruby"),
    ],
)
def test_builtin_profiles_share_the_bounded_lsp_contract(
    tmp_path: Path, provider_name: str, relative_path: str, language_id: str
) -> None:
    source = tmp_path / relative_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("fixture\n", encoding="utf-8")

    run = run_provider(
        builtin_registry().get(provider_name),
        tmp_path,
        max_relationship_requests=10,
        transport_factory=PortableTransport,
    )

    assert run.status is ProviderStatus.COMPLETED
    assert [node["label"] for node in run.nodes] == ["EntryPoint"]
    opened = next(
        notification
        for notification in PortableTransport.instances[-1].notifications
        if notification["method"] == "textDocument/didOpen"
    )
    assert opened["params"]["textDocument"]["languageId"] == language_id
    assert run.nodes[0]["metadata"]["semantic_language"] == language_id
    assert run.nodes[0]["metadata"]["evidence_provider_kind"] == "semantic"


def test_provider_budget_is_explicit_not_silently_expanded(tmp_path: Path) -> None:
    source = tmp_path / "src" / "lib.rs"
    source.parent.mkdir()
    source.write_text("struct App;\n", encoding="utf-8")
    run = run_provider(
        builtin_registry().get("rust-analyzer"),
        tmp_path,
        max_relationship_requests=1,
        transport_factory=FakeTransport,
    )
    assert run.status is ProviderStatus.BUDGET_EXHAUSTED
    assert run.reason_code == "semantic_budget_exhausted"
    assert run.relationship_requests == 1
    assert run.requests == 3  # initialize + document symbols + one relationship


def test_symbol_budget_also_bounds_relationship_targets(tmp_path: Path) -> None:
    source = tmp_path / "src" / "lib.rs"
    source.parent.mkdir()
    source.write_text("struct App;\nfn run() {}\n", encoding="utf-8")
    run = run_provider(
        builtin_registry().get("rust-analyzer"),
        tmp_path,
        max_symbols=2,
        max_relationship_requests=20,
        transport_factory=FakeTransport,
    )
    assert run.status is ProviderStatus.BUDGET_EXHAUSTED
    assert len(run.nodes) <= 2


def test_discovery_excludes_build_outputs_and_out_of_root_symlinks(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.go").write_text("package main", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "ignored.go").write_text("package ignored", encoding="utf-8")
    outside = tmp_path.parent / "outside.go"
    outside.write_text("package outside", encoding="utf-8")
    try:
        (tmp_path / "src" / "escape.go").symlink_to(outside)
    except OSError:
        pass
    files = discover_files(tmp_path, builtin_registry().get("gopls"), 10)
    assert [path.relative_to(tmp_path).as_posix() for path in files] == ["src/main.go"]


def test_command_resolution_preserves_toolchain_proxy_symlink(
    tmp_path: Path, monkeypatch, requires_symlinks
) -> None:
    target = Path("/usr/bin/true")
    alias = tmp_path / "language-server-proxy"
    alias.symlink_to(target)
    monkeypatch.setenv("TEST_LSP_BINARY", str(alias))
    spec = ProviderSpec(
        name="test",
        languages=("test",),
        extensions=(".test",),
        command=("ignored", "--stdio"),
        binary_env="TEST_LSP_BINARY",
    )
    assert resolve_command(spec) == (str(alias.absolute()), "--stdio")


def test_provider_environment_does_not_forward_unrelated_credentials(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "secret-canary")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-canary")

    environment = _provider_environment()

    assert environment["PATH"] == "/usr/bin"
    assert "AWS_ACCESS_KEY_ID" not in environment
    assert "CLOUDFLARE_API_TOKEN" not in environment
