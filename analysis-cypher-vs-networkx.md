# 分析函数双链路：NeuG Cypher vs NetworkX

graphify 的三个图分析功能（god nodes、cohesion、surprising connections）各有两套实现：NetworkX 原版和 NeuG Cypher 版。当 NeuG 可用时走 Cypher 路径，否则 fallback 到 NetworkX。本文详细说明两者的实现差异和 Cypher 映射方式。

---

## 1. God Nodes（核心枢纽节点）

### 功能定义

找出图中度数（degree）最高的"真实"实体节点。排除文件级 hub、概念节点、JSON key 噪声、内置类型噪声。

### NetworkX 原版（`analyze.py:god_nodes`）

```python
degree = dict(G.degree())                          # 无向图度数
sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)
for node_id, deg in sorted_nodes:
    if _is_file_node(G, node_id):        continue  # 排除文件 hub
    if _is_concept_node(G, node_id):     continue  # 排除概念节点
    if _is_json_key_node(G, node_id):    continue  # 排除 JSON key 噪声
    if label in _BUILTIN_NOISE_LABELS:   continue  # 排除内置类型
    result.append({"id": node_id, "label": label, "degree": deg})
```

- `G.degree()` 返回无向度数（in + out）
- 过滤逻辑通过访问 `G.nodes[node_id]` 的属性判断

### NeuG Cypher 版（`storage.py:god_nodes_cypher`）

**Cypher 查询**：

```cypher
MATCH (n:node)-[e]-(m:node)
RETURN n.id, n.label, n.source_file, count(e) AS deg
ORDER BY deg DESC
```

- `-[e]-` 是无向匹配（双向），等价于 NetworkX 的 `G.degree()`
- `count(e)` 计算每条边的出现次数
- `ORDER BY deg DESC` 在数据库层排序，避免 Python 层全量排序

**Python 后处理过滤**：

Cypher 返回所有节点的度数后，Python 侧逐行应用与 NetworkX 版完全相同的过滤逻辑：

```python
for row in rows:
    nid, label, source_file, deg = row[0], row[1] or "", row[2] or "", row[3]
    if _is_file_node_row(label, source_file, deg):   continue
    if _is_concept_node_row(source_file):             continue
    if _is_json_key_node_row(label, source_file):     continue
    if label in _GOD_NODE_NOISE_LABELS:               continue
    result.append({"id": nid, "label": label, "degree": deg})
    if len(result) >= top_n:  break
```

过滤函数 `_is_file_node_row`、`_is_concept_node_row`、`_is_json_key_node_row` 是 NetworkX 版的"扁平 row"镜像——逻辑完全一致，只是从 dict 属性访问改为参数传递。

### 差异点

| 维度 | NetworkX | NeuG Cypher |
|---|---|---|
| 度数计算 | `G.degree()` 内存计算 | `MATCH (n)-[e]-(m) RETURN count(e)` 数据库计算 |
| 排序 | Python `sorted()` | `ORDER BY deg DESC` 数据库排序 |
| 过滤 | 访问 `G.nodes[id]` 属性 | 从 Cypher row 提取字段，Python 侧过滤 |
| 提前终止 | Python `break` | Python `break`（Cypher 已排序，取前 N 即可） |
| 噪声标签集 | `_BUILTIN_NOISE_LABELS` | `_GOD_NODE_NOISE_LABELS`（内容一致，独立定义避免循环导入） |

---

## 2. Cohesion（社区内聚度）

### 功能定义

每个社区的内聚度 = 社区内实际边数 / 最大可能边数。值域 [0, 1]，1 表示完全图。

### NetworkX 原版（`cluster.py:cohesion_score` + `score_all`）

```python
def cohesion_score(G, community_nodes):
    n = len(community_nodes)
    if n <= 1:
        return 1.0
    subgraph = G.subgraph(community_nodes)       # 诱导子图
    actual = subgraph.number_of_edges()          # 子图边数
    possible = n * (n - 1) / 2                   # 完全图边数
    return actual / possible if possible > 0 else 0.0

def score_all(G, communities):
    return {cid: cohesion_score(G, nodes) for cid, nodes in communities.items()}
```

- `G.subgraph(nodes)` 创建社区节点的诱导子图（内存操作）
- `number_of_edges()` 统计子图中的边数
- NetworkX Graph 是无向的，`a→b` 和 `b→a` 自动合并为一条边

### NeuG Cypher 版（`storage.py:cohesion_cypher`）

**策略**：不做逐社区查询（避免 N 次 parameterized IN 查询），而是一次全扫所有边，在 Python 侧按社区归类。

**Cypher 查询**：

```cypher
MATCH (a:node)-[e:edge]->(b:node) RETURN a.id, b.id
```

- `-[e:edge]->` 是有向匹配（NeuG REL TABLE 是有向的）
- 一次查询返回所有边，Python 侧迭代处理

**Python 后处理**：

```python
node_comm = {n: cid for cid, nodes in communities.items() for n in nodes}
intra = {cid: set() for cid in communities}       # 每社区一个 set

for row in conn.execute("MATCH (a:node)-[e:edge]->(b:node) RETURN a.id, b.id"):
    a, b = row[0], row[1]
    if a == b: continue                            # 跳过自环
    ca = node_comm.get(a)
    if ca is not None and ca == node_comm.get(b):  # 两端在同一社区
        intra[ca].add(frozenset((a, b)))           # frozenset 去重有向边

# 计算每个社区的 cohesion
for cid, nodes in communities.items():
    n = len(nodes)
    possible = n * (n - 1) / 2
    result[cid] = len(intra[cid]) / possible       # 无向边数 / 最大可能边数
```

**关键设计**：`frozenset((a, b))` 把有向边 `(a, b)` 和 `(b, a)` 合并为同一条无向边，对齐 NetworkX 的无向图语义。如果 `a→b` 和 `b→a` 都存在，`frozenset` 保证只计一次。

### 差异点

| 维度 | NetworkX | NeuG Cypher |
|---|---|---|
| 边的方向 | 无向（Graph 自动合并） | 有向查询 + `frozenset` 去重 |
| 查询次数 | 0（全部内存操作） | 1 次全量边扫描 |
| 子图构建 | `G.subgraph(nodes)` 诱导子图 | 无子图，全扫边 + Python 过滤 |
| 性能 | 依赖 NetworkX 内存图大小 | 依赖 NeuG 全量边扫描 + Python dict 查找 |
| 自环处理 | NetworkX Graph 默认不计 | Python 侧 `if a == b: continue` |

---

## 3. Surprising Connections（惊喜连接）

### 功能定义

找出跨文件的、非显而易见的实体间连接。按复合惊喜分数排序，返回 top N。

### NetworkX 原版（`analyze.py:surprising_connections` → `_cross_file_surprises`）

```python
# 1. 判断是否多文件语料
source_files = {data.get("source_file") for _, data in G.nodes(data=True) if data.get("source_file")}
is_multi_source = len(source_files) > 1

# 2. 多文件 → _cross_file_surprises；单文件 → _cross_community_surprises（betweenness）
if is_multi_source:
    return _cross_file_surprises(G, communities, top_n)
else:
    return _cross_community_surprises(G, communities, top_n)
```

`_cross_file_surprises` 的核心：
- 遍历所有边 `G.edges(data=True)`
- 过滤掉 imports/contains/method 关系（结构性边）
- 过滤掉概念节点、文件 hub 节点
- 过滤掉同源文件边
- 对每条候选边调用 `_surprise_score()` 计算分数

`_surprise_score` 的评分维度：

| 维度 | 加分 | 条件 |
|---|---|---|
| 置信度 | +3/+2/+1 | AMBIGUOUS / INFERRED / EXTRACTED |
| 跨文件类型 | +2 | code ↔ doc / code ↔ paper 等 |
| 跨顶层目录 | +2 | 不同 repo/目录 |
| 跨社区 | +1 | 两端在不同社区 |
| 语义相似 | ×1.5 | `relation == "semantically_similar_to"` |
| 边缘→hub | +1 | 一端度数 ≤ 2，另一端 ≥ 5 |

INFERRED 的 calls/uses 跨语言/跨 code-doc 时，抑制所有结构加分（resolver 污染）。

### NeuG Cypher 版（`storage.py:surprising_connections_cypher`）

**策略**：两步 Cypher 查询（节点属性 + 边数据），Python 侧完全复刻评分逻辑。

**Cypher 查询 1 — 节点属性**：

```cypher
MATCH (n:node) RETURN n.id, n.label, n.source_file
```

构建 `labels` 和 `sources` 两个 dict。

**Cypher 查询 2 — 边数据**：

```cypher
MATCH (a:node)-[e:edge]->(b:node) RETURN a.id, b.id, e.relation, e.confidence
```

构建 `edges` 列表和 `degrees` dict（同时统计出度和入度）。

**Python 后处理 — 评分**：

```python
def _score(u, v, relation, conf, u_source, v_source):
    # 与 analyze._surprise_score 完全一致的评分逻辑
    score = 0
    reasons = []
    conf_bonus = {"AMBIGUOUS": 3, "INFERRED": 2, "EXTRACTED": 1}.get(conf, 1)
    # ... 跨文件类型、跨目录、跨社区、语义相似、边缘→hub ...
    return score, reasons
```

**Python 后处理 — 过滤 + 排序**：

```python
for a, b, relation, conf in edges:
    if relation in ("imports", "imports_from", "contains", "method"):  continue
    if _is_concept_node_row(sa) or _is_concept_node_row(sb):            continue
    if _is_file_node_row(la, sa, da) or _is_file_node_row(lb, sb, db_): continue
    if not sa or not sb or sa == sb:                                    continue  # 同源跳过
    score, reasons = _score(a, b, relation, conf, sa, sb)
    candidates.append({...})

candidates.sort(key=lambda x: x["_score"], reverse=True)
return candidates[:top_n]
```

### 差异点

| 维度 | NetworkX | NeuG Cypher |
|---|---|---|
| 数据获取 | `G.edges(data=True)` 内存遍历 | 2 次 Cypher 查询（节点 + 边） |
| 度数计算 | `G.degree(n)` | Python 侧边遍历时累计 `degrees[a] += 1` |
| 多/单文件分流 | 多文件 → cross_file；单文件 → betweenness | **仅实现 cross_file 路径**，单文件返回 `[]` |
| 评分函数 | `_surprise_score(G, u, v, data, ...)` | `_score(u, v, relation, conf, ...)` — dict 版镜像 |
| 过滤函数 | `_is_file_node(G, id)` / `_is_concept_node(G, id)` | `_is_file_node_row(label, source, deg)` / `_is_concept_node_row(source)` |
| 辅助函数复用 | 直接调用 | `from .analyze import _file_category, _top_level_dir, _cross_language` |

**注意**：Cypher 版省略了单文件 betweenness 路径（`_cross_community_surprises`），因为 extract 场景几乎都是多文件语料。单文件场景会返回空列表。

---

## 4. 过滤函数对照表

三个分析函数共享以下过滤逻辑，NetworkX 版访问图属性，Cypher 版从 row 字段判断：

| 过滤器 | NetworkX 版 | Cypher 版 | 判断逻辑 |
|---|---|---|---|
| 文件 hub | `_is_file_node(G, id)` | `_is_file_node_row(label, source_file, deg)` | label == 文件名，或 `.method()` 桩，或 `func()` 且 deg ≤ 1 |
| 概念节点 | `_is_concept_node(G, id)` | `_is_concept_node_row(source_file)` | source_file 为空，或末尾段无扩展名 |
| JSON key 噪声 | `_is_json_key_node(G, id)` | `_is_json_key_node_row(label, source_file)` | source_file 以 .json 结尾且 label 在噪声集合中 |
| 内置类型 | `label in _BUILTIN_NOISE_LABELS` | `label in _GOD_NODE_NOISE_LABELS` | 同一集合，独立定义避免循环导入 |

---

## 5. 性能特征

| 维度 | NetworkX | NeuG Cypher |
|---|---|---|
| 前置条件 | 已构建 NetworkX 图 G（内存） | 已有 graph.db（磁盘） |
| God nodes | O(V+E) 内存遍历 | O(E) Cypher 扫描 + Python 过滤 |
| Cohesion | O(k × E_sub) 子图提取 | O(E) 全量边扫描 + O(E) Python 归类 |
| Surprises | O(E) 边遍历 + O(E) 评分 | O(V) + O(E) 两次 Cypher + O(E) Python 评分 |
| 内存开销 | NetworkX 图 + Python 临时结构 | Python dict/list（无 NetworkX 图） |
| 适用场景 | NeuG 不可用时的 fallback | NeuG 可用时的主路径 |

Cohesion 的 Cypher 版看似低效（全量扫描所有边），但实际上 NeuG 的 Cypher 引擎在 C++ 层执行，比 Python 的 `G.subgraph()` + `number_of_edges()` 快很多。且全量扫描只需一次，不随社区数量增长。

---

## 6. 涉及文件索引

| 文件 | 函数 | 职责 |
|---|---|---|
| `graphify/analyze.py` | `god_nodes()` | NetworkX god nodes |
| `graphify/analyze.py` | `surprising_connections()` / `_cross_file_surprises()` / `_surprise_score()` | NetworkX surprises |
| `graphify/analyze.py` | `_file_category()` / `_top_level_dir()` / `_cross_language()` | 共享辅助函数（Cypher 版也复用） |
| `graphify/cluster.py` | `cohesion_score()` / `score_all()` | NetworkX cohesion |
| `graphify/storage.py` | `god_nodes_cypher()` | NeuG god nodes |
| `graphify/storage.py` | `cohesion_cypher()` | NeuG cohesion |
| `graphify/storage.py` | `surprising_connections_cypher()` | NeuG surprises |
| `graphify/storage.py` | `_is_file_node_row()` / `_is_concept_node_row()` / `_is_json_key_node_row()` | Cypher 版过滤函数 |
| `graphify/storage.py` | `_GOD_NODE_NOISE_LABELS` / `_GOD_NODE_JSON_NOISE` | Cypher 版噪声集合 |
