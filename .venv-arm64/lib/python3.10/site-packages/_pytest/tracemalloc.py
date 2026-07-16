from __future__ import annotations


def tracemalloc_message(source: object) -> str:
    if source is None:
        return ""

    try:
        import tracemalloc
    except ImportError:
        return ""

    tb = tracemalloc.get_object_traceback(source)
    if tb is not None:
        formatted_tb = "\n".join(tb.format())
        # Use a leading new line to better separate the (large) output
        # from the traceback to the previous warning text.
        return f"\nObject allocated at:\n{formatted_tb}"
    # No need for a leading new line.
    url = "https://docs.pytest.org/en/stable/how-to/capture-warnings.html#resource-warnings"
    return (
        "Enable tracemalloc to get traceback where the object was allocated.\n"
        f"See {url} for more info."
    )
