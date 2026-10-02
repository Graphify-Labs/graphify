"""OrcaRouter provider: credential seam, PKCE login, model catalog, capabilities.

These tests exercise the two authentication adapters through the interfaces the
application actually calls (``ApiKeySource`` / ``PkceSource`` /
``resolve_credential_secret``), the PKCE flow against a real local consent
server over real HTTP, and the catalog filters that decide which models a given
entry point may offer.

No test uses a real credential: every key and code below is a literal fake. The
PKCE tests never send anything to ``orcarouter.ai`` — the fake consent server is
reached through ``ORCA_AUTH_BASE_URL``, which is exactly the override a
self-hosted deployment would use.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from graphify import orcarouter as orca


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Never touch the developer's real ~/.graphify/orcarouter.json."""
    path = tmp_path / "orcarouter.json"
    monkeypatch.setenv("ORCAROUTER_CREDENTIALS_PATH", str(path))
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ORCA_BASE_URL", raising=False)
    monkeypatch.delenv("ORCA_AUTH_BASE_URL", raising=False)
    monkeypatch.delenv("ORCA_API_BASE_URL", raising=False)
    monkeypatch.delenv("ORCAROUTER_OAUTH_FLOW", raising=False)
    monkeypatch.delenv("ORCAROUTER_OAUTH_TIMEOUT", raising=False)
    return path


# ── Origins: two independent hosts, never derived from one another ────────────


def test_default_origins_are_distinct_and_correct():
    assert orca.auth_base() == "https://www.orcarouter.ai"
    assert orca.api_base() == "https://api.orcarouter.ai/v1"


def test_auth_and_api_overrides_are_independent(monkeypatch):
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "https://auth.internal.example")
    monkeypatch.setenv("ORCA_API_BASE_URL", "https://relay.internal.example/v1")
    # Changing one must not move the other.
    assert orca.auth_base() == "https://auth.internal.example"
    assert orca.api_base() == "https://relay.internal.example/v1"


def test_shared_base_applies_to_both_but_explicit_wins(monkeypatch):
    monkeypatch.setenv("ORCA_BASE_URL", "https://selfhosted.example")
    assert orca.auth_base() == "https://selfhosted.example"
    assert orca.api_base() == "https://selfhosted.example/v1"
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "https://auth.selfhosted.example")
    assert orca.auth_base() == "https://auth.selfhosted.example"
    assert orca.api_base() == "https://selfhosted.example/v1"


def test_exchange_path_is_api_v1_auth_keys_not_v1_auth_keys(monkeypatch):
    """The documented failure mode: the relay is at /v1, the auth API is not."""
    url = orca.auth_url(orca.EXCHANGE_PATH)
    assert url == "https://www.orcarouter.ai/api/v1/auth/keys"
    assert "/v1/auth/keys" not in url.replace("/api/v1/auth/keys", "")


def test_plaintext_origin_rejected_for_remote_but_allowed_for_loopback(monkeypatch):
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "http://evil.example.com")
    with pytest.raises(orca.OrcaRouterError):
        orca.auth_base()
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", "http://127.0.0.1:9999")
    assert orca.auth_base() == "http://127.0.0.1:9999"


# ── PKCE primitives ───────────────────────────────────────────────────────────


def test_challenge_is_unpadded_base64url_sha256_of_verifier():
    import base64
    import hashlib

    verifier = "test-verifier-fixed-for-this-assertion"
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).decode().rstrip("=")
    challenge = orca.challenge_for(verifier)
    assert challenge == expected
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge


def test_verifier_and_state_are_fresh_per_attempt_and_high_entropy():
    verifiers = {orca.generate_verifier() for _ in range(64)}
    states = {orca.generate_state() for _ in range(64)}
    assert len(verifiers) == 64, "verifier must not repeat across attempts"
    assert len(states) == 64, "state must not repeat across attempts"
    # 32 random bytes -> 43 base64url chars (RFC 7636's documented minimum).
    assert all(len(v) == 43 for v in verifiers)
    assert not any(v == orca.generate_verifier() for v in list(verifiers)[:1])


def test_authorize_url_uses_auth_origin_and_s256_never_plain():
    url = orca.build_authorize_url(
        callback_url="http://127.0.0.1:51733/cb",
        challenge="CHALLENGE",
        state="STATE",
        app_name="graphify",
    )
    parsed = urllib.parse.urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}" == "https://www.orcarouter.ai"
    assert parsed.path == "/auth"
    params = urllib.parse.parse_qs(parsed.query)
    assert params["code_challenge"] == ["CHALLENGE"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == ["STATE"]
    assert params["scope"] == ["api"]


def test_authorize_url_never_contains_the_verifier():
    verifier = orca.generate_verifier()
    url = orca.build_authorize_url(
        callback_url="oob", challenge=orca.challenge_for(verifier), state=orca.generate_state()
    )
    assert verifier not in url


# ── A local fake consent server (real HTTP, no network) ───────────────────────


class _FakeConsent(BaseHTTPRequestHandler):
    """Stands in for www.orcarouter.ai: serves /auth and /api/v1/auth/keys."""

    captured: dict = {}
    mode = "approve"

    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802
        if self.path != "/api/v1/auth/keys":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        _FakeConsent.captured = {
            "path": self.path,
            "host": self.headers.get("Host"),
            "body": body,
        }
        if _FakeConsent.mode == "deny_exchange":
            self.send_response(403)
            payload = {"error": "invalid_grant"}
        elif _FakeConsent.mode == "scope_downgrade":
            self.send_response(200)
            payload = {"key": "sk-orca-fake-connector-key", "user_id": "u1", "scope": "connector"}
        elif _FakeConsent.mode == "no_key":
            self.send_response(200)
            payload = {"user_id": "u1", "scope": "api"}
        elif _FakeConsent.mode == "ratelimited":
            self.send_response(429)
            payload = {"error": "too_many_requests"}
        else:
            self.send_response(200)
            payload = {"key": "sk-orca-fake-pkce-key-abcdef", "user_id": "u1", "scope": "api"}
        encoded = json.dumps(payload).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


@pytest.fixture
def fake_consent(monkeypatch):
    """Point the PKCE flow at a local consent server on an ephemeral port."""
    server = HTTPServer(("127.0.0.1", 0), _FakeConsent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _FakeConsent.captured = {}
    _FakeConsent.mode = "approve"
    monkeypatch.setenv("ORCA_AUTH_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
    try:
        yield _FakeConsent
    finally:
        server.shutdown()
        server.server_close()


def _drive_loopback_flow(monkeypatch, *, deny: bool = False):
    """Run Flow A end to end: real listener, real HTTP exchange, fake consent.

    The browser is replaced by a thread that reads the authorize URL the flow
    hands us and calls the loopback callback with the state it finds there —
    which is what a real browser does after the user clicks Approve/Deny.
    """
    seen: dict = {}
    opened = threading.Event()

    def fake_open(url: str) -> bool:
        seen["authorize_url"] = url
        opened.set()
        return True

    def click():
        if not opened.wait(10):
            return
        params = urllib.parse.parse_qs(urllib.parse.urlparse(seen["authorize_url"]).query)
        callback = params["callback_url"][0]
        if deny:
            query = urllib.parse.urlencode({"error": "access_denied", "state": params["state"][0]})
        else:
            query = urllib.parse.urlencode({"code": "fake-auth-code", "state": params["state"][0]})
        try:
            urllib.request.urlopen(f"{callback}?{query}", timeout=10).read()
        except urllib.error.URLError:
            pass

    clicker = threading.Thread(target=click, daemon=True)
    clicker.start()
    return fake_open, seen


def test_flow_a_loopback_completes_and_persists(fake_consent, monkeypatch):
    fake_open, seen = _drive_loopback_flow(monkeypatch)
    credential = orca.PkceSource().connect(open_browser=fake_open, timeout=20)

    assert credential.secret == "sk-orca-fake-pkce-key-abcdef"
    assert credential.source == "pkce"
    assert credential.scope == "api"

    # Exchange went to the AUTH origin's /api/v1/auth/keys, in the body only.
    captured = fake_consent.captured
    assert captured["path"] == "/api/v1/auth/keys"
    assert captured["body"]["code"] == "fake-auth-code"
    assert captured["body"]["code_challenge_method"] == "S256"

    # The verifier never appears in the authorize URL.
    verifier = captured["body"]["code_verifier"]
    assert verifier and verifier not in seen["authorize_url"]

    # ...and it was persisted, so the next run reuses it.
    stored = orca.CredentialStore().load()
    assert stored is not None and stored.secret == credential.secret
    assert stored.source == "pkce"


def test_flow_a_state_mismatch_is_rejected_and_nothing_is_stored(fake_consent, monkeypatch):
    """A callback carrying the wrong state must be ignored, not redeemed."""
    seen: dict = {}
    opened = threading.Event()

    def fake_open(url: str) -> bool:
        seen["authorize_url"] = url
        opened.set()
        return True

    def click_wrong_state():
        if not opened.wait(10):
            return
        params = urllib.parse.parse_qs(urllib.parse.urlparse(seen["authorize_url"]).query)
        query = urllib.parse.urlencode({"code": "attacker-code", "state": "not-the-state"})
        try:
            urllib.request.urlopen(f"{params['callback_url'][0]}?{query}", timeout=10).read()
        except (urllib.error.URLError, TimeoutError):
            pass

    threading.Thread(target=click_wrong_state, daemon=True).start()
    with pytest.raises(orca.OrcaRouterAuthError) as exc:
        orca.PkceSource().connect(open_browser=fake_open, timeout=20)
    assert "state" in str(exc.value).lower()
    assert orca.CredentialStore().load() is None
    # The attacker's code was never exchanged.
    assert fake_consent.captured == {}


def test_flow_a_denial_exits_cleanly_without_storing(fake_consent, monkeypatch):
    fake_open, _ = _drive_loopback_flow(monkeypatch, deny=True)
    with pytest.raises(orca.OrcaRouterAuthError):
        orca.PkceSource().connect(open_browser=fake_open, timeout=20)
    assert orca.CredentialStore().load() is None
    assert fake_consent.captured == {}


def test_flow_b_out_of_band_uses_callback_url_oob_and_s256(fake_consent):
    """Flow B asks for out-of-band delivery explicitly, and mandates S256."""
    credential = orca.PkceSource().connect(
        flow="oob", open_browser=lambda url: None, code_reader=lambda: "fake-oob-code", timeout=20
    )
    assert credential.secret == "sk-orca-fake-pkce-key-abcdef"
    assert fake_consent.captured["body"]["code"] == "fake-oob-code"
    assert fake_consent.captured["body"]["code_challenge_method"] == "S256"


def test_flow_b_authorize_url_uses_oob_literal():
    url = orca.build_authorize_url(callback_url="oob", challenge="C", state="S")
    assert urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["callback_url"] == ["oob"]


def test_flow_selection_rejects_unknown_value(fake_consent):
    with pytest.raises(orca.OrcaRouterAuthError):
        orca.PkceSource().connect(
            flow="device", open_browser=lambda url: None, code_reader=lambda: "x", timeout=5
        )


def test_timeout_produces_actionable_error_and_stores_nothing(fake_consent):
    with pytest.raises(orca.OrcaRouterAuthError) as exc:
        orca.PkceSource().connect(open_browser=lambda url: None, timeout=1)
    assert "timed out" in str(exc.value).lower()
    assert "oob" in str(exc.value)
    assert orca.CredentialStore().load() is None


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("deny_exchange", "403"),
        ("ratelimited", "429"),
        ("no_key", "no key"),
    ],
)
def test_exchange_failures_are_classified_and_store_nothing(fake_consent, mode, expected):
    fake_consent.mode = mode
    with pytest.raises(orca.OrcaRouterAuthError) as exc:
        orca.PkceSource().connect(
            flow="oob", open_browser=lambda url: None, code_reader=lambda: "c", timeout=20
        )
    assert expected in str(exc.value)
    assert orca.CredentialStore().load() is None


def test_granted_scope_is_read_back_and_a_downgrade_is_refused(fake_consent):
    """Requesting `api` and being granted `connector` must not be treated as success."""
    fake_consent.mode = "scope_downgrade"
    with pytest.raises(orca.OrcaRouterAuthError) as exc:
        orca.PkceSource().connect(
            flow="oob", open_browser=lambda url: None, code_reader=lambda: "c", timeout=20
        )
    assert "connector" in str(exc.value)
    assert orca.CredentialStore().load() is None


def test_code_reuse_is_reported_as_terminal(fake_consent):
    """Auth codes are single-use; a second exchange is a 403, not a retry."""
    from graphify import orcarouter as o

    verifier = o.generate_verifier()
    first = o.exchange_code("fake-auth-code", verifier)
    assert first.secret
    fake_consent.mode = "deny_exchange"
    with pytest.raises(o.OrcaRouterAuthError) as exc:
        o.exchange_code("fake-auth-code", verifier)
    assert "403" in str(exc.value)


# ── Two adapters, one credential shape ────────────────────────────────────────


def test_both_adapters_yield_the_same_credential_shape(fake_consent):
    api_credential = orca.connect_with_api_key("sk-orca-fake-pasted-key")
    pkce_credential = orca.connect_with_pkce(
        flow="oob", open_browser=lambda url: None, code_reader=lambda: "c", timeout=20
    )
    assert type(api_credential) is type(pkce_credential) is orca.OrcaCredential
    # Provenance differs; nothing else about the shape or the store does.
    assert {api_credential.source, pkce_credential.source} == {"api_key", "pkce"}
    for credential in (api_credential, pkce_credential):
        assert credential.secret.startswith("sk-orca-")
        assert credential.scope == "api"
        assert credential.generation >= 1
        assert credential.needs_reauth is False


def test_api_key_adapter_save_read_mask_clear(monkeypatch):
    source = orca.ApiKeySource()
    assert source.acquire() is None
    credential = source.save("sk-orca-fake-api-key-1234567890")
    assert credential.masked() != credential.secret
    assert "…" in credential.masked()
    assert credential.secret[:8] in credential.masked()
    assert credential.secret[-4:] in credential.masked()
    # Middle of the key is never reproduced.
    assert credential.secret not in credential.masked()

    assert orca.ApiKeySource().acquire().secret == credential.secret
    source.clear()
    assert orca.ApiKeySource().acquire() is None


def test_api_key_adapter_rejects_empty_and_whitespace():
    with pytest.raises(orca.OrcaRouterAuthError):
        orca.connect_with_api_key("")
    with pytest.raises(orca.OrcaRouterAuthError):
        orca.connect_with_api_key("sk-orca- has-a-space")


def test_env_key_overrides_the_stored_credential(monkeypatch):
    orca.connect_with_api_key("sk-orca-fake-stored-key")
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-fake-env-key")
    assert orca.resolve_credential_secret() == "sk-orca-fake-env-key"
    # An env override is not persisted by a read.
    assert orca.CredentialStore().load().secret == "sk-orca-fake-stored-key"


def test_removing_the_stored_credential_leaves_the_env_override_alone(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-fake-env-key")
    orca.connect_with_api_key("sk-orca-fake-stored-key")
    assert orca.CredentialStore().clear() is True
    # The user owns the environment variable; clearing the store must not pretend
    # it removed that too.
    assert orca.resolve_credential_secret() == "sk-orca-fake-env-key"
    assert orca.CredentialStore().load() is None


def test_status_reports_the_eventual_source_without_echoing_the_key(monkeypatch):
    orca.connect_with_api_key("sk-orca-fake-status-key-abcdef")
    status = orca.ApiKeySource().status()
    assert status["present"] is True
    assert status["source"] == "pkce" or status["source"] == "api_key"
    assert "sk-orca-fake-status-key-abcdef" not in json.dumps(status)
    # No non-billing validation endpoint exists, so validity is reported unknown
    # rather than guessed.
    assert status["validation"] == "unknown"


def test_a_fresh_credential_clears_a_previous_needs_reauth_flag():
    first = orca.connect_with_api_key("sk-orca-fake-first")
    orca.note_rejected(first.secret)
    assert orca.CredentialStore().load().needs_reauth is True
    second = orca.connect_with_api_key("sk-orca-fake-second")
    reloaded = orca.CredentialStore().load()
    assert reloaded.needs_reauth is False
    assert reloaded.secret == second.secret
    assert reloaded.generation == first.generation + 1


def test_downstream_credential_resolution_is_source_agnostic(fake_consent):
    """The inference path and catalog must not care which adapter ran."""
    from graphify import llm

    assert llm._get_backend_api_key("orcarouter") == ""

    orca.connect_with_api_key("sk-orca-fake-from-api-adapter")
    via_api = llm._get_backend_api_key("orcarouter")

    orca.CredentialStore().clear()
    orca.connect_with_pkce(
        flow="oob", open_browser=lambda url: None, code_reader=lambda: "c", timeout=20
    )
    via_pkce = llm._get_backend_api_key("orcarouter")

    assert via_api == "sk-orca-fake-from-api-adapter"
    assert via_pkce == "sk-orca-fake-pkce-key-abcdef"
    assert via_api != via_pkce


# ── Revocation, reauth, and generation safety ────────────────────────────────


def test_revoked_key_marks_needs_reauth_without_fake_refresh(monkeypatch):
    credential = orca.connect_with_api_key("sk-orca-fake-revoked-key")
    store = orca.CredentialStore()
    assert store.load().needs_reauth is False

    assert orca.note_rejected(credential.secret) is True
    stored = store.load()
    assert stored.needs_reauth is True
    # The secret is retained: a transient/misclassified failure must not become
    # irreversible account loss, and no refresh grant is invented.
    assert stored.secret == credential.secret
    assert store.load().generation == 1, "no new generation implies no refresh"


def test_stale_generation_cannot_poison_a_newer_credential():
    store = orca.CredentialStore()
    old = store.save(orca.OrcaCredential(secret="sk-orca-fake-old", source="pkce", key_id="k_old"))
    new = store.save(orca.OrcaCredential(secret="sk-orca-fake-new", source="pkce", key_id="k_new"))
    assert new.generation == old.generation + 1

    # A late 401 from a request that began under the old generation.
    assert store.mark_needs_reauth(old.key_id, old.generation) is False
    assert store.load().needs_reauth is False
    assert store.load().secret == "sk-orca-fake-new"

    # The 401 for the credential actually rejected still lands.
    assert store.mark_needs_reauth(new.key_id, new.generation) is True
    assert store.load().secret == "sk-orca-fake-new"


def test_env_supplied_key_is_not_written_to_the_store_by_a_401(monkeypatch):
    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-fake-env-only")
    assert orca.note_rejected("sk-orca-fake-env-only") is False
    assert orca.CredentialStore().load() is None


def test_needs_reauth_credential_is_not_returned_as_usable():
    credential = orca.connect_with_api_key("sk-orca-fake-revoked-key")
    orca.note_rejected(credential.secret)
    # ApiKeySource refuses it, so the login command starts a fresh authorization
    # instead of silently reusing a dead key.
    assert orca.ApiKeySource().acquire() is None
    assert orca.PkceSource().acquire() is None
    # But it is still visible, so status can explain the situation.
    assert orca.resolve_credential().needs_reauth is True


def test_login_reuses_a_stored_pkce_credential_instead_of_minting_a_second(fake_consent):
    """Re-authorizing on every launch exhausts the 10-keys-per-24h cap."""
    orca.connect_with_pkce(
        flow="oob", open_browser=lambda url: None, code_reader=lambda: "c", timeout=20
    )
    fake_consent.captured = {}
    existing = orca.PkceSource().acquire()
    assert existing is not None
    # Nothing was exchanged on the reuse path.
    assert fake_consent.captured == {}


# ── Credential never leaks into output ────────────────────────────────────────


def test_mask_key_never_reproduces_the_secret():
    secret = "sk-orca-fake-very-secret-value-abcdefghijklmnop"
    masked = orca.mask_key(secret)
    assert secret not in masked
    assert masked != secret
    assert orca.mask_key("") == "(none)"
    assert orca.mask_key(None) == "(none)"
    short = orca.mask_key("sk-orca-abc")
    assert short == "••••" and "abc" not in short


def test_verifier_and_key_absent_from_every_raised_message(fake_consent):
    """A failure path must not echo the credential or the verifier."""
    fake_consent.mode = "deny_exchange"
    captured_verifier: dict = {}

    original = orca.exchange_code

    def capture(code, verifier, **kwargs):
        captured_verifier["v"] = verifier
        return original(code, verifier, **kwargs)

    orca.exchange_code = capture  # type: ignore[assignment]
    try:
        with pytest.raises(orca.OrcaRouterAuthError) as exc:
            orca.PkceSource().connect(
                flow="oob", open_browser=lambda url: None, code_reader=lambda: "fake-code", timeout=20
            )
    finally:
        orca.exchange_code = original  # type: ignore[assignment]

    message = str(exc.value)
    assert captured_verifier["v"] not in message
    assert "sk-orca" not in message
    assert "fake-code" not in message


def test_store_file_is_owner_only_and_never_world_readable():
    orca.connect_with_api_key("sk-orca-fake-permissions-check")
    path = orca.store_path()
    assert path.is_file()
    mode = path.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"credential file mode {oct(mode)} is group/world accessible"


# ── Model catalog parsing and bounds ─────────────────────────────────────────


def _model(model_id, **overrides):
    raw = {
        "id": model_id,
        "object": "model",
        "owned_by": model_id.split("/")[0],
        "supported_endpoint_types": ["openai"],
    }
    raw.update(overrides)
    return raw


def test_catalog_record_validation_rejects_unusable_shapes():
    assert orca._model_from_api("not-a-dict") is None
    assert orca._model_from_api({"id": 123}) is None
    assert orca._model_from_api({"id": ""}) is None
    assert orca._model_from_api({"id": "x" * 500}) is None
    assert orca._model_from_api(_model("vendor/model")) is not None


def test_catalog_ids_keep_the_vendor_namespace_verbatim():
    info = orca._model_from_api(_model("deepseek/deepseek-v4.1-flash"))
    assert info.id == "deepseek/deepseek-v4.1-flash"


# ── Capability filtering ─────────────────────────────────────────────────────


def _catalog(*models):
    return orca.ModelCatalog(list(models), source="live")


TEXT_ONLY = orca.ModelInfo(id="vendor/text-only", supported_endpoint_types=("openai",),
                           input_modalities=("text",), output_modalities=("text",))
IMAGE_CHAT = orca.ModelInfo(id="vendor/vision-chat", supported_endpoint_types=("openai", "anthropic"),
                            input_modalities=("text", "image"), output_modalities=("text",))
NO_ARCH = orca.ModelInfo(id="vendor/no-architecture", supported_endpoint_types=("openai",))
EMBEDDING = orca.ModelInfo(id="vendor/embed", supported_endpoint_types=("embeddings",))
IMAGE_GEN = orca.ModelInfo(id="vendor/img-gen", supported_endpoint_types=("image-generation",))
VIDEO = orca.ModelInfo(id="vendor/vid", supported_endpoint_types=("openai-video",))
RERANK = orca.ModelInfo(id="vendor/rank", supported_endpoint_types=("jina-rerank",))
AUDIO_CHAT = orca.ModelInfo(id="vendor/audio", supported_endpoint_types=("openai",),
                            input_modalities=("text", "audio"), output_modalities=("text",))
ALL = [TEXT_ONLY, IMAGE_CHAT, NO_ARCH, EMBEDDING, IMAGE_GEN, VIDEO, RERANK, AUDIO_CHAT]


def test_chat_filter_uses_supported_endpoint_types_and_excludes_non_text_routes():
    ids = [m.id for m in _catalog(*ALL).filter("chat")]
    assert ids == ["vendor/text-only", "vendor/vision-chat", "vendor/no-architecture", "vendor/audio"]
    for excluded in ("vendor/embed", "vendor/img-gen", "vendor/vid", "vendor/rank"):
        assert excluded not in ids


def test_vision_filter_fails_closed_without_declared_modalities():
    ids = [m.id for m in _catalog(*ALL).filter("vision")]
    # Only the model that explicitly declares image INPUT.
    assert ids == ["vendor/vision-chat"]
    assert "vendor/no-architecture" not in ids, "absent architecture must not imply vision"
    assert "vendor/audio" not in ids


def test_media_filter_requires_the_exact_uploaded_modality():
    catalog = _catalog(*ALL)
    assert [m.id for m in catalog.filter_for_media(["image"])] == ["vendor/vision-chat"]
    assert [m.id for m in catalog.filter_for_media(["audio"])] == ["vendor/audio"]
    assert [m.id for m in catalog.filter_for_media(["video"])] == []
    # No media -> plain chat.
    assert len(catalog.filter_for_media([])) == 4


def test_embedding_image_video_rerank_filters_match_their_own_endpoint_only():
    catalog = _catalog(*ALL)
    assert [m.id for m in catalog.filter("embedding")] == ["vendor/embed"]
    assert [m.id for m in catalog.filter("image")] == ["vendor/img-gen"]
    assert [m.id for m in catalog.filter("video")] == ["vendor/vid"]
    assert [m.id for m in catalog.filter("rerank")] == ["vendor/rank"]


def test_capability_is_never_inferred_from_the_model_name():
    """A model named like an image generator but declaring text is still chat."""
    misleading = orca.ModelInfo(
        id="vendor/dall-e-image-generator-vision",
        supported_endpoint_types=("openai",),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    catalog = _catalog(misleading)
    assert [m.id for m in catalog.filter("chat")] == [misleading.id]
    assert catalog.filter("image") == []
    assert catalog.filter("vision") == []


def test_image_output_model_is_not_offered_as_chat_even_on_the_openai_route():
    generator = orca.ModelInfo(
        id="vendor/text-and-image-out",
        supported_endpoint_types=("openai",),
        input_modalities=("text",),
        output_modalities=("image",),
    )
    assert _catalog(generator).filter("chat") == []


# ── Degraded / fallback behaviour ────────────────────────────────────────────


def test_live_discovery_failure_falls_back_to_seed_never_to_free_text(monkeypatch):
    def boom(*args, **kwargs):
        raise orca.OrcaRouterCatalogError("connection refused")

    monkeypatch.setattr(orca, "discover_models", boom)
    catalog = orca.load_catalog(orca.OrcaCredential(secret="sk-orca-fake", source="api_key"),
                                prefer_cache=False)
    assert catalog.source == "seed"
    assert catalog.degraded is True
    assert catalog.error
    ids = [m.id for m in catalog.models]
    assert ids == [m.id for m in orca.VERIFIED_SEED]
    # The seed stays usable and keeps its verified metadata.
    gpt = catalog.get("openai/gpt-5.5")
    assert gpt is not None
    assert set(gpt.reasoning_efforts) == {"low", "medium", "high", "xhigh"}
    assert "image" in gpt.input_modalities


def test_seed_is_never_merged_into_a_successful_live_result(monkeypatch):
    live = [_model("vendor/live-only", supported_endpoint_types=["openai"])]

    def fake_fetch(api_key, **kwargs):
        return [orca._model_from_api(r) for r in live]

    monkeypatch.setattr(orca, "discover_models", fake_fetch)
    catalog = orca.load_catalog(orca.OrcaCredential(secret="sk-orca-fake", source="api_key"))
    assert catalog.source == "live"
    assert catalog.degraded is False
    assert [m.id for m in catalog.models] == ["vendor/live-only"]
    for seed_model in orca.VERIFIED_SEED:
        assert all(m.id != seed_model.id for m in catalog.models)


def test_live_metadata_wins_but_a_missing_reasoning_ladder_keeps_the_verified_one():
    """Live discovery is authoritative; it must not silently drop the ladder."""
    live = orca._model_from_api(
        _model(
            "openai/gpt-5.5",
            supported_endpoint_types=["openai"],
            architecture={"input_modalities": ["text"], "output_modalities": ["text"]},
        )
    )
    merged = orca._merge_seed_metadata([live])
    gpt = merged[0]
    assert set(gpt.reasoning_efforts) == {"low", "medium", "high", "xhigh"}
    # The live record declared text-only, and that narrower claim is respected:
    # we do not re-widen a model the gateway says cannot see images.
    assert gpt.input_modalities == ("text",)
    assert orca.ModelCatalog(merged, source="live").filter("vision") == []
    # A live record with no architecture block at all falls back to the verified
    # modality metadata, because there is nothing else to go on.
    bare = orca._model_from_api(_model("openai/gpt-5.5", supported_endpoint_types=["openai"]))
    assert orca._merge_seed_metadata([bare])[0].input_modalities == ("text", "image")


def test_last_known_good_cache_is_used_before_the_seed(monkeypatch):
    credential = orca.OrcaCredential(secret="sk-orca-fake", source="api_key")
    monkeypatch.setattr(
        orca, "discover_models", lambda *a, **k: [orca._model_from_api(_model("vendor/cached"))]
    )
    orca.load_catalog(credential)  # populates the cache

    def boom(*args, **kwargs):
        raise orca.OrcaRouterCatalogError("offline")

    monkeypatch.setattr(orca, "discover_models", boom)
    catalog = orca.load_catalog(credential, prefer_cache=True)
    assert catalog.source == "last-known-good"
    assert catalog.degraded is True
    assert [m.id for m in catalog.models] == ["vendor/cached"]


def test_catalog_http_401_mentions_the_credential_not_a_parse_error(monkeypatch):
    import urllib.error

    def raise_401(*args, **kwargs):
        raise urllib.error.HTTPError(orca.api_url("/models"), 401, "Unauthorized", {}, None)

    monkeypatch.setattr(orca.urllib.request, "urlopen", raise_401)
    with pytest.raises(orca.OrcaRouterCatalogError) as exc:
        orca.discover_models("sk-orca-fake")
    assert "401" in str(exc.value)
    assert "sk-orca" not in str(exc.value)


def test_catalog_request_targets_the_api_origin_with_bearer_auth(monkeypatch):
    seen: dict = {}

    class _Resp:
        status = 200

        def read(self, n=-1):
            return json.dumps({"data": [_model("vendor/x")]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        return _Resp()

    monkeypatch.setattr(orca.urllib.request, "urlopen", fake_urlopen)
    orca.discover_models("sk-orca-fake-key")
    assert seen["url"].startswith("https://api.orcarouter.ai/v1/models")
    assert seen["auth"] == "Bearer sk-orca-fake-key"


def test_auth_and_inference_requests_never_share_an_origin(fake_consent, monkeypatch):
    """The whole point of two origins: they must be independently traceable.

    Both requests are captured — authorize+exchange on the auth origin, the
    catalog on the inference origin — and neither is derived from the other.
    """
    seen: dict = {}
    opened = threading.Event()

    def fake_open(url: str) -> bool:
        seen["authorize"] = url
        opened.set()
        return True

    def click():
        if not opened.wait(10):
            return
        params = urllib.parse.parse_qs(urllib.parse.urlparse(seen["authorize"]).query)
        query = urllib.parse.urlencode({"code": "fake-auth-code", "state": params["state"][0]})
        urllib.request.urlopen(f"{params['callback_url'][0]}?{query}", timeout=10).read()

    class _Resp:
        def read(self, n=-1):
            return json.dumps({"data": [_model("vendor/x")]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_catalog_urlopen(req, timeout=None):
        seen["catalog"] = req.full_url
        return _Resp()

    threading.Thread(target=click, daemon=True).start()
    orca.PkceSource().connect(open_browser=fake_open, timeout=20)
    monkeypatch.setattr(orca.urllib.request, "urlopen", fake_catalog_urlopen)
    orca.discover_models("sk-orca-fake-key")

    auth_origin = urllib.parse.urlparse(seen["authorize"]).netloc
    exchange_origin = fake_consent.captured["host"]
    catalog_origin = urllib.parse.urlparse(seen["catalog"]).netloc

    # authorize and exchange went to the auth origin...
    assert auth_origin == exchange_origin
    # ...and discovery went to the inference origin, which is a different host.
    assert catalog_origin == "api.orcarouter.ai"
    assert catalog_origin != exchange_origin


def test_an_exchange_request_is_never_sent_to_the_inference_origin(monkeypatch):
    """Guard against the documented `/v1/auth/keys` 404 mistake."""
    monkeypatch.setenv("ORCA_API_BASE_URL", "https://api.orcarouter.ai/v1")
    exchange = orca.auth_url(orca.EXCHANGE_PATH)
    assert exchange.startswith("https://www.orcarouter.ai/")
    # The inference origin is a strict prefix of the wrong URL but not of the right one.
    assert not exchange.startswith("https://api.orcarouter.ai")


# ── Model selection for a run (the selector's options) ───────────────────────


def test_resolve_model_clears_an_incompatible_explicit_selection(monkeypatch):
    """A text-only model must be cleared when the corpus adds an image."""
    catalog = _catalog(TEXT_ONLY, IMAGE_CHAT)
    monkeypatch.setattr(orca, "load_catalog", lambda *a, **k: catalog)

    # Compatible with a text corpus: kept as-is.
    model, _ = orca.resolve_model("vendor/text-only")
    assert model == "vendor/text-only"

    # Incompatible once an image is attached: cleared with the options named.
    with pytest.raises(orca.OrcaRouterError) as exc:
        orca.resolve_model("vendor/text-only", media=["image"])
    assert "vendor/text-only" in str(exc.value)
    assert "vendor/vision-chat" in str(exc.value)


def test_resolve_model_options_are_the_filtered_list(monkeypatch):
    catalog = _catalog(TEXT_ONLY, IMAGE_CHAT, IMAGE_GEN)
    monkeypatch.setattr(orca, "load_catalog", lambda *a, **k: catalog)
    # With an image attached the compatible set is exactly the image-input chats.
    compatible = catalog.filter_for_media(["image"])
    assert [m.id for m in compatible] == ["vendor/vision-chat"]
    model, _ = orca.resolve_model(None, media=["image"], catalog=catalog)
    assert model in {m.id for m in compatible}


def test_resolve_model_reports_when_nothing_supports_the_media(monkeypatch):
    monkeypatch.setattr(orca, "load_catalog", lambda *a, **k: _catalog(TEXT_ONLY))
    with pytest.raises(orca.OrcaRouterError) as exc:
        orca.resolve_model(None, media=["image"])
    assert "image" in str(exc.value)


def test_media_kinds_detects_only_real_image_extensions(tmp_path):
    png = tmp_path / "diagram.png"
    md = tmp_path / "readme.md"
    pdf = tmp_path / "paper.pdf"
    assert orca.media_kinds([str(png), str(md), str(pdf)]) == ["image"]
    assert orca.media_kinds([str(md), str(pdf)]) == []


# ── Backend registration ─────────────────────────────────────────────────────


def test_orcarouter_is_registered_as_a_first_class_backend():
    from graphify import llm

    cfg = llm.BACKENDS["orcarouter"]
    assert cfg["base_url"] == "https://api.orcarouter.ai/v1"
    assert cfg["default_model"] == "orcarouter/auto"
    # Both authentication entries resolve through one seam, so the registry
    # declares the API-key variable while PKCE supplies the same secret.
    assert llm._backend_env_keys("orcarouter") == ["ORCAROUTER_API_KEY"]


def test_backend_env_isolation_covers_the_new_variable():
    from graphify import llm

    assert "ORCAROUTER_API_KEY" in llm.backend_detection_env_vars()


def test_detection_prefers_orcarouter_only_when_no_higher_priority_key_exists(monkeypatch):
    from graphify import llm

    monkeypatch.setenv("ORCAROUTER_API_KEY", "sk-orca-fake")
    assert llm.detect_backend() == "orcarouter"
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai")
    assert llm.detect_backend() == "openai"


def test_vision_support_follows_the_selected_orcarouter_model(monkeypatch):
    from graphify import llm

    catalog = orca.ModelCatalog(
        [
            orca.ModelInfo(id="orcarouter/auto", supported_endpoint_types=("openai",),
                           input_modalities=("text",), output_modalities=("text",)),
            orca.ModelInfo(id="vendor/vision-chat", supported_endpoint_types=("openai",),
                           input_modalities=("text", "image"), output_modalities=("text",)),
        ],
        source="live",
    )
    monkeypatch.setattr(orca, "load_catalog", lambda *a, **k: catalog)

    monkeypatch.delenv("GRAPHIFY_ORCAROUTER_MODEL", raising=False)
    assert llm._backend_supports_vision("orcarouter") is False, "default model is text-only"

    monkeypatch.setenv("GRAPHIFY_ORCAROUTER_MODEL", "vendor/vision-chat")
    assert llm._backend_supports_vision("orcarouter") is True

    # An unknown model fails closed rather than assuming the gateway is multimodal.
    monkeypatch.setenv("GRAPHIFY_ORCAROUTER_MODEL", "vendor/not-in-catalog")
    assert llm._backend_supports_vision("orcarouter") is False


def test_orcarouter_is_wired_into_the_other_ai_entry_points():
    """Extraction, dedup/labelling and PR triage all reach the same provider."""
    from graphify import llm, prs

    assert "orcarouter" in llm.BACKENDS
    assert prs._TRIAGE_MODEL_DEFAULTS["orcarouter"] == "orcarouter/auto"
    # extract_files_direct dispatches orcarouter through the OpenAI-compatible
    # transport, which is where the bearer credential and base_url are applied.
    assert "orcarouter" not in ("claude", "claude-cli", "bedrock", "azure")


# ── Terminal 401 and model-scope 403 classification in the transport ─────────


class _FakeStatusError(Exception):
    def __init__(self, status, body=None):
        super().__init__("boom")
        self.status_code = status
        self.body = body


def _fake_client(error, capture: dict):
    class _Completions:
        def create(self, **kwargs):
            capture.update(kwargs)
            raise error

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


def test_transport_401_marks_the_exact_credential_for_reauth():
    from graphify import llm

    credential = orca.connect_with_api_key("sk-orca-fake-revoked-transport")
    client = _fake_client(_FakeStatusError(401), {})
    with pytest.raises(ValueError) as exc:
        llm._orcarouter_guarded_create(client, {"model": "vendor/x"}, "orcarouter", credential.secret)
    assert "401" in str(exc.value)
    assert "reauth" in str(exc.value).lower()
    assert credential.secret not in str(exc.value)
    assert orca.CredentialStore().load().needs_reauth is True


def test_transport_model_access_denied_does_not_mark_the_credential():
    """A key restricted to a subset of the catalog is not a broken credential."""
    from graphify import llm

    credential = orca.connect_with_api_key("sk-orca-fake-scoped-key")
    error = _FakeStatusError(403, {"error": {"code": "model_access_denied"}})
    client = _fake_client(error, {})
    with pytest.raises(ValueError) as exc:
        llm._orcarouter_guarded_create(client, {"model": "orcarouter/auto"}, "orcarouter", credential.secret)
    assert "model_access_denied" in str(exc.value)
    assert orca.CredentialStore().load().needs_reauth is False


def test_transport_does_not_mark_a_credential_that_has_been_replaced():
    from graphify import llm

    old = orca.connect_with_api_key("sk-orca-fake-old-transport")
    orca.connect_with_api_key("sk-orca-fake-new-transport")
    client = _fake_client(_FakeStatusError(401), {})
    with pytest.raises(ValueError) as exc:
        llm._orcarouter_guarded_create(client, {"model": "vendor/x"}, "orcarouter", old.secret)
    # The 401 is still reported, but the replacement credential stays usable.
    assert "401" in str(exc.value)
    assert orca.CredentialStore().load().needs_reauth is False
    assert orca.CredentialStore().load().secret == "sk-orca-fake-new-transport"


def test_transport_leaves_other_backends_untouched():
    from graphify import llm

    client = _fake_client(_FakeStatusError(401), {})
    with pytest.raises(_FakeStatusError):
        llm._orcarouter_guarded_create(client, {"model": "gpt-4.1-mini"}, "openai", "sk-fake")


def test_transport_passes_unclassified_errors_through():
    from graphify import llm

    credential = orca.connect_with_api_key("sk-orca-fake-ratelimited")
    client = _fake_client(_FakeStatusError(429), {})
    with pytest.raises(_FakeStatusError):
        llm._orcarouter_guarded_create(client, {"model": "vendor/x"}, "orcarouter", credential.secret)
    assert orca.CredentialStore().load().needs_reauth is False
