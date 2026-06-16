"""Token counting utilities."""
from __future__ import annotations

_FILE_CHAR_CAP = 20_000
_PER_FILE_OVERHEAD_CHARS = 160
_CHARS_PER_TOKEN = 4


def _get_tokenizer():
    """Return a tiktoken encoder for accurate token counts, or None if tiktoken
    is not installed. We use `cl100k_base` (GPT-4 / GPT-3.5-turbo) as a proxy."""
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


_TOKENIZER = _get_tokenizer()


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken or heuristic."""
    if _TOKENIZER:
        return len(_TOKENIZER.encode(text))
    return len(text) // _CHARS_PER_TOKEN


def estimate_file_tokens(content: str) -> int:
    """Estimate tokens for a file with overhead."""
    capped = content[:_FILE_CHAR_CAP]
    return count_tokens(capped) + (_PER_FILE_OVERHEAD_CHARS // _CHARS_PER_TOKEN)
