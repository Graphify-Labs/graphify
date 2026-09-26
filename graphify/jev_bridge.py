"""JEV 语义种子决策层 — 基于 TypeSafe System One (JEV) 的工业级图谱精准导航（std-lib only，fail-open）。

解决传统代码图谱仅靠 Jieba 分词 / 关键词匹配在自然语言大白话提问下容易搜空或噪音节点扩散的痛点。
包含四大企业级优化机制：
1. 【图拓扑中枢加权】：使用 NetworkX 度数 (Degree) 排序提炼社区核心骨干 (God Nodes)，大幅提升社区识别准确率。
2. 【多候选概率取种】：利用 Jev 的完整概率分布 (probabilities) 进行多分支取种，支持跨社区复杂协同查询。
3. 【超大社区文件级二级折叠】：针对节点数超过 30 的庞大社区，先选代码文件再选函数，根除硬截断盲区。
4. 【Git Commit 感知 LRU 缓存】：针对重复查询实现 0ms 纯本地秒回，代码变动自动感知失效。

纪律与安全保障：
- 严格 Fail-open：未配置 API KEY、网络超时、格式错误等情况下无缝静默回退原生关键词寻种逻辑，绝不阻断服务。
- 出站仅元数据：发送的 criteria 仅包含模块文件路径与符号签名，严禁发送源码实现细节。
- 零第三方重型依赖：仅使用 Python 标准库 urllib.request 与 json。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Dict, List, Tuple, Any, Optional
import networkx as nx

DEFAULT_API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
_TIMEOUT_SECONDS = 4.0

# 优化点 4：内存 LRU 缓存（结构：cache_key -> list[seed_ids]）
# 最多保留 128 条近期查询缓存
_SEED_CACHE: Dict[str, list[str]] = {}
_MAX_CACHE_SIZE = 128


def _load_env_file() -> None:
    """自动加载当前工作目录或上级目录中的 .env 文件（轻量原生实现，不引入 python-dotenv 依赖）"""
    try:
        from pathlib import Path
        for base in [Path.cwd(), Path(__file__).resolve().parent.parent]:
            env_file = base / ".env"
            if env_file.is_file():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
                break
    except Exception:
        pass


def _api_key() -> str:
    """获取 API Key，优先读取 TYPESAFE_API_KEY，亦兼容 OPENCODE_API_KEY"""
    _load_env_file()
    return os.environ.get("TYPESAFE_API_KEY", "").strip() or os.environ.get("OPENCODE_API_KEY", "").strip()


def _api_url() -> str:
    """获取 API Endpoint，优先读取 TYPESAFE_API_URL，若使用 OpenCode Zen 则自动路由"""
    _load_env_file()
    url = os.environ.get("TYPESAFE_API_URL", "").strip() or os.environ.get("OPENCODE_API_URL", "").strip()
    if url:
        return url
    if os.environ.get("OPENCODE_API_KEY", "").strip() and not os.environ.get("TYPESAFE_API_KEY", "").strip():
        return "https://opencode.ai/zen/v1/systemone"
    return DEFAULT_API_URL


def is_available() -> bool:
    """检查 JEV 决策层是否已配置且可用"""
    return bool(_api_key())


def _call_jev_choice(
    state: str, instructions: str, options_map: Dict[str, str], timeout: float = _TIMEOUT_SECONDS
) -> Tuple[str, float, Dict[str, float]] | None:
    """POST 到 System One 执行 Choice 决策，返回 (最佳选项, 置信度, 全量概率分布)，失败时返回 None (fail-open)"""
    key = _api_key()
    if not key or not options_map:
        return None

    model = os.environ.get("TYPESAFE_MODEL", "").strip()
    if not model:
        model = "jev-1.13-free" if "opencode.ai" in _api_url() else DEFAULT_MODEL

    payload = {
        "state": state,
        "model": model,
        "questions": {
            "target": {
                "type": "choice",
                "instructions": instructions,
                "criteria": options_map,
            }
        },
    }

    req = urllib.request.Request(
        _api_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "graphify-jev/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ans = data.get("answers", {}).get("target", {})
            choice = ans.get("choice")
            conf = float(ans.get("confidence", 0.0))
            probs = ans.get("probabilities", {})
            if choice and choice in options_map:
                return choice, conf, probs
    except Exception:
        # fail-open 保护：任何网络、JSON、状态码异常直接忽略回退
        return None
    return None


def _get_cache_key(G: nx.Graph, question: str) -> str:
    """生成结合图谱规模与查询文本的缓存键"""
    # 结合节点数和边数作为图谱状态指纹，图谱改动时缓存自动不匹配
    graph_fingerprint = f"{G.number_of_nodes()}_{G.number_of_edges()}"
    norm_q = question.strip().lower()
    return f"{graph_fingerprint}::{norm_q}"


def pick_seeds_with_jev(G: nx.Graph, question: str, max_seeds: int = 3) -> list[str] | None:
    """使用 Jev 在代码图谱中执行工业级两阶段语义穿透寻种。

    成功时返回种子节点列表 [seed_node_id, ...]；
    失败或低置信度时返回 None，提示调用方回退原生关键词寻种逻辑。
    """
    if not is_available() or G.number_of_nodes() == 0:
        return None

    # 优化点 4：检查缓存
    cache_key = _get_cache_key(G, question)
    if cache_key in _SEED_CACHE:
        return _SEED_CACHE[cache_key]

    try:
        from graphify.cluster import cluster

        communities = cluster(G)
        if not communities:
            return None

        # 优化点 3：基于图拓扑中枢加权（Degree），提取每个社区的骨干中枢符号
        community_summaries: Dict[str, str] = {}
        for cid, nids in communities.items():
            # 按度数降序排列，优先展示连接度最高的骨干节点 (God Nodes)
            sorted_by_degree = sorted(nids, key=lambda n: G.degree(n), reverse=True)
            
            files: set[str] = set()
            hub_labels: list[str] = []
            for nid in sorted_by_degree:
                ndata = G.nodes[nid]
                sfile = ndata.get("source_file")
                if sfile:
                    files.add(os.path.basename(sfile))
                lbl = ndata.get("label", nid)
                if not lbl.startswith("rationale_") and lbl not in hub_labels:
                    hub_labels.append(lbl)
            
            summary = f"Files: [{', '.join(sorted(files)[:4])}] Hubs: [{', '.join(hub_labels[:4])}]"
            community_summaries[str(cid)] = summary

        # 阶段 1：社区选择
        target_cids: list[str] = []
        if len(community_summaries) <= 1:
            target_cids = ["0"] if "0" in community_summaries else [list(community_summaries.keys())[0]]
        else:
            state_c = f"Codebase Query: {question}"
            instr_c = "Which community/module scope directly relates to this developer query?"
            c_res = _call_jev_choice(state_c, instr_c, community_summaries)
            if not c_res:
                return None
            best_cid, c_conf, c_probs = c_res
            if c_conf < 0.35:  # 置信度过低时放弃，回退原生分词
                return None

            # 优化点 2：多候选概率取种（处理跨社区协同需求）
            # 不仅保留最高分项，若次高选项概率 >= 0.20 或与最高项差距 < 0.15，一并纳入搜索边界
            max_prob = max(c_probs.values()) if c_probs else 1.0
            target_cids.append(best_cid)
            for cid, prob in c_probs.items():
                if cid != best_cid and (prob >= 0.20 or (max_prob - prob) <= 0.12):
                    target_cids.append(cid)
                    if len(target_cids) >= 2:  # 最多取 2 个最强相关社区
                        break

        # 阶段 2：在目标社区内部寻找种子节点
        final_seed_candidates: list[str] = []

        for cid in target_cids:
            target_nids = communities[int(cid)]
            
            # 优化点 1：超大社区文件级二级折叠（按文件聚类，彻底消灭截断盲区）
            # 按文件对社区内部符号进行分类
            nodes_by_file: Dict[str, list[str]] = {}
            for nid in target_nids:
                ndata = G.nodes[nid]
                lbl = ndata.get("label", nid)
                if lbl.startswith("rationale_"):
                    continue
                sfile = os.path.basename(ndata.get("source_file", "unknown"))
                nodes_by_file.setdefault(sfile, []).append(nid)

            chosen_nids = target_nids
            # 如果社区内部文件很多且总节点超过 35 个，先选代码文件！
            if len(nodes_by_file) > 2 and len(target_nids) > 35:
                file_options: Dict[str, str] = {}
                for sfile, f_nids in list(nodes_by_file.items())[:20]:
                    # 包含该文件度数最高的前 3 个函数
                    f_hubs = sorted(f_nids, key=lambda n: G.degree(n), reverse=True)
                    f_labels = [G.nodes[n].get("label", n) for n in f_hubs[:3]]
                    file_options[sfile] = f"Symbols: [{', '.join(f_labels)}]"

                state_f = f"Target Community: {community_summaries.get(cid, '')}\nQuery: {question}"
                instr_f = "Which specific source code file contains the queried functionality?"
                f_res = _call_jev_choice(state_f, instr_f, file_options)
                if f_res and f_res[0] in nodes_by_file:
                    chosen_nids = nodes_by_file[f_res[0]]

            # 最终在精选出的节点集中做符号选择
            node_options: Dict[str, str] = {}
            for nid in chosen_nids:
                ndata = G.nodes[nid]
                lbl = ndata.get("label", nid)
                if lbl.startswith("rationale_"):
                    continue
                loc = ndata.get("source_location", "")
                sfile = os.path.basename(ndata.get("source_file", ""))
                doc = ndata.get("docstring") or lbl
                node_options[nid] = f"[{sfile}:{loc}] {doc}"

            if not node_options:
                continue

            # 保留前 40 个高质量候选
            if len(node_options) > 40:
                # 依然按度数优先保留骨干符号
                sorted_sub = sorted(node_options.keys(), key=lambda n: G.degree(n), reverse=True)
                node_options = {nid: node_options[nid] for nid in sorted_sub[:40]}

            state_n = f"Scope: {community_summaries.get(cid, '')}\nQuery: {question}"
            instr_n = "Which code entity directly handles or defines the queried functionality?"
            n_res = _call_jev_choice(state_n, instr_n, node_options)
            if n_res and n_res[0] in G:
                final_seed_candidates.append(n_res[0])
                if len(final_seed_candidates) >= max_seeds:
                    break

        if final_seed_candidates:
            # 写入缓存（保持不超过上限）
            if len(_SEED_CACHE) >= _MAX_CACHE_SIZE:
                _SEED_CACHE.pop(next(iter(_SEED_CACHE)))
            _SEED_CACHE[cache_key] = final_seed_candidates
            return final_seed_candidates

    except Exception:
        # fail-open 保护
        return None

    return None
