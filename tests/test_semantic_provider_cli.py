from __future__ import annotations

from graphify_semantic_providers import cli
from graphify_semantic_providers.contracts import ProviderRun, ProviderSpec, ProviderStatus
from graphify_semantic_providers.registry import ProviderRegistry


def _provider(name: str, extension: str) -> ProviderSpec:
    return ProviderSpec(
        name=name,
        languages=(name,),
        extensions=(extension,),
        command=(name,),
        binary_env=f"GRAPHIFY_SEMANTIC_{name.upper()}_BINARY",
    )


def test_explicit_provider_does_not_also_select_auto(tmp_path, monkeypatch) -> None:
    registry = ProviderRegistry()
    registry.register(_provider("chosen", ".chosen"))
    registry.register(_provider("other", ".other"))
    calls: list[str] = []

    monkeypatch.setattr(cli, "_registry", lambda manifests: registry)
    monkeypatch.setattr(cli, "discover_files", lambda root, spec, limit: [root / "fixture"])

    def fake_run(spec, root, **kwargs):
        calls.append(spec.name)
        return ProviderRun(provider=spec.name, status=ProviderStatus.COMPLETED)

    monkeypatch.setattr(cli, "run_provider", fake_run)
    out = tmp_path / "runs.json"
    result = cli.main(["run", str(tmp_path), "--provider", "chosen", "--out", str(out)])

    assert result == 0
    assert calls == ["chosen"]


def test_omitted_provider_keeps_auto_discovery(tmp_path, monkeypatch) -> None:
    registry = ProviderRegistry()
    registry.register(_provider("chosen", ".chosen"))
    registry.register(_provider("other", ".other"))
    calls: list[str] = []

    monkeypatch.setattr(cli, "_registry", lambda manifests: registry)
    monkeypatch.setattr(
        cli,
        "discover_files",
        lambda root, spec, limit: [root / "fixture"] if spec.name == "other" else [],
    )

    def fake_run(spec, root, **kwargs):
        calls.append(spec.name)
        return ProviderRun(provider=spec.name, status=ProviderStatus.COMPLETED)

    monkeypatch.setattr(cli, "run_provider", fake_run)
    out = tmp_path / "runs.json"
    result = cli.main(["run", str(tmp_path), "--out", str(out)])

    assert result == 0
    assert calls == ["other"]
