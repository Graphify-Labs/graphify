"""``graphify orcarouter`` — the CLI surface for the OrcaRouter provider.

Two explicit authentication choices, both landing on the same inference path:

* **OrcaRouter - API** — paste an existing ``sk-orca-…`` key
  (``graphify orcarouter key set``), or set ``ORCAROUTER_API_KEY``.
* **OrcaRouter - Auth** — sign in with an OrcaRouter account over OAuth 2.0 +
  PKCE (``graphify orcarouter login``), which issues an ordinary
  ``sk-orca-…`` key owned by the user.

Keeping them as two named commands (rather than one button that sometimes
prompts and sometimes opens a browser) is what makes status, logout and
reauthentication unambiguous.
"""

from __future__ import annotations

import sys

from graphify import orcarouter as orca

_USAGE = """\
graphify orcarouter — OrcaRouter provider (inference + account login)

Auth (two explicit choices):
  login [--flow loopback|oob]   Sign in with OrcaRouter (OAuth 2.0 + PKCE)
  login --api-key [KEY]         Store an existing sk-orca-… API key
  key set [KEY]                 Same as `login --api-key` (prompts when omitted)
  key clear                     Remove the stored credential
  status                        Show which credential is active (key is masked)

Models:
  models [--capability C]       List the live catalog from the configured origin
  use <model-id>                Pin a default model for this provider

  --capability: chat (default), vision, embedding, image, video, rerank

Environment:
  ORCAROUTER_API_KEY            API-key path (explicit override)
  ORCA_BASE_URL                 Shared self-hosted origin (auth + inference)
  ORCA_AUTH_BASE_URL            Auth origin override   (default {auth})
  ORCA_API_BASE_URL             Inference origin override (default {api})
  GRAPHIFY_ORCAROUTER_MODEL     Default model override
  ORCAROUTER_OAUTH_FLOW         loopback (default) or oob
  ORCAROUTER_OAUTH_TIMEOUT      Seconds to wait for the redirect (default 300)

Key management and revocation: {dashboard}
""".format(auth=orca.DEFAULT_AUTH_BASE, api=orca.DEFAULT_API_BASE, dashboard=orca.KEY_DASHBOARD_URL)


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _print_credential(credential: orca.OrcaCredential, action: str) -> None:
    print(f"  {action} ({credential.source})")
    print(f"  key:   {credential.masked()}")
    print(f"  scope: {credential.scope}")
    print(f"  store: {orca.store_path()}")


def _cmd_status() -> int:
    status = orca.ApiKeySource().status()
    print("OrcaRouter credential")
    print(f"  source:   {status['source']}")
    print(f"  key:      {status['masked']}")
    if status["present"]:
        print(f"  scope:    {status['scope']}")
        print(f"  key id:   {status['key_id']} (generation {status['generation']})")
    print(f"  store:    {status['store']}")
    # There is no documented non-billing validation endpoint, so claiming a
    # credential is "valid" here would be a guess. The first real request is
    # what establishes validity.
    print(f"  validity: {status['validation']} (first request confirms)")
    if status["needs_reauth"]:
        print()
        print("  This credential was rejected by OrcaRouter and is marked for")
        print("  reauthentication. It may have been revoked at:")
        print(f"    {orca.KEY_DASHBOARD_URL}")
        print("  Re-authorize with: graphify orcarouter login")
    if not status["present"]:
        print()
        print("  No credential configured. Either:")
        print("    graphify orcarouter key set      (paste an sk-orca-… key)")
        print("    graphify orcarouter login        (sign in with your account)")
    return 0


def _cmd_models(argv: list[str]) -> int:
    capability = "chat"
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--capability" and i + 1 < len(argv):
            capability = argv[i + 1]
            i += 2
        elif arg.startswith("--capability="):
            capability = arg.split("=", 1)[1]
            i += 1
        else:
            i += 1

    if capability not in orca.CAPABILITIES:
        _err(f"error: unknown capability {capability!r}. Known: {', '.join(orca.CAPABILITIES)}")
        return 2

    catalog = orca.load_catalog()
    models = catalog.models if capability == "chat" else catalog.filter(capability)

    print(f"OrcaRouter models  ({orca.api_base()})")
    print(f"  catalog: {catalog.source}" + ("  [DEGRADED]" if catalog.degraded else ""))
    if catalog.error:
        print(f"  note:    {catalog.error}")
    if catalog.source == "seed":
        print("  note:    live discovery failed — showing the verified cold-start seed only.")
    print(f"  filter:  {capability}  ->  {len(models)} model(s)")
    print()
    for model in models:
        bits = []
        if model.context_length:
            bits.append(f"ctx {model.context_length}")
        if model.input_modalities:
            bits.append("in:" + "/".join(model.input_modalities))
        if model.reasoning_efforts:
            bits.append("effort:" + "/".join(model.reasoning_efforts))
        suffix = ("  " + "  ".join(bits)) if bits else ""
        print(f"  {model.id}{suffix}")
    if not models:
        print("  (none)")
    return 0


def _cmd_use(argv: list[str]) -> int:
    if not argv or not argv[0].strip():
        _err("usage: graphify orcarouter use <model-id>")
        return 2
    model = argv[0].strip()
    catalog = orca.load_catalog()
    info = catalog.get(model)
    if info is None:
        _err(
            f"error: {model!r} is not in the OrcaRouter catalog ({len(catalog.models)} models, "
            f"source: {catalog.source}). Run `graphify orcarouter models` to see the list."
        )
        return 1
    if not info.supports("chat"):
        _err(
            f"error: {model!r} does not support text chat on OrcaRouter "
            f"(declared routes: {', '.join(info.supported_endpoint_types) or 'none'})."
        )
        return 1
    print(f"Pinned OrcaRouter model: {model}")
    print("Use it with:  export GRAPHIFY_ORCAROUTER_MODEL=" + model)
    print("         or:  graphify extract . --backend orcarouter --model " + model)
    return 0


def _cmd_key_set(argv: list[str]) -> int:
    if argv and argv[0].strip():
        secret = argv[0].strip()
    else:
        import getpass

        try:
            secret = getpass.getpass("OrcaRouter API key (sk-orca-…): ").strip()
        except (EOFError, KeyboardInterrupt):
            _err("\nAborted; nothing was stored.")
            return 1
    try:
        credential = orca.connect_with_api_key(secret)
    except orca.OrcaRouterError as exc:
        _err(f"error: {exc}")
        return 1
    _print_credential(credential, "Stored OrcaRouter API key.")
    print("  Use it with: graphify extract . --backend orcarouter")
    return 0


def _cmd_key_clear() -> int:
    store = orca.CredentialStore()
    if store.clear():
        print("OrcaRouter credential removed.")
    else:
        print("No stored OrcaRouter credential to remove.")
    print("Note: ORCAROUTER_API_KEY in the environment is not affected.")
    return 0


def _cmd_login(argv: list[str]) -> int:
    flow: str | None = None
    api_key: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--flow" and i + 1 < len(argv):
            flow = argv[i + 1]
            i += 2
        elif arg.startswith("--flow="):
            flow = arg.split("=", 1)[1]
            i += 1
        elif arg == "--api-key":
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                api_key = argv[i + 1]
                i += 2
            else:
                api_key = ""
                i += 1
        elif arg.startswith("--api-key="):
            api_key = arg.split("=", 1)[1]
            i += 1
        else:
            i += 1

    if api_key is not None:
        return _cmd_key_set([api_key] if api_key else [])

    # Reuse the stored key rather than minting a second one. OrcaRouter caps
    # PKCE-issued keys at 10 per user per 24 hours, so re-authorizing on every
    # launch would lock the user out by lunchtime.
    existing = orca.PkceSource().acquire()
    if existing is not None:
        print("Already connected to OrcaRouter — reusing the stored credential.")
        _print_credential(existing, "Active credential.")
        print("  Re-authorize anyway with: graphify orcarouter login --flow loopback --force")
        return 0
    if "--force" not in argv:
        api_existing = orca.ApiKeySource().acquire()
        if api_existing is not None and api_existing.source == "api_key":
            print("A stored API key is already configured; not starting a browser login.")
            _print_credential(api_existing, "Active credential.")
            print("  Force a new login with: graphify orcarouter login --force")
            return 0

    try:
        credential = orca.connect_with_pkce(flow=flow)
    except orca.OrcaRouterError as exc:
        _err(f"error: {exc}")
        return 1
    except KeyboardInterrupt:
        _err("\nCancelled; no key was stored.")
        return 1

    print()
    _print_credential(credential, "Connected to OrcaRouter.")
    print("  Use it with: graphify extract . --backend orcarouter")
    print(f"  Revoke it any time at: {orca.KEY_DASHBOARD_URL}")
    return 0


def cmd_orcarouter(argv: list[str]) -> None:
    """Entry point for ``graphify orcarouter <subcommand>``."""
    sub = argv[0] if argv else ""
    rest = argv[1:]

    if sub == "login":
        code = _cmd_login(rest)
    elif sub == "status":
        code = _cmd_status()
    elif sub == "models":
        code = _cmd_models(rest)
    elif sub == "use":
        code = _cmd_use(rest)
    elif sub == "key":
        action = rest[0] if rest else ""
        if action == "set":
            code = _cmd_key_set(rest[1:])
        elif action == "clear":
            code = _cmd_key_clear()
        else:
            _err("usage: graphify orcarouter key [set|clear]")
            code = 2
    elif sub in ("", "-h", "--help", "help"):
        print(_USAGE, end="")
        code = 0
    else:
        _err(f"error: unknown subcommand {sub!r}\n")
        _err(_USAGE)
        code = 2

    if code:
        sys.exit(code)
