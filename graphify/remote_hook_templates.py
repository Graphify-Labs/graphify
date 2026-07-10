"""Starter push/pull hook bodies scaffolded by `graphify remote init` into .graphify/.

Examples, not graphify dependencies — a hook can do anything (S3, git, rsync,
gcs). It receives the store context in the environment (see graphify.remote):
GRAPHIFY_ACTION / GRAPHIFY_STORE_DIR / GRAPHIFY_PREFIX / GRAPHIFY_REPO /
GRAPHIFY_BRANCH. The contract: mirror GRAPHIFY_STORE_DIR (the
``<store>/<repo>/<branch>`` tree holding every module's graphify-out) to the
backend under GRAPHIFY_PREFIX. Exit non-zero on failure.

The shebang pins an env with boto3 so the hook is self-contained; on Windows,
graphify runs a ``.py`` hook with its own interpreter (shebang ignored), so
install boto3 there or swap the body for the AWS CLI.
"""

_HEADER = """#!/usr/bin/env -S uv run --with boto3 python3
# graphify {action} hook (scaffolded by `graphify remote init`) — S3/MinIO starter.
# Not married to Python: replace this file with {action}.sh / {action}.js /
# {action}.ps1 / {action}.cmd (same name, any supported extension), or point
# .graphify/config.json {{"{action}": "<path>"}} at any script/binary.
# Contract: mirror $GRAPHIFY_STORE_DIR {arrow} your backend under $GRAPHIFY_PREFIX;
# exit non-zero on failure. Credentials come from the environment (env vars,
# ~/.aws, ...) — never commit secrets.
"""

_COMMON = '''
import os, pathlib

ACTION = os.environ["GRAPHIFY_ACTION"]
STORE  = pathlib.Path(os.environ["GRAPHIFY_STORE_DIR"])   # <store>/<repo>/<branch>
PREFIX = os.environ["GRAPHIFY_PREFIX"]                      # <repo>/<branch>
BUCKET = os.environ.get("GRAPHIFY_BUCKET", "graphify-graphs")
ENDPOINT = os.environ.get("GRAPHIFY_S3_ENDPOINT")           # e.g. http://127.0.0.1:9000 for MinIO

def client():
    import boto3
    return boto3.client("s3", endpoint_url=ENDPOINT or None)  # creds from env / ~/.aws

def skip(rel):  # the AST cache is a local accelerator, not shared
    return "/cache/" in f"/{rel}"
'''

PUSH_S3 = _HEADER.format(action="push", arrow="->") + _COMMON + '''
def main():
    c = client()
    n = 0
    for f in STORE.rglob("*"):
        if f.is_file():
            rel = f.relative_to(STORE).as_posix()   # e.g. services/api/graphify-out/graph.json
            if skip(rel):
                continue
            c.upload_file(str(f), BUCKET, f"{PREFIX}/{rel}")
            n += 1
    print(f"pushed {n} file(s) -> s3://{BUCKET}/{PREFIX}/")

main()
'''

PULL_S3 = _HEADER.format(action="pull", arrow="<-") + _COMMON + '''
def main():
    c = client()
    token, n = None, 0
    while True:
        kw = {"Bucket": BUCKET, "Prefix": PREFIX + "/"}
        if token:
            kw["ContinuationToken"] = token
        resp = c.list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            rel = o["Key"][len(PREFIX) + 1:]        # services/api/graphify-out/graph.json
            if not rel or skip(rel):
                continue
            dest = STORE / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            c.download_file(BUCKET, o["Key"], str(dest))
            n += 1
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    print(f"pulled {n} file(s) <- s3://{BUCKET}/{PREFIX}/")

main()
'''
