"""
Jev 增强型代码影响面分析器 (Jev-Enhanced Blast Radius Analyzer for Graphify)

实现进化 2：全自动变更影响面分析。
针对开发者提问的函数或符号，在 Graphify 拓扑图谱中进行反向有向边追踪（Predecessors），
直观列出所有直接与间接波及的上游调用方（Callers/Imports）。
"""
from __future__ import annotations
import os
import networkx as nx
from typing import Dict, List, Any, Optional

from graphify.jev_bridge import _call_jev_choice, is_available


def analyze_blast_radius(G: nx.Graph, symbol_query: str, max_depth: int = 2, active_graph_path: str | None = None) -> Dict[str, Any]:
    """
    全自动变更影响面分析（Blast Radius）。
    逆向有向边追踪（Predecessors），毫秒级列出所有会受影响的上游调用者。
    支持 project_path 作用域感知与 multi-project 隔离。
    """
    from graphify.jev_bridge import pick_seeds_with_jev

    # 1. 尝试找到目标起点符号
    matched_nid = None
    for nid in G.nodes():
        lbl = G.nodes[nid].get("label", "")
        if symbol_query.lower() in lbl.lower():
            matched_nid = nid
            break

    if not matched_nid and is_available():
        seeds = pick_seeds_with_jev(G, symbol_query, max_seeds=1, graph_path=active_graph_path)
        if seeds:
            matched_nid = seeds[0]

    if not matched_nid or matched_nid not in G:
        return {"error": f"在图谱中未找到与【{symbol_query}】匹配的代码符号"}

    target_data = G.nodes[matched_nid]
    target_label = target_data.get("label", matched_nid)
    target_file = target_data.get("source_file", "")

    # 2. 逆向有向边追踪（Predecessors 逆向 BFS）
    affected_nodes: Dict[int, list[str]] = {}
    visited = {matched_nid}
    current_layer = [matched_nid]

    for d in range(1, max_depth + 1):
        next_layer = []
        for n in current_layer:
            callers = list(G.predecessors(n)) if G.is_directed() else list(G.neighbors(n))
            for c in callers:
                if c not in visited:
                    visited.add(c)
                    next_layer.append(c)
                    affected_nodes.setdefault(d, []).append(c)
        current_layer = next_layer
        if not current_layer:
            break

    total_affected = sum(len(v) for v in affected_nodes.values())

    formatted_chains = []
    for depth_lvl, nids in affected_nodes.items():
        layer_items = []
        for nid in nids:
            nd = G.nodes[nid]
            lbl = nd.get("label", nid)
            sfile = os.path.basename(nd.get("source_file", ""))
            layer_items.append(f"{lbl} ({sfile})")
        formatted_chains.append({
            "depth": depth_lvl,
            "layer_name": "直接上游调用者 (1跳)" if depth_lvl == 1 else f"间接连锁波及者 ({depth_lvl}跳)",
            "affected": layer_items
        })

    return {
        "target_symbol": target_label,
        "target_file": target_file,
        "blast_radius_score": total_affected,
        "severity": "HIGH_RISK" if total_affected >= 5 else ("MODERATE_RISK" if total_affected >= 2 else "LOW_RISK"),
        "chains": formatted_chains
    }
