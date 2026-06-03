"""Local embedding pass — exhaustive `semantically_similar_to` edges, no API cost (#7).

This module adds `semantically_similar_to` edges across all graph nodes using a
local, CPU-only embedding model (EmbeddingGemma via ONNX Runtime + Hugging Face)
instead of an LLM call. The LLM semantic pass finds the *interesting* cross-cutting
edges during extraction; this pass finds the *exhaustive* ones for free.

The heavy dependencies (`onnxruntime`, `huggingface_hub`, `tokenizers`, `numpy`)
are lazy-imported so a normal install / no-flag run never pays for them. Install
them with `pip install graphifyy[embeddings]`.

The single entry point is `embed_graph(G, ...)`, used by both `graphify extract
--embeddings` and the standalone `graphify embed` subcommand. A `_embedder` test
seam lets CI exercise the edge/cache logic with deterministic fake vectors, with
neither a model download nor onnxruntime installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable, Sequence

DEFAULT_MODEL_REPO = "onnx-community/embeddinggemma-300m-ONNX"
DEFAULT_THRESHOLD = 0.82
DEFAULT_QUANT = "q4"
VALID_QUANTS = ("q4", "q8", "fp16", "fp32")
# EmbeddingGemma's max sequence length. Node text is truncated to this before
# inference so an over-long summary can't blow up the model.
MAX_TOKENS = 2048
# Cosine is computed in row-blocks of this many nodes so peak RAM stays flat
# instead of materializing the full N×N similarity matrix.
_SIM_BLOCK = 512
# Above this many embeddable nodes the full pairwise scan gets expensive; warn
# and suggest --embed-top-k rather than silently churning.
_LARGE_GRAPH_WARN = 50_000

_MISSING_DEPS_MSG = (
    "embeddings require the [embeddings] extra — pip install graphifyy[embeddings]"
)


def _node_text(node: dict) -> str:
    """Build the text we embed for a node.

    `label` plus whatever structured context is available. By the time this pass
    runs every node is already text (image/video nodes were converted to text
    descriptions during semantic extraction), so a text-only signal is sufficient.
    """
    parts: list[str] = []
    label = node.get("label")
    if label:
        parts.append(str(label))
    for key in ("qualified_name", "signature", "summary", "description"):
        val = node.get(key)
        if val and str(val).strip():
            parts.append(str(val).strip())
    return "\n".join(parts).strip()


def _content_hash(text: str, model_repo: str, quant: str, dim: int | None) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"\x00")
    h.update(model_repo.encode("utf-8"))
    h.update(b"\x00")
    h.update(quant.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(dim).encode("utf-8"))
    return h.hexdigest()


def _load_cache(cache_path: Path | None, model_repo: str, quant: str, dim: int | None) -> dict:
    """Load embeddings.json. Invalidate wholesale if model/quant/dim drifted so we
    never mix vector spaces."""
    if cache_path is None or not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if (
        data.get("model") != model_repo
        or data.get("quant") != quant
        or data.get("dim") != dim
    ):
        return {}
    nodes = data.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _save_cache(
    cache_path: Path,
    model_repo: str,
    quant: str,
    dim: int | None,
    nodes: dict,
) -> None:
    """Atomic write (mkstemp + os.replace), mirroring cache.save_cached."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model_repo, "quant": quant, "dim": dim, "nodes": nodes}
    fd, tmp = tempfile.mkstemp(dir=cache_path.parent, prefix="embeddings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, cache_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _l2_normalize(vec, np):
    """L2-normalize a 1-D vector; return None for a zero/degenerate vector so the
    caller can skip it (no divide-by-zero / NaN)."""
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0 or not np.isfinite(norm):
        return None
    return arr / norm


class _OnnxEmbedder:
    """EmbeddingGemma via ONNX Runtime. Constructed lazily and only when no test
    seam is injected, so importing this module costs nothing."""

    def __init__(self, model_repo: str, quant: str):
        try:
            import numpy as np  # noqa: F401
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
            raise RuntimeError(_MISSING_DEPS_MSG) from exc

        try:
            model_file = hf_hub_download(model_repo, f"onnx/model_{quant}.onnx")
            try:
                hf_hub_download(model_repo, f"onnx/model_{quant}.onnx_data")
            except Exception:
                # Quantized variants are usually self-contained (no external
                # weights sidecar); ignore when absent.
                pass
            tok_file = hf_hub_download(model_repo, "tokenizer.json")
        except Exception as exc:
            raise RuntimeError(
                f"could not fetch embedding model '{model_repo}' ({quant}): {exc}. "
                f"If you are offline, pre-cache the model or unset HF_HUB_OFFLINE."
            ) from exc

        self._tok = Tokenizer.from_file(tok_file)
        self._tok.enable_truncation(max_length=MAX_TOKENS)
        self._sess = ort.InferenceSession(model_file, providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self._sess.get_inputs()}

    def __call__(self, texts: Sequence[str]):
        import numpy as np

        encs = self._tok.encode_batch(list(texts))
        max_len = max((len(e.ids) for e in encs), default=1) or 1
        ids = np.zeros((len(encs), max_len), dtype=np.int64)
        mask = np.zeros((len(encs), max_len), dtype=np.int64)
        for r, e in enumerate(encs):
            n = len(e.ids)
            ids[r, :n] = e.ids
            mask[r, :n] = e.attention_mask
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        feeds = {k: v for k, v in feeds.items() if k in self._input_names}
        outputs = self._sess.run(None, feeds)
        out_names = [o.name for o in self._sess.get_outputs()]
        pooled = None
        for name, arr in zip(out_names, outputs):
            if "sentence_embedding" in name or arr.ndim == 2:
                pooled = arr
                break
        if pooled is None:
            # Mean-pool the last hidden state over the attention mask.
            hidden = outputs[0]
            m = mask[:, :, None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
        return np.asarray(pooled, dtype=np.float32)


def embed_graph(
    G,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    model_repo: str = DEFAULT_MODEL_REPO,
    quant: str = DEFAULT_QUANT,
    dim: int | None = None,
    top_k: int | None = None,
    batch_size: int = 32,
    cache_path: Path | None = None,
    progress: Callable[[str], None] | None = None,
    _embedder: Callable[[Sequence[str]], object] | None = None,
) -> int:
    """Add `semantically_similar_to` edges to G from local embedding similarity.

    Returns the number of edges added. Idempotent: re-running on an unchanged
    graph adds zero vectors and zero edges (content-hash cache + has_edge guard).

    `_embedder` is a test seam — a callable(list[str]) -> 2-D array of row vectors.
    When omitted, the EmbeddingGemma ONNX embedder is built lazily (and raises a
    clean RuntimeError if the [embeddings] extra is not installed).
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(_MISSING_DEPS_MSG) from exc

    # Collect embeddable nodes in a deterministic (sorted-by-id) order.
    items: list[tuple[str, str]] = []  # (node_id, text)
    for node_id in sorted(G.nodes()):
        text = _node_text(G.nodes[node_id])
        if text:
            items.append((str(node_id), text))

    if len(items) < 2:
        return 0

    if len(items) > _LARGE_GRAPH_WARN and top_k is None and progress:
        progress(
            f"warning: {len(items)} embeddable nodes — the pairwise scan may be slow; "
            f"consider --embed-top-k to cap fan-out."
        )

    cache_nodes = _load_cache(cache_path, model_repo, quant, dim)

    # Figure out which nodes need fresh embedding (new or content-changed).
    hashes = {nid: _content_hash(text, model_repo, quant, dim) for nid, text in items}
    vectors: dict[str, object] = {}
    to_embed: list[tuple[str, str]] = []
    for nid, text in items:
        cached = cache_nodes.get(nid)
        if cached and cached.get("hash") == hashes[nid] and cached.get("vec"):
            v = _l2_normalize(cached["vec"], np)
            if v is not None:
                vectors[nid] = v
                continue
        to_embed.append((nid, text))

    if to_embed:
        embedder = _embedder if _embedder is not None else _OnnxEmbedder(model_repo, quant)
        if progress:
            progress(f"embedding {len(to_embed)} nodes ({len(items) - len(to_embed)} cached)")
        for start in range(0, len(to_embed), batch_size):
            batch = to_embed[start : start + batch_size]
            raw = np.asarray(embedder([t for _, t in batch]), dtype=np.float32)
            for (nid, _text), row in zip(batch, raw):
                truncated = row[:dim] if dim is not None else row
                v = _l2_normalize(truncated, np)
                if v is not None:
                    vectors[nid] = v

    # Persist the cache (only when a path was given). Store the normalized vector.
    if cache_path is not None:
        new_cache_nodes = {
            nid: {"hash": hashes[nid], "vec": [round(float(x), 6) for x in vectors[nid].tolist()]}
            for nid in vectors
        }
        try:
            _save_cache(cache_path, model_repo, quant, dim, new_cache_nodes)
        except Exception as exc:  # pragma: no cover - best-effort cache write
            if progress:
                progress(f"warning: could not write embeddings cache: {exc}")

    ids = [nid for nid, _ in items if nid in vectors]
    if len(ids) < 2:
        return 0
    matrix = np.stack([vectors[nid] for nid in ids]).astype(np.float32)

    return _add_similarity_edges(
        G, ids, matrix, np, threshold=threshold, top_k=top_k
    )


def _add_similarity_edges(G, ids, matrix, np, *, threshold, top_k) -> int:
    """Block-wise cosine threshold + edge insertion. Rows are already L2-normalized
    so cosine is a plain dot product. Never materializes the full N×N matrix."""
    n = len(ids)
    added = 0
    directed = G.is_directed()
    for start in range(0, n, _SIM_BLOCK):
        end = min(start + _SIM_BLOCK, n)
        sims = matrix[start:end] @ matrix.T  # (block, n)
        for local_i, global_i in enumerate(range(start, end)):
            row = sims[local_i]
            u = ids[global_i]
            # Candidate j with cos >= threshold, excluding self.
            cand = [
                (ids[j], float(row[j]))
                for j in range(n)
                if j != global_i and row[j] >= threshold
            ]
            if not cand:
                continue
            # Deterministic order: highest similarity first, then id.
            cand.sort(key=lambda t: (-t[1], t[0]))
            if top_k is not None:
                cand = cand[:top_k]
            for v, cos in cand:
                # Skip when an edge already exists — never clobber a real
                # calls/implements edge's attrs, and don't duplicate an existing
                # similarity edge. For undirected graphs has_edge is symmetric;
                # for digraphs check both directions so we add a single edge.
                if G.has_edge(u, v) or (directed and G.has_edge(v, u)):
                    continue
                score = round(cos, 4)
                G.add_edge(
                    u,
                    v,
                    relation="semantically_similar_to",
                    confidence="INFERRED",
                    confidence_score=score,
                    weight=score,
                    _src=u,
                    _tgt=v,
                )
                added += 1
    return added
