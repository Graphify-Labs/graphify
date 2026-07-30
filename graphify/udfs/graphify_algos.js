// graphify_algos — FalkorDB server-side UDF library.
//
// These replace the NetworkX algorithms graphify used to run in-process,
// for the ones FalkorDB has no built-in equivalent of:
//   - louvain          : community detection   (was graspologic Leiden / nx.community.louvain)
//   - edgeBetweenness  : edge betweenness       (was nx.edge_betweenness_centrality)
//   - simpleCycles     : directed simple cycles (was nx.simple_cycles)
//
// DESIGN: these are PURE-COMPUTE functions. They do NOT read the graph through
// the UDF graph API — that API (as of FalkorDB 4.18) does not expose edge
// endpoints via iterateEdges, and getNeighbors() ignores its direction config
// and never surfaces edge weights. Instead the Python GraphStore pulls the edge
// list (with weights) via ordinary Cypher and passes it in as an argument. That
// keeps weights/direction correct and makes these functions trivially testable.
//
// DETERMINISM: every function processes nodes/edges in a fixed sorted order and
// uses no randomness, so results are byte-stable across runs (graphify pins
// seed=42 everywhere; here we get the same guarantee from sorted iteration).
//
// Edge argument shape (all functions): an array of [u, v, w] triples, where u/v
// are node-id strings and w is an optional numeric weight (defaults to 1).

// ----------------------------------------------------------------------------
// louvain(edges, resolution) -> { nodeId: communityId(int) }
//
// Standard Louvain modularity maximization on the UNDIRECTED, WEIGHTED graph.
// Two-phase: (1) greedy local moving, (2) community aggregation, repeated until
// modularity stops improving. The returned community ids are arbitrary integers;
// the Python cluster() wrapper re-indexes them to size-stable ids.
//
// Node move order is the sorted node order (deterministic). Ties in modularity
// gain are broken toward the smallest community id, again for determinism.
// ----------------------------------------------------------------------------
function louvain(edges, resolution) {
  var gamma = (resolution === undefined || resolution === null) ? 1.0 : resolution;

  // Collect a sorted, de-duplicated node list -> integer index.
  var idSet = {};
  for (var i = 0; i < edges.length; i++) {
    idSet[edges[i][0]] = true;
    idSet[edges[i][1]] = true;
  }
  var ids = Object.keys(idSet).sort();
  var index = {};
  for (var n = 0; n < ids.length; n++) index[ids[n]] = n;
  var N = ids.length;
  if (N === 0) return {};

  // Build a weighted undirected adjacency as an aggregated edge map.
  // adj[i] = { j: weight } summed across parallel/both-direction edges.
  // Self-loops are kept (they contribute to a node's degree twice, as usual).
  var adj = new Array(N);
  for (var a = 0; a < N; a++) adj[a] = {};
  var totalW = 0.0;            // m  (sum of all edge weights, each undirected edge once)
  for (var e = 0; e < edges.length; e++) {
    var u = index[edges[e][0]];
    var v = index[edges[e][1]];
    var w = edges[e][2];
    if (w === undefined || w === null || isNaN(w)) w = 1.0;
    if (u === v) {
      adj[u][u] = (adj[u][u] || 0) + w;   // self-loop
      totalW += w;
      continue;
    }
    adj[u][v] = (adj[u][v] || 0) + w;
    adj[v][u] = (adj[v][u] || 0) + w;
    totalW += w;
  }
  if (totalW === 0) {
    // No edges: every node is its own community.
    var solo = {};
    for (var s = 0; s < N; s++) solo[ids[s]] = s;
    return solo;
  }

  // Weighted degree k_i for each node (self-loops count twice).
  function degrees(adjacency, count) {
    var k = new Array(count);
    for (var p = 0; p < count; p++) {
      var sum = 0.0;
      var row = adjacency[p];
      for (var q in row) {
        sum += (parseInt(q, 10) === p) ? 2 * row[q] : row[q];
      }
      k[p] = sum;
    }
    return k;
  }

  // One Louvain level: greedy local moving on `adjacency` (size `count`),
  // total weight `m`. Returns { comm: int[], improved: bool }.
  function oneLevel(adjacency, count, m) {
    var k = degrees(adjacency, count);
    var comm = new Array(count);
    var sigmaTot = new Array(count);   // total degree of community c
    for (var i = 0; i < count; i++) { comm[i] = i; sigmaTot[i] = k[i]; }
    var twoM = 2 * m;

    var improvedAny = false;
    var moved = true;
    var guard = 0;
    while (moved && guard < 100) {
      moved = false;
      guard++;
      for (var node = 0; node < count; node++) {
        var nodeComm = comm[node];
        // Weight from `node` into each neighboring community.
        var wToComm = {};
        var row = adjacency[node];
        var selfLoop = row[node] || 0;
        for (var nb in row) {
          var nbi = parseInt(nb, 10);
          if (nbi === node) continue;
          var c = comm[nbi];
          wToComm[c] = (wToComm[c] || 0) + row[nb];
        }
        // Remove node from its current community.
        sigmaTot[nodeComm] -= k[node];
        var wToOwn = wToComm[nodeComm] || 0;

        // Evaluate candidate communities: current + all neighbor communities.
        // Deterministic: consider community ids in ascending order.
        var candidates = {};
        candidates[nodeComm] = true;
        for (var cc in wToComm) candidates[cc] = true;
        var candList = Object.keys(candidates).map(function (x) { return parseInt(x, 10); }).sort(function (p, q) { return p - q; });

        var bestComm = nodeComm;
        // Gain of staying (relative baseline) — start from current community.
        var bestGain = wToOwn - gamma * sigmaTot[nodeComm] * k[node] / twoM;
        for (var ci = 0; ci < candList.length; ci++) {
          var cand = candList[ci];
          var wln = wToComm[cand] || 0;
          var gain = wln - gamma * sigmaTot[cand] * k[node] / twoM;
          if (gain > bestGain + 1e-12) {
            bestGain = gain;
            bestComm = cand;
          }
        }
        // Insert node into the chosen community.
        sigmaTot[bestComm] += k[node];
        comm[node] = bestComm;
        if (bestComm !== nodeComm) { moved = true; improvedAny = true; }
      }
    }
    return { comm: comm, improved: improvedAny };
  }

  // Aggregate communities into a smaller graph for the next level.
  function aggregate(adjacency, count, comm) {
    // Renumber communities to a dense 0..K-1 range (deterministic by first appearance in sorted node order).
    var remap = {};
    var K = 0;
    for (var i = 0; i < count; i++) {
      var c = comm[i];
      if (remap[c] === undefined) { remap[c] = K++; }
    }
    var dense = new Array(count);
    for (var j = 0; j < count; j++) dense[j] = remap[comm[j]];
    var newAdj = new Array(K);
    for (var a = 0; a < K; a++) newAdj[a] = {};
    for (var p = 0; p < count; p++) {
      var cp = dense[p];
      var row = adjacency[p];
      for (var q in row) {
        var cq = dense[parseInt(q, 10)];
        newAdj[cp][cq] = (newAdj[cp][cq] || 0) + row[q];
      }
    }
    return { adj: newAdj, count: K, dense: dense };
  }

  // node -> current community id at the original-node granularity.
  var nodeComm = new Array(N);
  for (var t = 0; t < N; t++) nodeComm[t] = t;

  var curAdj = adj;
  var curCount = N;
  var pass = 0;
  while (pass < 50) {
    pass++;
    var level = oneLevel(curAdj, curCount, totalW);
    if (!level.improved) break;
    var agg = aggregate(curAdj, curCount, level.comm);
    // Fold this level's mapping back onto original nodes.
    for (var orig = 0; orig < N; orig++) {
      nodeComm[orig] = agg.dense[nodeComm[orig]];
    }
    curAdj = agg.adj;
    curCount = agg.count;
    if (agg.count === curCount && !level.improved) break;
  }

  var out = {};
  for (var z = 0; z < N; z++) out[ids[z]] = nodeComm[z];
  return out;
}

// ----------------------------------------------------------------------------
// edgeBetweenness(edges) -> { "u\tv": score }
//
// Brandes' algorithm for edge betweenness on the UNDIRECTED, UNWEIGHTED graph
// (matches nx.edge_betweenness_centrality default weight=None). Normalized by
// 2/(n(n-1)) like networkx's undirected default. Edge keys are "u\tv" with u<v
// (sorted) so the Python side can split them back deterministically.
// ----------------------------------------------------------------------------
function edgeBetweenness(edges) {
  var idSet = {};
  for (var i = 0; i < edges.length; i++) { idSet[edges[i][0]] = true; idSet[edges[i][1]] = true; }
  var ids = Object.keys(idSet).sort();
  var index = {};
  for (var n = 0; n < ids.length; n++) index[ids[n]] = n;
  var N = ids.length;

  var adj = new Array(N);
  for (var a = 0; a < N; a++) adj[a] = {};
  for (var e = 0; e < edges.length; e++) {
    var u = index[edges[e][0]], v = index[edges[e][1]];
    if (u === v) continue;
    adj[u][v] = true;
    adj[v][u] = true;
  }
  var neighbors = new Array(N);
  for (var b = 0; b < N; b++) neighbors[b] = Object.keys(adj[b]).map(function (x) { return parseInt(x, 10); }).sort(function (p, q) { return p - q; });

  // edge betweenness accumulator keyed by "min,max".
  var eb = {};
  function ekey(x, y) { return x < y ? x + "," + y : y + "," + x; }

  for (var s = 0; s < N; s++) {
    // BFS single-source shortest paths (unweighted).
    var S = [];
    var P = new Array(N);
    var sigma = new Array(N);
    var dist = new Array(N);
    for (var k = 0; k < N; k++) { P[k] = []; sigma[k] = 0; dist[k] = -1; }
    sigma[s] = 1; dist[s] = 0;
    var queue = [s];
    var qh = 0;
    while (qh < queue.length) {
      var w = queue[qh++];
      S.push(w);
      var nbrs = neighbors[w];
      for (var ni = 0; ni < nbrs.length; ni++) {
        var nb = nbrs[ni];
        if (dist[nb] < 0) { dist[nb] = dist[w] + 1; queue.push(nb); }
        if (dist[nb] === dist[w] + 1) { sigma[nb] += sigma[w]; P[nb].push(w); }
      }
    }
    // Accumulation (back-propagation).
    var delta = new Array(N);
    for (var d = 0; d < N; d++) delta[d] = 0;
    for (var si = S.length - 1; si >= 0; si--) {
      var ww = S[si];
      var preds = P[ww];
      for (var pi = 0; pi < preds.length; pi++) {
        var pv = preds[pi];
        var c = (sigma[pv] / sigma[ww]) * (1 + delta[ww]);
        var key = ekey(pv, ww);
        eb[key] = (eb[key] || 0) + c;
        delta[pv] += c;
      }
    }
  }

  // Undirected: each shortest path counted from both endpoints -> divide by 2.
  // Normalize like networkx undirected default: scale = 2/(n(n-1)).
  var scale = (N > 1) ? (2.0 / (N * (N - 1))) : 1.0;
  var out = {};
  for (var key2 in eb) {
    var parts = key2.split(",");
    var a2 = parseInt(parts[0], 10), b2 = parseInt(parts[1], 10);
    var val = (eb[key2] / 2.0) * scale;
    out[ids[a2] + "\t" + ids[b2]] = val;
  }
  return out;
}

// ----------------------------------------------------------------------------
// simpleCycles(edges, maxLen) -> [[id, id, ...], ...]
//
// Enumerate simple cycles in a DIRECTED graph, bounded by maxLen (number of
// nodes in the cycle). Edges are treated as directed u->v (weight ignored).
// Replaces nx.simple_cycles for import-cycle detection; the Python side already
// dedupes rotations and caps the result, so here we just enumerate (with a hard
// safety cap) starting each search from the lexicographically smallest member.
// ----------------------------------------------------------------------------
function simpleCycles(edges, maxLen) {
  var limit = (maxLen === undefined || maxLen === null) ? 5 : maxLen;
  var SAFETY = 5000;

  var idSet = {};
  for (var i = 0; i < edges.length; i++) { idSet[edges[i][0]] = true; idSet[edges[i][1]] = true; }
  var ids = Object.keys(idSet).sort();
  var index = {};
  for (var n = 0; n < ids.length; n++) index[ids[n]] = n;
  var N = ids.length;

  var succ = new Array(N);
  for (var a = 0; a < N; a++) succ[a] = {};
  for (var e = 0; e < edges.length; e++) {
    var u = index[edges[e][0]], v = index[edges[e][1]];
    if (u === v) continue; // self-loop is not a multi-node cycle
    succ[u][v] = true;
  }
  var out = [];

  // For each start node (ascending), DFS for cycles returning to start, only
  // visiting nodes > start so each cycle is found once from its min member.
  for (var start = 0; start < N && out.length < SAFETY; start++) {
    var stack = [start];
    var onStack = {};
    onStack[start] = true;

    function dfs(node) {
      if (out.length >= SAFETY) return;
      var nbrs = Object.keys(succ[node]).map(function (x) { return parseInt(x, 10); }).sort(function (p, q) { return p - q; });
      for (var ni = 0; ni < nbrs.length; ni++) {
        var nb = nbrs[ni];
        if (nb === start && stack.length >= 2) {
          if (stack.length <= limit) {
            var cyc = [];
            for (var si = 0; si < stack.length; si++) cyc.push(ids[stack[si]]);
            out.push(cyc);
          }
          continue;
        }
        if (nb < start || onStack[nb]) continue;
        if (stack.length >= limit) continue;
        stack.push(nb);
        onStack[nb] = true;
        dfs(nb);
        stack.pop();
        delete onStack[nb];
      }
    }
    dfs(start);
  }
  return out;
}

falkor.register('louvain', louvain);
falkor.register('edgeBetweenness', edgeBetweenness);
falkor.register('simpleCycles', simpleCycles);
