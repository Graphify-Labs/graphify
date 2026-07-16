from __future__ import annotations

import hashlib
import hmac
import os
import posixpath
import secrets

SALT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DEFAULT_PBKDF2_ITERATIONS = 1_000_000

_os_alt_seps: list[str] = list(
    sep for sep in [os.sep, os.altsep] if sep is not None and sep != "/"
)
# https://chrisdenton.github.io/omnipath/Special%20Dos%20Device%20Names.html
_windows_device_files = {
    "AUX",
    "CON",
    "CONIN$",
    "CONOUT$",
    *(f"COM{c}" for c in "123456789¹²³"),
    *(f"LPT{c}" for c in "123456789¹²³"),
    "NUL",
    "PRN",
}


def gen_salt(length: int) -> str:
    """Generate a random string of SALT_CHARS with specified ``length``."""
    if length <= 0:
        raise ValueError("Salt length must be at least 1.")

    return "".join(secrets.choice(SALT_CHARS) for _ in range(length))


def _hash_internal(method: str, salt: str, password: str) -> tuple[str, str]:
    method, *args = method.split(":")
    salt_bytes = salt.encode()
    password_bytes = password.encode()

    if method == "scrypt":
        if not args:
            n = 2**15
            r = 8
            p = 1
        else:
            try:
                n, r, p = map(int, args)
            except ValueError:
                raise ValueError("'scrypt' takes 3 arguments.") from None

        maxmem = 132 * n * r * p  # ideally 128, but some extra seems needed
        return (
            hashlib.scrypt(
                password_bytes, salt=salt_bytes, n=n, r=r, p=p, maxmem=maxmem
            ).hex(),
            f"scrypt:{n}:{r}:{p}",
        )
    elif method == "pbkdf2":
        len_args = len(args)

        if len_args == 0:
            hash_name = "sha256"
            iterations = DEFAULT_PBKDF2_ITERATIONS
        elif len_args == 1:
            hash_name = args[0]
            iterations = DEFAULT_PBKDF2_ITERATIONS
        elif len_args == 2:
            hash_name = args[0]
            iterations = int(args[1])
        else:
            raise ValueError("'pbkdf2' takes 2 arguments.")

        return (
            hashlib.pbkdf2_hmac(
                hash_name, password_bytes, salt_bytes, iterations
            ).hex(),
            f"pbkdf2:{hash_name}:{iterations}",
        )
    else:
        raise ValueError(f"Invalid hash method '{method}'.")


def generate_password_hash(
    password: str, method: str = "scrypt", salt_length: int = 16
) -> str:
    """Securely hash a password for storage. A password can be compared to a stored hash
    using :func:`check_password_hash`.

    The following methods are supported:

    -   ``scrypt``, the default. The parameters are ``n``, ``r``, and ``p``, the default
        is ``scrypt:32768:8:1``. See :func:`hashlib.scrypt`.
    -   ``pbkdf2``, less secure. The parameters are ``hash_method`` and ``iterations``,
        the default is ``pbkdf2:sha256:600000``. See :func:`hashlib.pbkdf2_hmac`.

    Default parameters may be updated to reflect current guidelines, and methods may be
    deprecated and removed if they are no longer considered secure. To migrate old
    hashes, you may generate a new hash when checking an old hash, or you may contact
    users with a link to reset their password.

    :param password: The plaintext password.
    :param method: The key derivation function and parameters.
    :param salt_length: The number of characters to generate for the salt.

    .. versionchanged:: 3.1
        The default iterations for pbkdf2 was increased to 1,000,000.

    .. versionchanged:: 2.3
        Scrypt support was added.

    .. versionchanged:: 2.3
        The default iterations for pbkdf2 was increased to 600,000.

    .. versionchanged:: 2.3
        All plain hashes are deprecated and will not be supported in Werkzeug 3.0.
    """
    salt = gen_salt(salt_length)
    h, actual_method = _hash_internal(method, salt, password)
    return f"{actual_method}${salt}${h}"


def check_password_hash(pwhash: str, password: str) -> bool:
    """Securely check that the given stored password hash, previously generated using
    :func:`generate_password_hash`, matches the given password.

    Methods may be deprecated and removed if they are no longer considered secure. To
    migrate old hashes, you may generate a new hash when checking an old hash, or you
    may contact users with a link to reset their password.

    :param pwhash: The hashed password.
    :param password: The plaintext password.

    .. versionchanged:: 2.3
        All plain hashes are deprecated and will not be supported in Werkzeug 3.0.
    """
    try:
        method, salt, hashval = pwhash.split("$", 2)
    except ValueError:
        return False

    return hmac.compare_digest(_hash_internal(method, salt, password)[0], hashval)


def safe_join(directory: str, *untrusted: str) -> str | None:
    """Safely join zero or more untrusted path components to a trusted base
    directory to avoid escaping the base directory.

    The untrusted path is assumed to be from/for a URL, such as for serving
    files. Therefore, it should only use the forward slash ``/`` path separator,
    and will be joined using that separator. On Windows, the backslash ``\\``
    separator is not allowed.

    :param directory: The trusted base directory.
    :param untrusted: The untrusted path components relative to the
        base directory.
    :return: A safe path, otherwise ``None``.

    .. versionchanged:: 3.1.6
        Special device names in multi-segment paths are not allowed on Windows.

    .. versionchanged:: 3.1.5
        More special device names, regardless of extension or trailing spaces,
        are not allowed on Windows.

    .. versionchanged:: 3.1.4
        Special device names are not allowed on Windows.
    """
    if not directory:
        # Ensure we end up with ./path if directory="" is given,
        # otherwise the first untrusted part could become trusted.
        directory = "."

    parts = [directory]

    for part in untrusted:
        if not part:
            continue

        part = posixpath.normpath(part)

        if (
            os.path.isabs(part)
            # ntpath.isabs doesn't catch this
            or part.startswith("/")
            or part == ".."
            or part.startswith("../")
            or any(sep in part for sep in _os_alt_seps)
            or (
                os.name == "nt"
                and any(
                    p.partition(".")[0].strip().upper() in _windows_device_files
                    for p in part.split("/")
                )
            )
        ):
            return None

        parts.append(part)

    return posixpath.join(*parts)
