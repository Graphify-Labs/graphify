# neug GDS Leiden + Cypher Analysis

## Context

neug clustered 路径目前是 TODO 占位（cli.py:2640-2661），输出空的 communities/cohesion/gods/surprises。
需要实现 5 个分析功能，全部在 neug db 上用 GDS Leiden + Cypher 完成，不依赖 NetworkX。

neug GDS Leiden API 参考：`test_incremental_community_workflow.py:76-110`
- `CALL project_graph('g', ['node'], {'[node, edge, node]': ''})`
- `INSTALL gds; LOAD gds;`
- `CALL leiden('g', {concurrency: 1}) YIELD node, community`

neug 不支持 edge betweenness centrality — 单源场景用跨社区边替代。

## Task 1: storage.py — `run_leiden(conn)` 函数

在 `storage.py` 末尾新增函数：

```python
def run_leiden(conn) -> dict[int, list[str]]:
    """Run neug GDS Leiden. Returns {community_id: [node_ids]}, re-indexed by size desc."""
```

实现要点：
- 先检查空图/无边图（退化为每节点一个社区）
- `CALL drop_projected_graph('g')` (try/except，可能不存在)
- `CALL project_graph('g', ['node'], {'[node, edge, node]': ''})`
- `INSTALL gds; LOAD gds;`
- `CALL leiden('g', {concurrency: 1}) YIELD node, community RETURN node.id, community`
- 收集 {cid: [node_ids]}，按 size desc + tuple(sorted(nodes)) 重排 ID（对齐 cluster.py:235 的稳定 ID 约定）

## Task 2: storage.py — `compute_cohesion` + `label_communities_by_hub`

### compute_cohesion(conn, communities) -> dict[int, float]

```python
def compute_cohesion(conn, communities: dict[int, list[str]]) -> dict[int, float]:
    """Per-community cohesion: internal edges / max possible. Requires community written to db."""
```

Cypher（每社区一次查询，用 community 属性）：
```cypher
MATCH (a:node)-[:edge]->(b:node)
WHERE a.community = $cid AND b.community = $cid
RETURN count(*)
```
公式：`actual / (n * (n-1) / 2)`，n<=1 时返回 1.0

### label_communities_by_hub(conn, communities) -> dict[int, str]

```python
def label_communities_by_hub(conn, communities: dict[int, list[str]]) -> dict[int, str]:
    """Name each community after its highest-degree member. Requires community written to db."""
```

单次 Cypher 查询所有社区：
```cypher
MATCH (n:node)
WHERE n.community IS NOT NULL
WITH n, n.community AS cid, size((n)-[:edge]-()) AS degree
ORDER BY cid, degree DESC, n.id ASC
WITH cid, collect(n)[0] AS hub
RETURN cid, hub.label
```
- label 以 `()` 结尾时去掉（对齐 cluster.py:107-108）
- 无节点的社区退化为 `f"Community {cid}"`

## Task 3: storage.py — `find_god_nodes(conn, top_n=10)`

```python
def find_god_nodes(conn, top_n: int = 10) -> list[dict]:
    """Top-N most-connected real entities. Cypher for degree + basic filter, Python for complex filter."""
```

从 `analyze.py` 导入常量：`_BUILTIN_NOISE_LABELS`, `_JSON_NOISE_LABELS`

Cypher 查询（获取候选节点 + 度 + 属性）：
```cypher
MATCH (n:node)-[e:edge]-()
WITH n, count(e) AS degree
WHERE degree > 0
  AND n.label IS NOT NULL AND n.label <> ''
  AND n.label NOT IN $noise
  AND NOT (n.label STARTS WITH '.' AND n.label ENDS WITH '()')
ORDER BY degree DESC, n.id ASC
LIMIT $limit
RETURN n.id, n.label, n.file_type, n.source_file, degree
```
`$limit = top_n * 5`（留余量给 Python 过滤）

Python 过滤（逐候选检查，直到收够 top_n）：
- file hub: `label == Path(source_file).name`（对齐 analyze.py:70-72）
- method stub degree<=1: `label.endswith("()") and degree <= 1`（对齐 analyze.py:78-79）
- concept node: `not source_file or "." not in Path(source_file).name`（对齐 analyze.py:165-172）
- JSON key node: `source_file.lower().endswith(".json") and label.strip().lower() in _JSON_NOISE_LABELS`

返回 `[{"id", "label", "degree"}]`

## Task 4: storage.py — `find_surprising_connections(conn, communities, top_n=5)`

```python
def find_surprising_connections(conn, communities: dict[int, list[str]], top_n: int = 5) -> list[dict]:
    """Cross-file or cross-community edges ranked by composite surprise score."""
```

从 `analyze.py` 导入：`_LANG_FAMILY`, `_cross_language`, `_file_category`, `_top_level_dir`

**步骤**：
1. Cypher 查 `count(DISTINCT source_file)` 判断多源/单源
2. 预查所有节点度（一次 Cypher，建 dict）
3. Cypher 取候选边（多源：跨文件；单源：跨社区），排除 structural relations
4. Python 过滤 concept/file-hub 节点 + 计算复合 surprise score

**多源 Cypher**：
```cypher
MATCH (a:node)-[e:edge]->(b:node)
WHERE a.source_file <> '' AND b.source_file <> ''
  AND a.source_file <> b.source_file
  AND e.relation NOT IN ['imports', 'imports_from', 'contains', 'method']
RETURN a.id, a.label, a.source_file, a.community,
       b.id, b.label, b.source_file, b.community,
       e.relation, e.confidence
```

**单源 Cypher**：
```cypher
MATCH (a:node)-[e:edge]->(b:node)
WHERE a.community IS NOT NULL AND b.community IS NOT NULL
  AND a.community <> b.community
  AND e.relation NOT IN ['imports', 'imports_from', 'contains', 'method']
RETURN a.id, a.label, a.source_file, a.community,
       b.id, b.label, b.source_file, b.community,
       e.relation, e.confidence
```

**复合 score（Python，对齐 analyze.py:194-265）**：
1. confidence bonus: AMBIGUOUS=3, INFERRED=2, EXTRACTED=1
2. cross file-type: +2 if cat_u != cat_v
3. cross-repo: +2 if top_level_dir(u) != top_level_dir(v)
4. cross-community: +1 if cid_u != cid_v
5. semantic similarity: score *= 1.5 if relation == "semantically_similar_to"
6. peripheral→hub: +1 if min(deg_u, deg_v) <= 2 and max(deg_u, deg_v) >= 5
7. `_suppress_structural` 标志：INFERRED calls/uses 跨语言或 code→doc 时，结构 bonus 归零

单源去重：按 community pair 去重（对齐 analyze.py:409-416）

## Task 5: cli.py — 接入 neug clustered 路径

替换 cli.py:2640-2661 的 TODO 占位代码。

**流程**：
```python
if _use_neug:
    # 1. Leiden
    from graphify.storage import (
        run_leiden as _run_leiden,
        ingest_communities as _ingest_comm,
        compute_cohesion as _cohesion,
        find_god_nodes as _find_gods,
        find_surprising_connections as _find_surprises,
        label_communities_by_hub as _label_by_hub,
    )
    communities = _run_leiden(_neug_conn)
    stages.mark("cluster")
    
    # 2. Write community IDs to db (batch UNWIND per community)
    _ingest_comm(_neug_conn, communities)
    
    # 3. Label communities by hub
    labels = _label_by_hub(_neug_conn, communities)
    
    # 4. Write community_name to db (per-community SET)
    for cid, name in labels.items():
        _neug_conn.execute(
            "MATCH (n:node {community: $cid}) SET n.community_name = $name",
            parameters={"cid": int(cid), "name": name}
        )
    
    # 5. Analysis
    cohesion = _cohesion(_neug_conn, communities)
    gods = _find_gods(_neug_conn)
    surprises = _find_surprises(_neug_conn, communities)
    stages.mark("analyze")
    
    # 6. Export graph.json (with community + community_name)
    _data = _export_to_json(_neug_conn, hyperedges=merged.get("hyperedges", []))
    graph_json_path.write_text(json.dumps(_data, indent=2), encoding="utf-8")
    stages.mark("export")
    
    # 7. Write .graphify_analysis.json
    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "tokens": {"input": merged["input_tokens"], "output": merged["output_tokens"]},
    }
    analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    
    # 8. Close db, global_merge, manifest, print summary (unchanged)
    _close_db(_neug_db, _neug_conn)
    ...
```

同时优化 `ingest_communities` — 从 per-node SET 改为 per-community UNWIND batch：
```python
# Before: N queries (one per node)
for nid in node_ids:
    conn.execute(f"MATCH (n:node) WHERE n.id = $nid SET n.community = {cid_int}", ...)

# After: C queries (one per community)
conn.execute(
    "UNWIND $ids AS nid MATCH (n:node {id: nid}) "
    f"SET n.community = {cid_int}" + (", n.community_name = $cname" if cname else ""),
    parameters={"ids": node_ids, "cname": cname}
)
```

## Task 6: test_storage.py — 新增测试

在 `tests/test_storage.py` 中新增：
- `test_run_leiden`：构建小图，跑 leiden，验证社区数量和大小
- `test_compute_cohesion`：已知社区结构，验证内聚度计算
- `test_find_god_nodes`：含噪声节点，验证过滤后 top-N
- `test_find_surprising_connections`：跨文件边，验证 score 排序
- `test_label_communities_by_hub`：多社区，验证每个社区以最高度节点命名

## Task 7: 验证

1. `graphify extract --no-cluster` — 验证 graph.json + graph.db 一致（点边数量）
2. `graphify extract`（clustered）— 验证：
   - graph.json 含 community + community_name 字段
   - .graphify_analysis.json 含 communities/cohesion/gods/surprises
   - community 数量和社区成员总数 = 节点总数
   - gods 不含 file hub / concept / noise label
3. 对比 neug 路径与 NetworkX 路径输出格式一致性（字段名、结构）
