"""OrcaRouter provider: credentials, PKCE login, and the live model catalog.

OrcaRouter is an OpenAI-compatible AI gateway. Inference lives on
``https://api.orcarouter.ai/v1``; authentication lives on
``https://www.orcarouter.ai``. Those are two different origins and neither is
derived from the other — ``https://api.orcarouter.ai/v1/auth/keys`` is a 404.

This module owns three things and nothing else:

1. **The credential seam.** ``CredentialSource`` is the small interface
   ``graphify`` asks for a secret; :class:`ApiKeySource` (a pasted
   ``sk-orca-…`` key, from the env var or ``graphify orcarouter key set``) and
   :class:`PkceSource` (OAuth 2.0 + PKCE) are two adapters over it. Both hand
   back the same :class:`OrcaCredential` and both persist through the same
   store, so the provider adapter, the catalog and every AI entry point read a
   credential without ever asking where it came from.

2. **The PKCE flow.** Flow A (loopback redirect) is the default because
   graphify is self-hosted software running on the user's own machine, where a
   ``127.0.0.1`` listener is always reachable. Flow B (out-of-band code) is the
   fallback for headless/SSH/container runs and for users who pick "Show me a
   code" on the consent screen. Both always send ``S256``.

3. **Model discovery.** The live ``GET /v1/models`` catalog is authoritative;
   :data:`VERIFIED_SEED` is a small, sourced cold-start fallback that is only
   ever used when discovery fails, and is never merged into a successful live
   result.

The returned key is a durable, user-owned OrcaRouter API key — not a refresh
token. There is no refresh grant; a revoked key requires reauthentication
(:meth:`CredentialStore.mark_needs_reauth`).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

__all__ = [
    "DEFAULT_AUTH_BASE",
    "DEFAULT_API_BASE",
    "KEY_DASHBOARD_URL",
    "APP_NAME",
    "OrcaCredential",
    "OrcaRouterError",
    "OrcaRouterAuthError",
    "OrcaRouterCatalogError",
    "CredentialStore",
    "ApiKeySource",
    "PkceSource",
    "resolve_credential",
    "resolve_credential_secret",
    "note_rejected",
    "connect_with_api_key",
    "connect_with_pkce",
    "generate_verifier",
    "generate_state",
    "challenge_for",
    "build_authorize_url",
    "exchange_code",
    "discover_models",
    "load_catalog",
    "models_for_capability",
    "ModelInfo",
    "ModelCatalog",
    "mask_key",
    "auth_base",
    "api_base",
    "store_path",
    "VERIFIED_SEED",
    "CAPABILITIES",
]

# ── Origins ───────────────────────────────────────────────────────────────────
# Two public origins, each overridable. ORCA_BASE_URL is the documented shared
# self-hosted fallback; the explicit per-origin overrides take precedence over
# it. Never derive one origin from the other — see the module docstring.

DEFAULT_AUTH_BASE = "https://www.orcarouter.ai"
DEFAULT_API_BASE = "https://api.orcarouter.ai/v1"

AUTHORIZE_PATH = "/auth"
EXCHANGE_PATH = "/api/v1/auth/keys"
# Documented for completeness; graphify does not implement the device grant.
# See the "Flows not implemented" note in the PR body.
DEVICE_CODE_PATH = "/api/v1/auth/device/code"
DEVICE_TOKEN_PATH = "/api/v1/auth/device/token"

APP_NAME = "graphify"
KEY_DASHBOARD_URL = "https://www.orcarouter.ai/console/authorized-apps"
KEY_PREFIX = "sk-orca-"

# The relay speaks the OpenAI wire format; `graphify` drives it through the
# `openai` SDK, so only these endpoint types are usable here.
TEXT_ENDPOINT_TYPES = ("openai", "openai-response", "anthropic", "gemini")
# Routes a text-extraction client cannot speak. A model advertising ONLY these
# is not a chat model, however chatty its name looks.
NON_TEXT_ENDPOINT_TYPES = ("image-generation", "openai-video", "jina-rerank", "embeddings")

_BOUNDED_ENDPOINT_TYPES = frozenset(TEXT_ENDPOINT_TYPES) | frozenset(NON_TEXT_ENDPOINT_TYPES)

# Discovery bounds. The catalog drives a menu, so a hostile or broken response
# must not be able to exhaust memory or advertise a route we cannot speak.
CATALOG_TIMEOUT_S = 15.0
CATALOG_MAX_BYTES = 8 * 1024 * 1024
CATALOG_MAX_ITEMS = 2000
CATALOG_MAX_ID_LEN = 200
# Height of the "authorize" wait. The auth code itself is single-use with a
# 10 minute TTL; this only bounds how long we hold a loopback listener open.
DEFAULT_OAUTH_TIMEOUT_S = 300.0
# PKCE verifier entropy. RFC 7636 requires 43..128 chars of the unreserved set;
# 32 random bytes -> 43 base64url chars, the documented minimum.
_PKCE_BYTES = 32
_STATE_BYTES = 16

CAPABILITIES = ("chat", "vision", "embedding", "image", "video", "rerank")


class OrcaRouterError(Exception):
    """Base class for OrcaRouter provider errors."""


class OrcaRouterAuthError(OrcaRouterError):
    """A credential could not be obtained, or was rejected by the gateway."""


class OrcaRouterCatalogError(OrcaRouterError):
    """The live model catalog could not be read or parsed."""


def mask_key(secret: str | None) -> str:
    """Redact a credential for display. Never returns more than a short prefix.

    Used by every user-facing status line so a key can be confirmed without
    being reproduced. There is no inverse: the caller keeps the only copy.
    """
    if not secret:
        return "(none)"
    if len(secret) <= 12:
        return "••••"
    return f"{secret[:8]}…{secret[-4:]}"


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _is_loopback_host(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    return host in ("localhost", "127.0.0.1", "::1") or host.startswith("127.")


def _validate_origin(url: str, *, what: str) -> str:
    """Reject a remote plaintext origin; permit http only for loopback.

    Mirrors ``provider_base_url_ok``'s stance: a self-hosted OrcaRouter gateway
    may legitimately live on a private address, so this checks the scheme, not
    the IP.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise OrcaRouterError(
            f"{what} base URL {url!r} must be http or https (got {parsed.scheme!r})."
        )
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname or ""):
        raise OrcaRouterError(
            f"{what} base URL {url!r} is plaintext http to a non-loopback host. "
            "Use https (http is accepted only for 127.0.0.1/[::1]/localhost)."
        )
    return url.rstrip("/")


def _shared_base() -> str:
    return _first_env("ORCA_BASE_URL")


def auth_base() -> str:
    """The authentication origin. Explicit override, then shared, then default.

    Never derived from :func:`api_base` by swapping a hostname.
    """
    explicit = _first_env("ORCA_AUTH_BASE_URL")
    if explicit:
        return _validate_origin(explicit, what="auth")
    shared = _shared_base()
    if shared:
        return _validate_origin(shared, what="auth")
    return DEFAULT_AUTH_BASE


def api_base() -> str:
    """The inference + model-discovery base, always ending in ``/v1``.

    Explicit override, then shared (with ``/v1`` appended if the shared base is
    a bare origin), then the public default.
    """
    explicit = _first_env("ORCA_API_BASE_URL")
    if explicit:
        return _validate_origin(explicit, what="inference")
    shared = _shared_base()
    if shared:
        shared = _validate_origin(shared, what="inference")
        # A shared self-hosted base names one origin for both roles; the relay
        # path always lives under /v1. This is not hostname derivation — it is
        # the same origin the user configured.
        return shared if shared.endswith("/v1") else f"{shared}/v1"
    return DEFAULT_API_BASE


def auth_url(path: str) -> str:
    """Join ``path`` onto the auth origin. ``path`` must start with ``/``."""
    return f"{auth_base()}{path}"


def api_url(path: str) -> str:
    """Join ``path`` onto the inference base (which already ends in ``/v1``)."""
    return f"{api_base()}{path}"


# ── Credential interface ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrcaCredential:
    """One OrcaRouter credential, however it was obtained.

    ``source`` is provenance for status output only. Nothing downstream may
    branch on it: the inference adapter, the catalog and every AI entry point
    take this object and use ``secret``.
    """

    secret: str
    source: str  # "api_key" | "pkce"
    key_id: str = ""
    generation: int = 1
    scope: str = "api"
    user_id: str = ""
    created_at: float = 0.0
    needs_reauth: bool = False

    def masked(self) -> str:
        return mask_key(self.secret)


class CredentialSource(Protocol):
    """The seam. Two adapters implement it; callers never know which one ran."""

    name: str

    def acquire(self) -> OrcaCredential | None:
        """Return a usable credential without any user interaction, or None."""

    def clear(self) -> None:
        """Remove the credential this source owns."""


def store_path() -> Path:
    """Where the OrcaRouter credential lives.

    ``~/.graphify/`` is already this project's trust anchor for persisted
    provider config (see ``_custom_providers_path``); reusing it means no new
    secret store is introduced. The file is written 0600.
    """
    override = os.environ.get("ORCAROUTER_CREDENTIALS_PATH", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".graphify" / "orcarouter.json"


class CredentialStore:
    """The one persisted record backing both adapters.

    A single active credential keeps precedence unambiguous: an explicit
    ``ORCAROUTER_API_KEY`` in the environment always wins (it is a deliberate
    per-invocation override), otherwise the stored record is used whether it
    came from ``key set`` or from a PKCE login.

    The store never holds anything but a normal OrcaRouter API key. No refresh
    token is invented, and the old secret is never deleted before a successful
    replacement — that would turn a transient failure into irreversible account
    loss.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else store_path()

    # -- raw IO ------------------------------------------------------------

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        from graphify.paths import write_text_atomic

        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(self.path, json.dumps(data, indent=2) + "\n")
        # write_text_atomic matches the destination's existing mode for atomic
        # replaces, which for a brand-new file is the umask default (0644 under
        # a typical umask). This file holds a live API key, so tighten it.
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # -- public API --------------------------------------------------------

    def load(self) -> OrcaCredential | None:
        rec = self._read().get("credential")
        if not isinstance(rec, dict):
            return None
        secret = rec.get("secret")
        if not isinstance(secret, str) or not secret:
            return None
        return OrcaCredential(
            secret=secret,
            source=str(rec.get("source") or "api_key"),
            key_id=str(rec.get("key_id") or ""),
            generation=int(rec.get("generation") or 1),
            scope=str(rec.get("scope") or "api"),
            user_id=str(rec.get("user_id") or ""),
            created_at=float(rec.get("created_at") or 0.0),
            needs_reauth=bool(rec.get("needs_reauth")),
        )

    def save(self, credential: OrcaCredential) -> OrcaCredential:
        """Persist ``credential``, incrementing its generation.

        A new generation is what makes the 401 path safe: a request that began
        under generation N can only ever mark generation N as broken.
        """
        previous = self.load()
        generation = (previous.generation + 1) if previous else 1
        stored = replace(credential, generation=generation, created_at=time.time(), needs_reauth=False)
        self._write(
            {
                "credential": {
                    "secret": stored.secret,
                    "source": stored.source,
                    "key_id": stored.key_id,
                    "generation": stored.generation,
                    "scope": stored.scope,
                    "user_id": stored.user_id,
                    "created_at": stored.created_at,
                    "needs_reauth": False,
                }
            }
        )
        return stored

    def clear(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        except OSError:
            return False
        return True

    def mark_needs_reauth(self, key_id: str, generation: int) -> bool:
        """Flag exactly one credential generation as requiring re-login.

        Returns True only when the stored record matches BOTH the key id and the
        generation that made the rejected request. A late 401 from a request
        that started before a re-login therefore cannot poison the fresh
        credential.
        """
        current = self.load()
        if current is None:
            return False
        if current.needs_reauth:
            return False
        if key_id and current.key_id and current.key_id != key_id:
            return False
        if current.generation != generation:
            return False
        self._write(
            {
                "credential": {
                    "secret": current.secret,
                    "source": current.source,
                    "key_id": current.key_id,
                    "generation": current.generation,
                    "scope": current.scope,
                    "user_id": current.user_id,
                    "created_at": current.created_at,
                    "needs_reauth": True,
                }
            }
        )
        return True


def _key_id_for(secret: str) -> str:
    """A stable, non-reversible label for a key, safe to store and print.

    Derived by hashing the secret so the id can be compared across runs without
    the plaintext ever being needed for identity.
    """
    return "k_" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


# ── Adapter 1: an existing API key ────────────────────────────────────────────


class ApiKeySource:
    """The paste-an-existing-key adapter (env var, or the persisted store).

    Only a lightweight shape check is applied. An ``sk-orca-`` prefix is not
    proof that a credential is valid and there is no free validation endpoint,
    so validity is established by the first real request rather than by a paid
    probe (documented as "validation: unknown" in the CLI status output).
    """

    name = "api_key"

    def __init__(self, store: CredentialStore | None = None) -> None:
        self.store = store or CredentialStore()

    def from_env(self) -> OrcaCredential | None:
        secret = _first_env("ORCAROUTER_API_KEY")
        if not secret:
            return None
        return OrcaCredential(secret=secret, source=self.name, key_id=_key_id_for(secret))

    def acquire(self) -> OrcaCredential | None:
        env = self.from_env()
        if env is not None:
            return env
        stored = self.store.load()
        if stored is None or stored.needs_reauth:
            return None
        return stored

    def clear(self) -> None:
        self.store.clear()

    def save(self, secret: str) -> OrcaCredential:
        """Persist a pasted key. Replaces any previous credential."""
        secret = (secret or "").strip()
        if not secret:
            raise OrcaRouterAuthError("Refusing to store an empty OrcaRouter API key.")
        if any(ch.isspace() for ch in secret):
            raise OrcaRouterAuthError(
                "That does not look like an OrcaRouter API key (it contains whitespace)."
            )
        return self.store.save(
            OrcaCredential(secret=secret, source=self.name, key_id=_key_id_for(secret))
        )

    def status(self) -> dict:
        env = self.from_env()
        stored = self.store.load()
        active = env or stored
        return {
            "source": "env:ORCAROUTER_API_KEY" if env else (stored.source if stored else "none"),
            "present": bool(active),
            "masked": mask_key(active.secret) if active else "(none)",
            "key_id": (active.key_id if active else ""),
            "generation": (active.generation if active else 0),
            "scope": (active.scope if active else ""),
            "needs_reauth": bool(stored.needs_reauth) if stored else False,
            "store": str(self.store.path),
            # There is no documented non-billing validation endpoint, so any
            # claim of "valid" here would be a guess.
            "validation": "unknown",
        }


# ── Adapter 2: OAuth 2.0 + PKCE ───────────────────────────────────────────────

OAUTH_FLOWS = ("loopback", "oob")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_verifier() -> str:
    """A fresh, high-entropy PKCE verifier from the OS CSPRNG.

    Generated per attempt and never derived from anything guessable — no
    timestamp, no username, no fixed salt. Never logged, never printed, never
    placed in a URL.
    """
    return _b64url(secrets.token_bytes(_PKCE_BYTES))


def challenge_for(verifier: str) -> str:
    """``base64url(sha256(verifier))`` with no padding. Always S256, never plain.

    ``plain`` is unusable here even on Flow A: the user can pick "Show me a
    code" on the consent screen, and then the challenge would have travelled on
    the authorize URL in the clear.
    """
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def generate_state() -> str:
    """An opaque CSRF token for one attempt."""
    return _b64url(secrets.token_bytes(_STATE_BYTES))


def build_authorize_url(
    *,
    callback_url: str,
    challenge: str,
    state: str,
    app_name: str = APP_NAME,
    scope: str = "api",
    login_hint: str | None = None,
    workspace_hint: str | None = None,
    prompt: str | None = None,
) -> str:
    """Build the consent-screen URL on the AUTH origin."""
    params = {
        "callback_url": callback_url,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "app_name": app_name,
        "scope": scope,
    }
    if login_hint:
        params["login_hint"] = login_hint
    if workspace_hint:
        params["workspace_hint"] = workspace_hint
    if prompt:
        params["prompt"] = prompt
    return f"{auth_url(AUTHORIZE_PATH)}?{urllib.parse.urlencode(params)}"


def _post_json(url: str, payload: dict, *, timeout: float) -> tuple[int, dict]:
    """POST JSON and decode the body, without ever echoing it into an error.

    Error text is deliberately NOT embedded in raised messages: an exchange
    failure body is untrusted server output that could contain the credential.
    The caller gets the status code and a plain description instead.
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(CATALOG_MAX_BYTES)
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = b""
        try:
            raw = exc.read(CATALOG_MAX_BYTES)
        except Exception:
            raw = b""
        status = exc.code
    except urllib.error.URLError as exc:
        raise OrcaRouterAuthError(
            f"Could not reach the OrcaRouter authentication service at {auth_base()} "
            f"({exc.reason}). Check your network connection and try again."
        ) from exc
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return status, data


def exchange_code(
    code: str,
    verifier: str,
    *,
    timeout: float = 30.0,
) -> OrcaCredential:
    """Redeem an auth code for a durable API key at ``/api/v1/auth/keys``.

    The verifier is sent in the POST body only. It is never placed in a URL and
    never appears in an error message.
    """
    if not code:
        raise OrcaRouterAuthError("No authorization code to exchange.")
    status, data = _post_json(
        auth_url(EXCHANGE_PATH),
        {
            "code": code,
            "code_verifier": verifier,
            "code_challenge_method": "S256",
        },
        timeout=timeout,
    )

    if status == 400:
        raise OrcaRouterAuthError(
            "OrcaRouter rejected the exchange (400): the code_challenge_method was not "
            "recognised, or it differs from the one sent at authorize time. Start the "
            "login again."
        )
    if status == 403:
        raise OrcaRouterAuthError(
            "OrcaRouter rejected the exchange (403): the code is unknown, expired, already "
            "used, or the verifier does not match. Auth codes are single-use with a "
            "10 minute TTL — start the login again."
        )
    if status == 429:
        raise OrcaRouterAuthError(
            "OrcaRouter rate-limited this login (429). There is a cap of 10 PKCE-issued "
            "keys per user per 24 hours; the client reuses the stored key instead of "
            "re-authorizing, so this usually means logins were forced repeatedly."
        )
    if status != 200:
        raise OrcaRouterAuthError(f"OrcaRouter rejected the exchange (HTTP {status}).")

    key = data.get("key")
    if not isinstance(key, str) or not key:
        raise OrcaRouterAuthError(
            "OrcaRouter returned no key in the exchange response. Start the login again."
        )

    # Read back what was GRANTED, not what was asked for. A workspace role can
    # narrow the grant, and a narrower grant cannot drive inference here.
    scope = data.get("scope")
    scope = scope if isinstance(scope, str) and scope else "api"
    if scope != "api":
        raise OrcaRouterAuthError(
            f"OrcaRouter granted scope {scope!r}, not 'api'. That grant does not permit "
            "inference, so it was not stored. Ask a workspace admin for a role that can "
            "grant 'api'."
        )

    return OrcaCredential(
        secret=key,
        source="pkce",
        key_id=_key_id_for(key),
        scope=scope,
        user_id=str(data.get("user_id") or ""),
    )


class _CallbackHandler(BaseHTTPRequestHandler):
    """Serves the loopback redirect target. One request, then it is done.

    ``_make_handler`` binds the expected state and the result slot for one
    listener, so two logins in the same process cannot see each other's state.
    """

    expected_state = ""
    result: dict = {}
    done: threading.Event

    def log_message(self, *args) -> None:  # noqa: D102 — silence the access log
        return

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(url.query)

        def one(name: str) -> str:
            values = params.get(name) or []
            return values[0] if values else ""

        if url.path != "/cb":
            self.send_response(404)
            self.end_headers()
            return

        # Constant-time compare BEFORE the code is allowed anywhere near the
        # flow. This is the only thing standing between the listener and a code
        # some other page dropped on it.
        state = one("state")
        if not hmac.compare_digest(state, self.expected_state):
            self.result["error"] = "state_mismatch"
            self._respond(
                "<p>Authorization failed: the state did not match. You can close this tab.</p>"
            )
            self.done.set()
            return

        error = one("error")
        if error:
            self.result["error"] = error
            self._respond(
                f"<p>Authorization was not completed ({_html_escape(error)}). "
                "You can close this tab.</p>"
            )
            self.done.set()
            return

        code = one("code")
        if not code:
            self.result["error"] = "missing_code"
            self._respond("<p>No authorization code was returned. You can close this tab.</p>")
            self.done.set()
            return

        self.result["code"] = code
        self._respond("<p>Connected to OrcaRouter. You can close this tab and return to graphify.</p>")
        self.done.set()

    def _respond(self, html: str) -> None:
        payload = (
            "<!doctype html><html><head><meta charset='utf-8'><title>graphify</title></head>"
            f"<body style='font-family:system-ui;padding:2rem'>{html}</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _html_escape(text: str) -> str:
    import html as _html

    return _html.escape(text)


def _make_handler(expected_state: str, result: dict, done: threading.Event) -> type:
    """Bind one listener's state/result onto a handler class.

    A per-listener subclass rather than class attributes on the shared base:
    the expected state is the CSRF token for ONE attempt, so reading it from a
    global would let a second concurrent login (or a stale one) validate against
    the wrong token.
    """

    class _BoundHandler(_CallbackHandler):
        pass

    _BoundHandler.expected_state = expected_state
    _BoundHandler.result = result
    _BoundHandler.done = done
    return _BoundHandler


class _LoopbackListener:
    """A one-shot loopback HTTP listener on an ephemeral port.

    Bound on ``127.0.0.1`` before the browser is opened, so the port is known
    and nothing races.
    """

    def __init__(self, expected_state: str, host: str = "127.0.0.1") -> None:
        if not _is_loopback_host(host):
            raise OrcaRouterAuthError(
                f"ORCAROUTER_OAUTH_CALLBACK_HOST={host!r} is not loopback. The redirect "
                "target must be localhost, 127.0.0.1 or [::1]."
            )
        self.host = host
        self.expected_state = expected_state
        self.result: dict = {}
        self.done = threading.Event()
        self._server: socketserver.TCPServer | None = None
        self.port = 0

    def __enter__(self) -> "_LoopbackListener":
        handler = _make_handler(self.expected_state, self.result, self.done)

        class _Server(socketserver.TCPServer):
            allow_reuse_address = True

        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        self._server = _Server((self.host, 0), handler, bind_and_activate=False)
        self._server.socket = socket.socket(family, socket.SOCK_STREAM)
        self._server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.server_bind()
        self._server.server_activate()
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    @property
    def callback_url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}/cb"

    def wait(self, timeout: float) -> dict:
        if not self.done.wait(timeout):
            raise OrcaRouterAuthError(
                f"Timed out after {int(timeout)}s waiting for the browser to return the "
                "authorization code. Run `graphify orcarouter login --flow oob` on a "
                "headless machine."
            )
        return dict(self.result)


class PkceSource:
    """The sign-in-with-your-account adapter (OAuth 2.0 + PKCE, S256).

    Produces exactly the same :class:`OrcaCredential` as :class:`ApiKeySource`
    and stores it in the same place. The exchange returns a durable API key, not
    a refresh token — so this is only ever run when there is no usable stored
    credential.
    """

    name = "pkce"

    def __init__(self, store: CredentialStore | None = None) -> None:
        self.store = store or CredentialStore()

    def acquire(self) -> OrcaCredential | None:
        stored = self.store.load()
        if stored is None or stored.needs_reauth:
            return None
        return stored

    def clear(self) -> None:
        self.store.clear()

    def connect(
        self,
        *,
        flow: str | None = None,
        open_browser: Callable[[str], object] | None = None,
        code_reader: Callable[[], str] | None = None,
        timeout: float | None = None,
        out: Callable[[str], None] | None = None,
    ) -> OrcaCredential:
        """Run the whole flow and persist the result.

        ``flow`` is ``loopback`` (Flow A, default) or ``oob`` (Flow B). The
        default comes from ``ORCAROUTER_OAUTH_FLOW`` so a headless environment
        can pick Flow B without changing the command line.
        """
        chosen = (flow or os.environ.get("ORCAROUTER_OAUTH_FLOW", "") or "loopback").strip().lower()
        aliases = {"a": "loopback", "loopback": "loopback", "b": "oob", "oob": "oob"}
        if chosen not in aliases:
            raise OrcaRouterAuthError(
                f"Unknown OAuth flow {chosen!r}. Use 'loopback' (Flow A) or 'oob' (Flow B)."
            )
        chosen = aliases[chosen]
        emit = out or (lambda line: print(line, file=sys.stderr))
        open_url = open_browser or webbrowser.open
        ask = code_reader or (lambda: input("Code: "))
        wait_s = timeout if timeout is not None else _oauth_timeout()

        # Fresh verifier + state for THIS attempt, from the CSPRNG. The verifier
        # stays in this stack frame until the exchange.
        verifier = generate_verifier()
        challenge = challenge_for(verifier)
        state = generate_state()

        listener: _LoopbackListener | None = None
        try:
            if chosen == "loopback":
                listener = _LoopbackListener(
                    state, os.environ.get("ORCAROUTER_OAUTH_CALLBACK_HOST", "127.0.0.1")
                )
                listener.__enter__()
                callback_url = listener.callback_url
            else:
                # Flow B asks for out-of-band delivery explicitly rather than
                # omitting callback_url and letting the server guess.
                callback_url = "oob"

            url = build_authorize_url(callback_url=callback_url, challenge=challenge, state=state)
            emit(f"Authorize graphify in your browser:\n  {url}")
            try:
                open_url(url)
            except Exception:
                emit("(Could not open a browser automatically — open the URL above.)")

            if chosen == "loopback":
                assert listener is not None
                result = listener.wait(wait_s)
                error = result.get("error")
                if error == "state_mismatch":
                    raise OrcaRouterAuthError(
                        "The redirect did not carry the state this login sent. It was "
                        "ignored and no key was stored. Start the login again."
                    )
                if error:
                    raise OrcaRouterAuthError(
                        f"Authorization was not completed ({error}). No key was stored."
                    )
                code = result.get("code") or ""
            else:
                code = (ask() or "").strip()
                if not code:
                    raise OrcaRouterAuthError("No code entered; no key was stored.")
        finally:
            if listener is not None:
                listener.close()

        credential = exchange_code(code, verifier, timeout=min(wait_s, 30.0))
        return self.store.save(credential)


def _oauth_timeout() -> float:
    raw = os.environ.get("ORCAROUTER_OAUTH_TIMEOUT", "").strip()
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_OAUTH_TIMEOUT_S


# ── The seam, resolved ────────────────────────────────────────────────────────


def resolve_credential(*, allow_reauth: bool = False) -> OrcaCredential | None:
    """Return the active OrcaRouter credential, or None.

    Both adapters are tried in one place so no call site has to know which one
    produced the secret. An ``ORCAROUTER_API_KEY`` in the environment is an
    explicit override and wins; otherwise the persisted record is used whether
    it came from ``key set`` or a PKCE login.

    A record flagged ``needs_reauth`` is returned but marked, so callers can
    explain the situation instead of silently retrying a revoked key. It is
    never deleted here — the user's re-login replaces it.
    """
    store = CredentialStore()
    env = ApiKeySource(store).from_env()
    if env is not None:
        return env
    stored = store.load()
    if stored is None:
        return None
    if stored.needs_reauth and not allow_reauth:
        return replace(stored, needs_reauth=True)
    return stored


def resolve_credential_secret() -> str:
    """The one call the inference path makes. Empty string when unconfigured."""
    credential = resolve_credential()
    return credential.secret if credential is not None else ""


def note_rejected(secret: str) -> bool:
    """Terminal reauthentication: the gateway rejected ``secret`` with a 401.

    Flags the stored credential as needing re-login, but ONLY when the rejected
    secret is still the stored one. Two failure modes are deliberately not
    covered:

    * an ``ORCAROUTER_API_KEY`` supplied from the environment — the user owns
      that variable, and graphify has no stored record to mark;
    * a secret that has already been replaced by a newer login — a late 401
      from a request that began before the re-login must not poison the fresh
      credential.

    No refresh is attempted, because OrcaRouter issues durable keys rather than
    refreshable tokens. The old secret is left in place; the next successful
    login replaces it.
    """
    store = CredentialStore()
    stored = store.load()
    if stored is None or not secret or stored.secret != secret:
        return False
    return store.mark_needs_reauth(stored.key_id, stored.generation)


def connect_with_api_key(secret: str) -> OrcaCredential:
    """Adapter 1 entry point: store a pasted key."""
    return ApiKeySource().save(secret)


def connect_with_pkce(**kwargs: Any) -> OrcaCredential:
    """Adapter 2 entry point: run OAuth 2.0 + PKCE and store the result."""
    return PkceSource().connect(**kwargs)


# ── Model catalog ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelInfo:
    """One catalog entry, with the metadata graphify actually consumes."""

    id: str
    name: str = ""
    owned_by: str = ""
    context_length: int = 0
    max_completion_tokens: int = 0
    input_modalities: tuple[str, ...] = ()
    output_modalities: tuple[str, ...] = ()
    supported_endpoint_types: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ()
    source: str = "live"  # "live" | "seed"

    def supports(self, capability: str) -> bool:
        return _model_supports(self, capability)


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value if isinstance(v, (str, int)))
    return ()


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _model_from_api(raw: object) -> ModelInfo | None:
    """Validate ONE catalog record. Returns None for a record we cannot trust.

    Shape validation is the control that stops a malformed or hostile catalog
    from advertising a route this client cannot speak.
    """
    if not isinstance(raw, dict):
        return None
    model_id = raw.get("id")
    if not isinstance(model_id, str):
        return None
    model_id = model_id.strip()
    if not model_id or len(model_id) > CATALOG_MAX_ID_LEN:
        return None

    endpoints = tuple(e for e in _as_str_tuple(raw.get("supported_endpoint_types")) if e)
    architecture = raw.get("architecture")
    architecture = architecture if isinstance(architecture, dict) else {}

    return ModelInfo(
        id=model_id,
        name=str(raw.get("name") or ""),
        owned_by=str(raw.get("owned_by") or ""),
        context_length=_as_int(raw.get("context_length")),
        max_completion_tokens=_as_int(raw.get("max_completion_tokens")),
        input_modalities=_as_str_tuple(architecture.get("input_modalities")),
        output_modalities=_as_str_tuple(architecture.get("output_modalities")),
        supported_endpoint_types=endpoints,
        reasoning_efforts=_as_str_tuple(raw.get("reasoning_efforts")),
        source="live",
    )


def _endpoint_types_for_capability(capability: str) -> tuple[str, ...]:
    if capability == "chat":
        return TEXT_ENDPOINT_TYPES
    if capability == "embedding":
        return ("embeddings",)
    if capability == "image":
        return ("image-generation",)
    if capability == "video":
        return ("openai-video",)
    if capability == "rerank":
        return ("jina-rerank",)
    return ()


def _model_supports(model: ModelInfo, capability: str) -> bool:
    """Capability filter. Fails closed whenever the metadata is absent.

    Never infers a capability from a model's NAME — only from declared
    endpoint types and declared modalities.
    """
    endpoints = set(model.supported_endpoint_types)

    if capability == "chat":
        # Must declare a route this client can speak.
        if not (endpoints & set(TEXT_ENDPOINT_TYPES)):
            return False
        # A record that declares output modalities and does not list text is an
        # image/video generator that happens to share the OpenAI route.
        if model.output_modalities and "text" not in model.output_modalities:
            return False
        return True

    if capability == "vision":
        # Chat first, then an EXPLICIT image input modality. A model with no
        # architecture block fails closed — we do not guess.
        if not _model_supports(model, "chat"):
            return False
        return "image" in model.input_modalities

    if capability in ("embedding", "image", "video", "rerank"):
        return bool(endpoints & set(_endpoint_types_for_capability(capability)))

    return False


def _supports_media(model: ModelInfo, media: str) -> bool:
    """Multimodal understanding filter for one uploaded media kind."""
    if media == "text":
        return _model_supports(model, "chat")
    if media in ("image", "audio", "video"):
        if not _model_supports(model, "chat"):
            return False
        return media in model.input_modalities
    return False


# Cold-start seed. Used ONLY when live discovery fails, and never merged into a
# successful live result. Every entry carries the metadata we have verified;
# entries are deliberately few and sourced rather than a long guess.
VERIFIED_SEED: tuple[ModelInfo, ...] = (
    ModelInfo(
        id="openai/gpt-5.5",
        name="GPT-5.5",
        owned_by="openai",
        context_length=400_000,
        max_completion_tokens=128_000,
        input_modalities=("text", "image"),
        output_modalities=("text",),
        supported_endpoint_types=("openai", "openai-response", "anthropic", "gemini"),
        # Verified reasoning ladder; retained so live discovery cannot silently
        # flatten it (see _merge_seed_metadata).
        reasoning_efforts=("low", "medium", "high", "xhigh"),
        source="seed",
    ),
    ModelInfo(
        id="anthropic/claude-opus-4.8",
        name="Claude Opus 4.8",
        owned_by="anthropic",
        context_length=200_000,
        max_completion_tokens=64_000,
        input_modalities=("text", "image"),
        output_modalities=("text",),
        supported_endpoint_types=("openai", "anthropic", "gemini"),
        reasoning_efforts=("low", "medium", "high"),
        source="seed",
    ),
    ModelInfo(
        id="google/gemini-3.5-flash",
        name="Gemini 3.5 Flash",
        owned_by="google",
        context_length=1_000_000,
        max_completion_tokens=65_536,
        input_modalities=("text", "image"),
        output_modalities=("text",),
        supported_endpoint_types=("openai", "gemini"),
        source="seed",
    ),
    ModelInfo(
        id="deepseek/deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        owned_by="deepseek",
        context_length=128_000,
        max_completion_tokens=32_768,
        input_modalities=("text",),
        output_modalities=("text",),
        supported_endpoint_types=("openai",),
        source="seed",
    ),
    ModelInfo(
        # The gateway's own routing alias: always resolvable, so it is the
        # safest default when nothing else is confirmed.
        id="orcarouter/auto",
        name="OrcaRouter Auto",
        owned_by="orcarouter",
        context_length=128_000,
        max_completion_tokens=32_768,
        input_modalities=("text",),
        output_modalities=("text",),
        supported_endpoint_types=("openai", "openai-response", "anthropic", "gemini"),
        source="seed",
    ),
)

SEED_DEFAULT_MODEL = "orcarouter/auto"
SEED_VISION_MODEL = "openai/gpt-5.5"


def _seed_index() -> dict[str, ModelInfo]:
    return {m.id: m for m in VERIFIED_SEED}


def _merge_seed_metadata(models: list[ModelInfo]) -> list[ModelInfo]:
    """Overlay verified metadata onto a live record that omits it.

    Live discovery is authoritative for which models exist AND for anything it
    actually declares. The seed only fills fields the live record is silent
    about — the reasoning ladder, a missing context window, and modalities when
    there is no ``architecture`` block at all. A live record that declares a
    narrower modality set (say text-only) keeps it: reducing a model to what the
    gateway says it is, is the fail-closed direction. Inventing image support
    from the seed would not be.
    """
    seed = _seed_index()
    merged: list[ModelInfo] = []
    for model in models:
        known = seed.get(model.id)
        if known is None:
            merged.append(model)
            continue
        overlay: dict[str, Any] = {
            "reasoning_efforts": model.reasoning_efforts or known.reasoning_efforts,
            "context_length": model.context_length or known.context_length,
            "max_completion_tokens": model.max_completion_tokens or known.max_completion_tokens,
        }
        if not (model.input_modalities or model.output_modalities):
            # No architecture block at all -> fall back to the verified record.
            overlay["input_modalities"] = known.input_modalities
            overlay["output_modalities"] = known.output_modalities
        merged.append(replace(model, **overlay))
    return merged


@dataclass
class ModelCatalog:
    """A model list plus where it came from, for honest UI/CLI reporting."""

    models: list[ModelInfo]
    source: str  # "live" | "seed" | "last-known-good"
    degraded: bool = False
    error: str = ""

    def filter(self, capability: str) -> list["ModelInfo"]:
        return [m for m in self.models if _model_supports(m, capability)]

    def filter_for_media(self, media: Iterable[str]) -> list["ModelInfo"]:
        wanted = [m for m in media if m and m != "text"]
        if not wanted:
            return self.filter("chat")
        return [m for m in self.models if all(_supports_media(m, w) for w in wanted)]

    def get(self, model_id: str) -> ModelInfo | None:
        return next((m for m in self.models if m.id == model_id), None)


def _catalog_cache_path() -> Path:
    return store_path().with_name("orcarouter-models.json")


def _read_last_known_good() -> list[ModelInfo] | None:
    try:
        data = json.loads(_catalog_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    raw = data.get("models") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return None
    models = [m for m in (_model_from_api(r) for r in raw[:CATALOG_MAX_ITEMS]) if m is not None]
    return models or None


def _write_last_known_good(models: list[ModelInfo]) -> None:
    from graphify.paths import write_json_atomic

    try:
        path = _catalog_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            path,
            {
                "models": [
                    {
                        "id": m.id,
                        "name": m.name,
                        "owned_by": m.owned_by,
                        "context_length": m.context_length,
                        "max_completion_tokens": m.max_completion_tokens,
                        "architecture": {
                            "input_modalities": list(m.input_modalities),
                            "output_modalities": list(m.output_modalities),
                        },
                        "supported_endpoint_types": list(m.supported_endpoint_types),
                        "reasoning_efforts": list(m.reasoning_efforts),
                    }
                    for m in models
                ]
            },
            indent=None,
        )
    except Exception:
        # A cache write failure must never break discovery.
        pass


def discover_models(
    api_key: str,
    *,
    capability: str | None = None,
    timeout: float = CATALOG_TIMEOUT_S,
) -> list[ModelInfo]:
    """Fetch the authoritative catalog from ``GET {api_base}/models``.

    Bounded on every axis: timeout, response bytes, item count, id length and
    per-record shape. Ids are preserved verbatim, including the ``vendor/model``
    namespace.
    """
    url = api_url("/models")
    if capability:
        url = f"{url}?{urllib.parse.urlencode({'capability': capability})}"

    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(CATALOG_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise OrcaRouterCatalogError(
                f"The OrcaRouter model catalog rejected this credential (HTTP {exc.code}). "
                "The key may have been revoked — run `graphify orcarouter login`."
            ) from exc
        raise OrcaRouterCatalogError(f"Model catalog unavailable (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise OrcaRouterCatalogError(f"Could not reach {api_base()} ({exc.reason}).") from exc

    if len(raw) > CATALOG_MAX_BYTES:
        raise OrcaRouterCatalogError(
            f"Model catalog response exceeded {CATALOG_MAX_BYTES} bytes; refusing to parse it."
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise OrcaRouterCatalogError(f"Model catalog was not valid JSON: {exc}") from exc

    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise OrcaRouterCatalogError("Model catalog response had no model list.")

    models: list[ModelInfo] = []
    seen: set[str] = set()
    for raw_item in items[:CATALOG_MAX_ITEMS]:
        model = _model_from_api(raw_item)
        if model is None or model.id in seen:
            continue
        seen.add(model.id)
        models.append(model)

    if not models:
        raise OrcaRouterCatalogError("Model catalog contained no usable model records.")
    return _merge_seed_metadata(models)


def load_catalog(
    credential: OrcaCredential | None = None,
    *,
    capability: str | None = None,
    timeout: float = CATALOG_TIMEOUT_S,
    prefer_cache: bool = True,
) -> ModelCatalog:
    """Live catalog when reachable, otherwise last-known-good, otherwise seed.

    The seed is NEVER mixed into a successful live result. A degraded catalog
    says so, so callers can surface it rather than silently showing less.
    """
    cred = credential if credential is not None else resolve_credential()
    api_key = cred.secret if cred is not None else ""
    try:
        models = discover_models(api_key, capability=capability, timeout=timeout)
    except OrcaRouterCatalogError as exc:
        if prefer_cache:
            cached = _read_last_known_good()
            if cached:
                return ModelCatalog(list(cached), source="last-known-good", degraded=True, error=str(exc))
        return ModelCatalog(list(VERIFIED_SEED), source="seed", degraded=True, error=str(exc))
    if capability is None:
        _write_last_known_good(models)
    return ModelCatalog(models, source="live", degraded=False)


def models_for_capability(capability: str) -> ModelCatalog:
    """Catalog narrowed to one capability — what a model selector should offer."""
    if capability not in CAPABILITIES:
        raise OrcaRouterError(
            f"Unknown capability {capability!r}. Known: {', '.join(CAPABILITIES)}."
        )
    catalog = load_catalog(capability=capability if capability in ("embedding", "image") else None)
    if capability in ("embedding", "image", "video", "rerank"):
        # These routes are declared in supported_endpoint_types, not in a
        # dedicated ?capability= filter, so filter locally too.
        return replace(catalog, models=catalog.filter(capability))
    if capability == "vision":
        return replace(catalog, models=catalog.filter("vision"))
    return replace(catalog, models=catalog.filter("chat"))


def media_kinds(paths: Iterable[str]) -> list[str]:
    """The non-text modalities a corpus actually contains.

    Drives the model filter for the extraction entry point: a corpus with
    raster images needs a model that DECLARES image input, not one whose name
    sounds multimodal.
    """
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    found: list[str] = []
    for path in paths:
        suffix = Path(str(path)).suffix.lower()
        if suffix in image_exts and "image" not in found:
            found.append("image")
    return found


def resolve_model(
    model: str | None,
    *,
    media: Iterable[str] = (),
    catalog: ModelCatalog | None = None,
) -> tuple[str, ModelCatalog]:
    """Pick a model that is actually valid for what this run will send.

    This is the CLI equivalent of a capability-filtered model dropdown: the
    candidate list is the filtered catalog, an incompatible explicitly-selected
    model is CLEARED (with the compatible options named) rather than silently
    kept, and a live catalog outage falls back to the verified seed.

    Returns ``(model_id, catalog)``. Raises ``OrcaRouterError`` when the
    selection is incompatible and must be re-made.
    """
    cat = catalog if catalog is not None else load_catalog()
    kinds = [k for k in media if k and k != "text"]
    compatible = cat.filter_for_media(kinds) if kinds else cat.filter("chat")

    if not compatible:
        wanted = ", ".join(kinds) if kinds else "chat"
        raise OrcaRouterError(
            f"The OrcaRouter catalog at {api_base()} lists no model supporting {wanted}. "
            f"(catalog source: {cat.source}{'; ' + cat.error if cat.error else ''})"
        )

    if model:
        if any(m.id == model for m in compatible):
            return model, cat
        # An explicitly requested model that cannot serve this run is cleared —
        # keeping it would send an incompatible payload.
        detail = ", ".join(kinds) if kinds else "chat"
        options = ", ".join(m.id for m in compatible[:12])
        raise OrcaRouterError(
            f"Model {model!r} is not available for {detail} on OrcaRouter. "
            f"Compatible models: {options}. "
            "Re-run with `--model <id>` from that list (or drop --model to use the default)."
        )

    preferred = SEED_VISION_MODEL if "image" in kinds else SEED_DEFAULT_MODEL
    if any(m.id == preferred for m in compatible):
        return preferred, cat
    return compatible[0].id, cat
