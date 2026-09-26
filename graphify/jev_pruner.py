"""
Jev 智能拓扑修枝扩展 (Jev-Guided Dynamic Subgraph Pruner)
解决原生 BFS 盲目扩散导致无关工具函数（日志、时间、基础IO）污染上下文并撑爆 Token 的痛点。
"""
from __future__ import annotations
import os
import networkx as nx
from typing import Dict, List, Set, Tuple

from graphify.jev_bridge import _call_jev_choice, is_available

# 常见纯工具/打杂类的噪音关键词
_NOISE_TERMS = frozenset({
    "logger", "logging", "log", "time", "datetime", "utc", "sleep",
    "print", "format", "json", "os", "sys", "path", "typing", "abc"
})

def prune_bfs_neighbors_with_jev(
    G: nx.Graph,
    current_node: str,
    raw_neighbors: list[str],
    question: str,
    max_keep: int = 5
) -> list[str]:
    """
    进化 1 实现：在 BFS 扩散时，让 Jev 快速给候选邻居做一次因果过滤，
    斩断无关的工具/日志分支，只保留与问题强相关的业务调用链。
    """
    if len(raw_neighbors) <= max_keep or not is_available():
        return raw_neighbors[:max_keep]

    # 构建每个邻居的摘要
    neighbor_options: Dict[str, str] = {}
    for nid in raw_neighbors:
        ndata = G.nodes[nid]
        lbl = ndata.get("label", nid)
        if lbl.startswith("rationale_"):
            continue
        sfile = os.path.basename(ndata.get("source_file", ""))
        doc = ndata.get("docstring") or lbl
        neighbor_options[nid] = f"[{sfile}] {doc}"

    if len(neighbor_options) <= max_keep:
        return list(neighbor_options.keys())

    # 优先使用启发式规则先过滤显而易见的纯噪音（如 logging、os 等）
    filtered_options = {}
    for nid, desc in neighbor_options.items():
        lbl_lower = G.nodes[nid].get("label", nid).lower()
        if not any(noise in lbl_lower for noise in _NOISE_TERMS):
            filtered_options[nid] = desc

    # 若过滤后太少，则回退全量候选项
    candidates_to_judge = filtered_options if len(filtered_options) >= 2 else neighbor_options

    curr_label = G.nodes[current_node].get("label", current_node)
    state = f"核心业务函数：{curr_label}\n开发者检索需求：【{question}】"
    instr = "在当前函数调用的下级依赖中，哪一个与开发者的核心诉求具有最直接的业务因果关系？（过滤掉纯辅助日志与通用工具）"

    res = _call_jev_choice(state, instr, candidates_to_judge)
    if res and res[0] in raw_neighbors:
        best_neighbor = res[0]
        # 严格防御：仅从传入的 raw_neighbors 候选集中挑选，防止幻觉 ID
        kept = [best_neighbor]
        for n in candidates_to_judge:
            if n in raw_neighbors and n != best_neighbor and len(kept) < max_keep:
                kept.append(n)
        return kept

    return raw_neighbors[:max_keep]
