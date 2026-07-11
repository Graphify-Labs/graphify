"""Starter push/pull hook bodies scaffolded by `graphify remote init --backend <name>`.

These are EXAMPLES, not graphify dependencies — a hook can be any executable and do
anything. graphify only runs `.graphify/push.*` / `pull.*` (see graphify.remote) and
hands it the store context in the environment:

    GRAPHIFY_ACTION     "push" | "pull"
    GRAPHIFY_STORE_DIR  the <store> tree to mirror (holds every module's graphify-out)
    GRAPHIFY_PREFIX     the store folder's basename (a natural object-key / path prefix)
    GRAPHIFY_CONFIG     path to .graphify/config.json (read your own extra keys)
    GRAPHIFY_STORE / GRAPHIFY_REPO_ROOT

The contract: mirror GRAPHIFY_STORE_DIR to/from your backend under GRAPHIFY_PREFIX,
exit non-zero on failure. Secrets come from the environment (env vars, ~/.aws, ~/.ssh)
— never from the repo.

Backends below (pick with `--backend`):
  s3         private S3/MinIO — authenticated read AND write (boto3)
  s3-public  public-read bucket — authenticated push, URL-only pull (readers need NO creds)
  git-lfs    a git repo with git-lfs — versioned graphs
  rsync      rsync / SSH / a mounted network share
"""

# --------------------------------------------------------------- s3 (private)
_HEADER = """#!/usr/bin/env -S uv run --with boto3 python3
# graphify {action} hook (scaffolded by `graphify remote init`) — private S3/MinIO.
# Contract: mirror $GRAPHIFY_STORE_DIR {arrow} your backend under $GRAPHIFY_PREFIX.
# Credentials come from the environment (env vars, ~/.aws) — never commit secrets.
"""

_COMMON = '''
import os, pathlib

ACTION = os.environ["GRAPHIFY_ACTION"]
STORE  = pathlib.Path(os.environ["GRAPHIFY_STORE_DIR"])   # the <store> tree
PREFIX = os.environ["GRAPHIFY_PREFIX"]                      # store folder basename
BUCKET = os.environ.get("GRAPHIFY_BUCKET", "graphify-graphs")
ENDPOINT = os.environ.get("GRAPHIFY_S3_ENDPOINT")          # e.g. http://127.0.0.1:9000 for MinIO

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
            rel = f.relative_to(STORE).as_posix()
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
            rel = o["Key"][len(PREFIX) + 1:]
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

# --------------------------------------------------------------- s3-public
PUSH_S3_PUBLIC = '''#!/usr/bin/env -S uv run --with boto3 python3
# graphify push hook — S3 PUBLIC-READ. Authenticated WRITE; readers pull with only a
# URL (see pull.py). One-time: give the bucket a policy allowing anonymous
# s3:GetObject, and put its public base URL in .graphify/config.json as "store_url".
# We also write _manifest.json so readers never need to LIST the bucket.
import os, json, boto3

STORE  = os.environ["GRAPHIFY_STORE_DIR"]
PREFIX = os.environ.get("GRAPHIFY_PREFIX", "").strip("/")
BUCKET = os.environ.get("GRAPHIFY_BUCKET", "graphify-graphs")
ENDPOINT = os.environ.get("GRAPHIFY_S3_ENDPOINT")
s3 = boto3.client("s3", endpoint_url=ENDPOINT or None)   # creds from env / ~/.aws
rels = []
for root, dirs, files in os.walk(STORE):
    dirs[:] = [d for d in dirs if d != "cache"]
    for f in files:
        p = os.path.join(root, f); rel = os.path.relpath(p, STORE)
        s3.upload_file(p, BUCKET, f"{PREFIX}/{rel}" if PREFIX else rel); rels.append(rel)
key = f"{PREFIX}/_manifest.json" if PREFIX else "_manifest.json"
s3.put_object(Bucket=BUCKET, Key=key,
              Body=json.dumps({"files": sorted(rels)}).encode(), ContentType="application/json")
print(f"pushed {len(rels)} file(s) + manifest -> s3://{BUCKET}/{PREFIX}/  (public-read)")
'''

PULL_S3_PUBLIC = '''#!/usr/bin/env python3
# graphify pull hook — URL-ONLY, no creds, no SDK (stdlib). Reads "store_url" (the
# public base URL) from .graphify/config.json, GETs _manifest.json, then GETs each file.
import os, sys, json, pathlib, urllib.request

def cfg(k):
    p = os.environ.get("GRAPHIFY_CONFIG")
    try:
        return json.load(open(p)).get(k) if p else None
    except Exception:
        return None

url = (os.environ.get("GRAPHIFY_STORE_URL") or cfg("store_url") or "").rstrip("/")
if not url:
    sys.exit('pull: set "store_url": "<public base URL>" in .graphify/config.json')
PREFIX = os.environ.get("GRAPHIFY_PREFIX", "").strip("/")
STORE = os.environ["GRAPHIFY_STORE_DIR"]
base = f"{url}/{PREFIX}" if PREFIX else url

def get(u):
    return urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "graphify-pull"}), timeout=60).read()

man = json.loads(get(f"{base}/_manifest.json"))
n = 0
for rel in man.get("files", []):
    dest = pathlib.Path(STORE) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(get(f"{base}/{rel}"))
    n += 1
print(f"pulled {n} file(s) <- {base}/  (URL-only, no creds)")
'''

# --------------------------------------------------------------- git-lfs
PUSH_GITLFS = '''#!/usr/bin/env bash
# graphify push hook — a git repo with git-lfs (versioned graphs).
# Set GRAPHIFY_GIT_REMOTE to the store repo URL (e.g. git@github.com:you/graph-store.git).
set -euo pipefail
REMOTE="${GRAPHIFY_GIT_REMOTE:?set GRAPHIFY_GIT_REMOTE to the store git repo URL}"
WORK="${GRAPHIFY_GIT_WORK:-$HOME/.cache/graphify-store-git}"
if [ ! -d "$WORK/.git" ]; then
  git clone "$REMOTE" "$WORK" 2>/dev/null || { mkdir -p "$WORK"; git -C "$WORK" init -q; git -C "$WORK" remote add origin "$REMOTE"; }
fi
git -C "$WORK" lfs install --local >/dev/null 2>&1 || true
printf '* filter=lfs diff=lfs merge=lfs -text\\n.gitattributes -filter\\n' > "$WORK/.gitattributes"
rsync -a --delete --exclude '.git' --exclude '*/cache/*' "$GRAPHIFY_STORE_DIR/" "$WORK/$GRAPHIFY_PREFIX/"
git -C "$WORK" add -A
git -C "$WORK" commit -qm "graphify store update" 2>/dev/null || { echo "push: nothing changed"; exit 0; }
git -C "$WORK" push -u origin HEAD 2>&1 | tail -1
echo "push: mirrored store -> $REMOTE (git-lfs)"
'''

PULL_GITLFS = '''#!/usr/bin/env bash
# graphify pull hook — git-lfs. See push.sh for GRAPHIFY_GIT_REMOTE.
set -euo pipefail
REMOTE="${GRAPHIFY_GIT_REMOTE:?set GRAPHIFY_GIT_REMOTE to the store git repo URL}"
WORK="${GRAPHIFY_GIT_WORK:-$HOME/.cache/graphify-store-git}"
if [ -d "$WORK/.git" ]; then git -C "$WORK" pull -q; else git clone "$REMOTE" "$WORK"; fi
mkdir -p "$GRAPHIFY_STORE_DIR"
rsync -a --exclude '.git' "$WORK/$GRAPHIFY_PREFIX/" "$GRAPHIFY_STORE_DIR/"
echo "pull: mirrored $REMOTE -> store (git-lfs)"
'''

# --------------------------------------------------------------- rsync / share
PUSH_RSYNC = '''#!/usr/bin/env bash
# graphify push hook — rsync to SSH or a mounted share (NFS/Dropbox/…).
# Set GRAPHIFY_RSYNC_DEST, e.g. user@host:/srv/graphify  or  /mnt/share/graphify.
# (If the store already lives on a shared drive, you don't need push/pull at all.)
set -euo pipefail
DEST="${GRAPHIFY_RSYNC_DEST:?set GRAPHIFY_RSYNC_DEST (user@host:/path or /shared/path)}"
rsync -a --delete --exclude '*/cache/*' "$GRAPHIFY_STORE_DIR/" "$DEST/$GRAPHIFY_PREFIX/"
echo "push: rsynced store -> $DEST/$GRAPHIFY_PREFIX/"
'''

PULL_RSYNC = '''#!/usr/bin/env bash
# graphify pull hook — rsync. See push.sh for GRAPHIFY_RSYNC_DEST.
set -euo pipefail
DEST="${GRAPHIFY_RSYNC_DEST:?set GRAPHIFY_RSYNC_DEST (user@host:/path or /shared/path)}"
mkdir -p "$GRAPHIFY_STORE_DIR"
rsync -a "$DEST/$GRAPHIFY_PREFIX/" "$GRAPHIFY_STORE_DIR/"
echo "pull: rsynced $DEST/$GRAPHIFY_PREFIX/ -> store"
'''

# --------------------------------------------------------------- registry
# name -> {desc, push: (ext, body), pull: (ext, body), config: extra config.json keys}
TEMPLATES = {
    "s3": {
        "desc": "private S3/MinIO — authenticated read AND write (boto3)",
        "push": (".py", PUSH_S3), "pull": (".py", PULL_S3),
    },
    "s3-public": {
        "desc": "public-read S3 — authenticated push, URL-only pull (readers need NO creds)",
        "push": (".py", PUSH_S3_PUBLIC), "pull": (".py", PULL_S3_PUBLIC),
        "config": {"store_url": "https://<bucket>.<endpoint>  # public base URL, safe to commit"},
    },
    "git-lfs": {
        "desc": "a git repo with git-lfs (set GRAPHIFY_GIT_REMOTE)",
        "push": (".sh", PUSH_GITLFS), "pull": (".sh", PULL_GITLFS),
    },
    "rsync": {
        "desc": "rsync / SSH / a mounted network share (set GRAPHIFY_RSYNC_DEST)",
        "push": (".sh", PUSH_RSYNC), "pull": (".sh", PULL_RSYNC),
    },
}
DEFAULT_BACKEND = "s3"
