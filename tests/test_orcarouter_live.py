"""Live OrcaRouter checks: the real provider path against the real gateway.

Skipped unless ``ORCAROUTER_API_KEY`` is exported, which is how the integration
is exercised end to end: the credential belongs to that run and is never
committed. Everything below calls the implemented provider code —
``graphify.orcarouter`` for the origins, the credential seam and the catalog,
``graphify.llm`` for inference — rather than a hand-rolled HTTP request, so a
pass means the wiring works, not merely that the gateway is reachable.

The catalog and inference checks must reach ``https://api.orcarouter.ai/v1``;
nothing here touches the auth origin, which is a separate host by design.
"""

from __future__ import annotations

import os

import pytest

from graphify import llm
from graphify import orcarouter as orca

#: Read at import time: the repository's own ``_isolate_backend_env`` fixture
#: clears every backend key (including ORCAROUTER_API_KEY) before each test, so
#: the exported credential is captured before fixtures run and restored per test.
_ENV_KEY = os.environ.get("ORCAROUTER_API_KEY", "").strip()

pytestmark = pytest.mark.skipif(
    not _ENV_KEY,
    reason="set ORCAROUTER_API_KEY to run the live OrcaRouter checks",
)

_PING = "Reply with the single word: ok"
#: Generous enough that a reasoning model, which spends part of the budget on
#: its reasoning channel before emitting any content, still returns text.
_PING_MAX_TOKENS = 128
_callable_cache: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _restore_live_key(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", _ENV_KEY)


def _first_callable_chat_model() -> str:
    """The first chat-capable catalog model this key can actually answer with.

    Workspace catalogs are scoped to what the workspace may route to, and an
    individual key can be narrowed further still, so the callable subset is
    discovered rather than assumed. Two answers are normal and mean "try the
    next candidate" rather than "the integration is broken": a
    ``model_access_denied`` refusal, which is a per-key scope answer, and an
    empty completion, which a routing alias can return when it has no upstream
    to hand the request to. The assertion that matters is at the end — some
    model in this workspace's own catalog produced a real completion through
    the provider path.
    """
    if "model" in _callable_cache:
        return _callable_cache["model"]
    refusals: list[str] = []
    for model in orca.models_for_capability("chat").models:
        try:
            reply = llm._call_llm(_PING, backend="orcarouter", model=model.id, max_tokens=_PING_MAX_TOKENS)
        except Exception as exc:  # noqa: BLE001 — the message is the diagnosis
            refusals.append(f"{model.id}: {exc}")
            continue
        if not reply.strip():
            refusals.append(f"{model.id}: returned an empty completion")
            continue
        _callable_cache["model"] = model.id
        return model.id
    pytest.fail(
        "No chat-capable model in the live catalog answered through the "
        "orcarouter backend. Checked: " + " | ".join(refusals[:8])
    )


def test_live_catalog_is_discovered_from_the_api_origin():
    catalog = orca.load_catalog()

    assert catalog.source == "live", (catalog.source, catalog.error)
    assert not catalog.degraded
    assert len(catalog.models) > 1
    if not (os.environ.get("ORCA_API_BASE_URL") or os.environ.get("ORCA_BASE_URL")):
        assert orca.api_base() == orca.DEFAULT_API_BASE
    # Ids are preserved verbatim, vendor namespace included.
    assert any("/" in model.id for model in catalog.models)


def test_live_chat_options_only_contain_declared_chat_routes():
    models = orca.models_for_capability("chat").models

    assert models, "the live catalog offered no chat-capable model"
    for model in models:
        assert set(model.supported_endpoint_types) & set(orca.TEXT_ENDPOINT_TYPES), model.id
        assert orca._model_supports(model, "chat"), model.id


def test_live_vision_options_declare_image_input():
    models = orca.models_for_capability("vision").models

    # A workspace may expose none; what must hold is that anything offered here
    # declares the modality rather than merely sounding multimodal.
    for model in models:
        assert "image" in model.input_modalities, model.id
        assert orca._model_supports(model, "vision"), model.id


def test_live_inference_goes_through_the_credential_seam():
    model = _first_callable_chat_model()

    # The same seam a pasted key and a PKCE login both feed.
    assert llm._get_backend_api_key("orcarouter") == os.environ["ORCAROUTER_API_KEY"]

    reply = llm._call_llm(_PING, backend="orcarouter", model=model, max_tokens=_PING_MAX_TOKENS)

    assert reply.strip(), f"empty reply from {model}"


def test_live_an_unusable_selection_is_refused_before_it_is_sent():
    catalog = orca.load_catalog()
    unusable = [m.id for m in catalog.models if not orca._model_supports(m, "chat")]
    if not unusable:
        pytest.skip("this workspace's catalog is entirely chat-capable")

    with pytest.raises(orca.OrcaRouterError) as excinfo:
        orca.resolve_model(unusable[0], catalog=catalog)

    assert unusable[0] in str(excinfo.value)
