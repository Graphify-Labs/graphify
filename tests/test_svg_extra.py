"""SVG export should point at the svg extra, not a bare matplotlib install."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from graphify.export import to_svg


def test_to_svg_import_error_recommends_the_svg_extra(tmp_path: Path):
    """A missing matplotlib must hint at the svg extra, not a bare matplotlib install."""
    G = nx.Graph()
    G.add_node("a")
    blocked = {
        "matplotlib": None,
        "matplotlib.pyplot": None,
        "matplotlib.patches": None,
    }
    with patch.dict("sys.modules", blocked):
        with pytest.raises(ImportError) as exc_info:
            to_svg(G, {0: ["a"]}, str(tmp_path / "graph.svg"))
    msg = str(exc_info.value)
    assert 'pip install "graphifyy[svg]"' in msg
    assert "pip install matplotlib" not in msg
