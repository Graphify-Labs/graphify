"""Persistent token-usage ledger shared by CLI pipeline commands."""
from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


@contextmanager
def _cost_lock(output_dir: Path) -> Iterator[None]:
    """Serialize ledger updates across processes without stale lock cleanup."""
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / ".cost.lock"
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _total_from_runs(runs: list, key: str) -> int:
    total = 0
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("cost.json 'runs' entries must be JSON objects")
        value = run.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"cost.json run '{key}' must be numeric")
        total += int(value)
    return total


def _write_atomic(path: Path, payload: str) -> None:
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    while True:
        tmp_name = path.parent / f".cost.{secrets.token_hex(8)}.tmp"
        try:
            fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            break
        except FileExistsError:
            continue
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        if existing_mode is not None:
            os.chmod(tmp_name, existing_mode)
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def record_cost_run(
    output_dir: Path,
    *,
    input_tokens: int,
    output_tokens: int,
    files: int,
) -> dict:
    """Append one run to ``cost.json`` and return the updated ledger."""
    with _cost_lock(output_dir):
        cost_path = output_dir / "cost.json"
        cost: dict
        if cost_path.exists():
            cost = json.loads(cost_path.read_text(encoding="utf-8"))
            if not isinstance(cost, dict):
                raise ValueError("cost.json must contain a JSON object")
        else:
            cost = {"runs": []}

        runs = cost.setdefault("runs", [])
        if not isinstance(runs, list):
            raise ValueError("cost.json 'runs' must be a JSON array")

        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        files = int(files or 0)
        runs.append({
            "date": datetime.now(timezone.utc).isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "files": files,
        })
        cost["total_input_tokens"] = _total_from_runs(runs, "input_tokens")
        cost["total_output_tokens"] = _total_from_runs(runs, "output_tokens")

        _write_atomic(
            cost_path,
            json.dumps(cost, indent=2, ensure_ascii=False),
        )
        return cost
