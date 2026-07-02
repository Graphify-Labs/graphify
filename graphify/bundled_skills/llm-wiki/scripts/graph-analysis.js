#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { extractFrontmatter, parseSourcesFrontmatter, sortedUnique } = require("./lib/source-signal-eligibility");

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function roundNumber(value, digits = 3) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function sortedPairKey(a, b) {
  return a < b ? `${a}\t${b}` : `${b}\t${a}`;
}

function normalizeBody(text, degraded, maxLines) {
  const { body } = extractFrontmatter(text);
  const normalized = body.replace(/^\s+/, "").replace(/\s+$/, "");
  if (!degraded) return normalized;
  return normalized.split(/\r?\n/).slice(0, maxLines).join("\n").replace(/\s+$/, "");
}

function loadNodeDetails(nodes, degraded, maxLines) {
  const byId = {};

  for (const node of nodes) {
    const filePath = node._file_path || node.source_path;
    const raw = fs.readFileSync(filePath, "utf8");
    const frontmatter = extractFrontmatter(raw);
    const parsedSources = parseSourcesFrontmatter(frontmatter.frontmatter);
    const normalizedNode = {
      ...node,
      content: normalizeBody(raw, degraded, maxLines),
      _signals: {
        sources: parsedSources.sources,
        sourceSignalAvailable: parsedSources.signalAvailable,
        sourceFieldPresent: parsedSources.hasField,
        sourceFieldParsed: parsedSources.parsed
      }
    };
    byId[node.id] = normalizedNode;
  }

  return byId;
}

function buildInlinks(edges) {
  const inlinks = new Map();

  for (const edge of edges) {
    if (!inlinks.has(edge.to)) inlinks.set(edge.to, new Set());
    inlinks.get(edge.to).add(edge.from);
  }

  return inlinks;
}

function intersectionCount(setA, setB) {
  if (!setA || !setB) return 0;
  let small = setA;
  let large = setB;
  if (setB.size < setA.size) {
    small = setB;
    large = setA;
  }

  let count = 0;
  for (const value of small) {
    if (large.has(value)) count += 1;
  }
  return count;
}

function typeAffinity(typeA, typeB) {
  const pair = [typeA || "other", typeB || "other"].sort().join(":");
  switch (pair) {
    case "entity:entity":
    case "entity:topic":
      return 1;
    case "topic:topic":
      return 0.8;
    case "entity:source":
      return 0.6;
    case "source:source":
      return 0.3;
    default:
      return 0.5;
  }
}

function computePairMetrics(nodesById, edges) {
  const inlinks = buildInlinks(edges);
  const pairMetrics = new Map();

  for (const edge of edges) {
    const pairKey = sortedPairKey(edge.from, edge.to);
    if (pairMetrics.has(pairKey)) continue;

    const fromNode = nodesById[edge.from];
    const toNode = nodesById[edge.to];
    if (!fromNode || !toNode) continue;

    const fromInlinks = inlinks.get(edge.from) || new Set();
    const toInlinks = inlinks.get(edge.to) || new Set();
    const sharedInlinks = intersectionCount(fromInlinks, toInlinks);
    const coCitation = sharedInlinks / Math.max(fromInlinks.size, toInlinks.size, 1);
    const affinity = typeAffinity(fromNode.type, toNode.type);

    const signals = [coCitation, affinity];
    let sourceOverlap = null;
    const sourceSignalAvailable = Boolean(
      fromNode._signals.sourceSignalAvailable && toNode._signals.sourceSignalAvailable
    );

    if (sourceSignalAvailable) {
      const fromSources = new Set(fromNode._signals.sources);
      const toSources = new Set(toNode._signals.sources);
      const overlap = intersectionCount(fromSources, toSources);
      const minSize = Math.min(fromSources.size, toSources.size);
      sourceOverlap = minSize > 0 ? overlap / minSize : 0;
      signals.push(sourceOverlap);
    }

    const weight = clamp01(signals.reduce((sum, value) => sum + value, 0) / signals.length);

    pairMetrics.set(pairKey, {
      weight: roundNumber(weight),
      signals: {
        co_citation: roundNumber(coCitation),
        source_overlap: sourceOverlap == null ? null : roundNumber(sourceOverlap),
        type_affinity: roundNumber(affinity)
      },
      source_signal_available: sourceSignalAvailable
    });
  }

  return pairMetrics;
}

function buildUndirectedGraph(nodeIds, pairMetrics) {
  const adjacency = new Map();
  const degrees = new Map();

  for (const nodeId of nodeIds) {
    adjacency.set(nodeId, new Map());
    degrees.set(nodeId, 0);
  }

  for (const [pairKey, metrics] of pairMetrics.entries()) {
    const [left, right] = pairKey.split("\t");
    if (!adjacency.has(left) || !adjacency.has(right)) continue;
    const weight = metrics.weight;
    adjacency.get(left).set(right, weight);
    adjacency.get(right).set(left, weight);
    degrees.set(left, degrees.get(left) + weight);
    degrees.set(right, degrees.get(right) + weight);
  }

  return { adjacency, degrees };
}

function runLocalMove(graph) {
  const nodes = Array.from(graph.nodes.keys()).sort();
  const communities = new Map();
  const totals = new Map();
  let moved = false;

  for (const nodeId of nodes) {
    communities.set(nodeId, nodeId);
    totals.set(nodeId, graph.degrees.get(nodeId) || 0);
  }

  if (graph.m2 === 0) {
    return { communities, changed: false };
  }

  let changedInPass = true;
  let passCount = 0;
  while (changedInPass && passCount < 50) {
    passCount++;
    changedInPass = false;

    for (const nodeId of nodes) {
      const degree = graph.degrees.get(nodeId) || 0;
      const currentCommunity = communities.get(nodeId);
      const neighborCommunities = new Map();

      for (const [neighborId, weight] of graph.nodes.get(nodeId).entries()) {
        const communityId = communities.get(neighborId);
        neighborCommunities.set(communityId, (neighborCommunities.get(communityId) || 0) + weight);
      }

      totals.set(currentCommunity, (totals.get(currentCommunity) || 0) - degree);
      if ((neighborCommunities.get(currentCommunity) || 0) === 0) {
        neighborCommunities.set(currentCommunity, 0);
      }

      let bestCommunity = currentCommunity;
      let bestGain = 0;

      const candidates = Array.from(neighborCommunities.keys()).sort();
      for (const communityId of candidates) {
        const inWeight = neighborCommunities.get(communityId) || 0;
        const gain = inWeight - ((totals.get(communityId) || 0) * degree) / graph.m2;
        if (gain > bestGain + 1e-9) {
          bestGain = gain;
          bestCommunity = communityId;
        }
      }

      communities.set(nodeId, bestCommunity);
      totals.set(bestCommunity, (totals.get(bestCommunity) || 0) + degree);

      if (bestCommunity !== currentCommunity) {
        changedInPass = true;
        moved = true;
      }
    }
  }

  return { communities, changed: moved };
}

function aggregateGraph(graph, communities) {
  const communityIds = sortedUnique(Array.from(communities.values()));
  const aggregatedNodes = new Map();
  const aggregatedDegrees = new Map();
  const members = new Map();

  for (const communityId of communityIds) {
    aggregatedNodes.set(communityId, new Map());
    aggregatedDegrees.set(communityId, 0);
    members.set(communityId, []);
  }

  for (const [nodeId, communityId] of communities.entries()) {
    members.get(communityId).push(...(graph.members.get(nodeId) || [nodeId]));
  }

  for (const [nodeId, neighbors] of graph.nodes.entries()) {
    const sourceCommunity = communities.get(nodeId);
    for (const [neighborId, weight] of neighbors.entries()) {
      if (nodeId > neighborId) continue;
      const targetCommunity = communities.get(neighborId);
      const current = aggregatedNodes.get(sourceCommunity).get(targetCommunity) || 0;
      aggregatedNodes.get(sourceCommunity).set(targetCommunity, current + weight);
      if (sourceCommunity !== targetCommunity) {
        const mirrored = aggregatedNodes.get(targetCommunity).get(sourceCommunity) || 0;
        aggregatedNodes.get(targetCommunity).set(sourceCommunity, mirrored + weight);
      }
    }
  }

  for (const [communityId, neighbors] of aggregatedNodes.entries()) {
    let degree = 0;
    for (const [neighborId, weight] of neighbors.entries()) {
      degree += neighborId === communityId ? weight * 2 : weight;
    }
    aggregatedDegrees.set(communityId, degree);
  }

  return {
    nodes: aggregatedNodes,
    degrees: aggregatedDegrees,
    members,
    m2: Array.from(aggregatedDegrees.values()).reduce((sum, value) => sum + value, 0)
  };
}

function runLouvain(nodeIds, pairMetrics) {
  const baseGraph = buildUndirectedGraph(nodeIds, pairMetrics);
  let graph = {
    nodes: baseGraph.adjacency,
    degrees: baseGraph.degrees,
    members: new Map(nodeIds.map((nodeId) => [nodeId, [nodeId]])),
    m2: Array.from(baseGraph.degrees.values()).reduce((sum, value) => sum + value, 0)
  };

  let bestMembers = graph.members;

  while (true) {
    const phase = runLocalMove(graph);
    const nextGraph = aggregateGraph(graph, phase.communities);
    bestMembers = nextGraph.members;

    if (!phase.changed || nextGraph.nodes.size === graph.nodes.size) {
      break;
    }

    graph = nextGraph;
  }

  const finalCommunities = new Map();
  for (const [communityId, members] of bestMembers.entries()) {
    for (const nodeId of members) {
      finalCommunities.set(nodeId, communityId);
    }
  }

  return finalCommunities;
}

function buildDirectedDegree(edges) {
  const degree = new Map();
  for (const edge of edges) {
    degree.set(edge.from, (degree.get(edge.from) || 0) + 1);
    degree.set(edge.to, (degree.get(edge.to) || 0) + 1);
  }
  return degree;
}

function chooseCommunityLabels(nodeIds, communityAssignments, nodesById, edges) {
  const groups = new Map();
  const degree = buildDirectedDegree(edges);

  for (const nodeId of nodeIds) {
    const communityId = communityAssignments.get(nodeId) || nodeId;
    if (!groups.has(communityId)) groups.set(communityId, []);
    groups.get(communityId).push(nodeId);
  }

  const labeledAssignments = new Map();

  for (const members of groups.values()) {
    members.sort();
    if (members.length === 1) {
      labeledAssignments.set(members[0], null);
      continue;
    }

    const memberNodes = members.map((memberId) => nodesById[memberId]);
    const topics = memberNodes.filter((node) => node && node.type === "topic");
    const candidates = topics.length ? topics : memberNodes;
    candidates.sort((left, right) => {
      const degreeDiff = (degree.get(right.id) || 0) - (degree.get(left.id) || 0);
      if (degreeDiff !== 0) return degreeDiff;
      return left.id.localeCompare(right.id);
    });

    const label = candidates[0] ? candidates[0].id : members[0];
    for (const memberId of members) {
      labeledAssignments.set(memberId, label);
    }
  }

  return labeledAssignments;
}

function buildInsights(nodesById, edges, pairMetrics, communityAssignments, options) {
  const directedDegree = buildDirectedDegree(edges);
  const undirectedPairs = new Map();
  const adjacency = new Map();

  for (const nodeId of Object.keys(nodesById)) {
    adjacency.set(nodeId, new Set());
  }

  for (const edge of edges) {
    const pairKey = sortedPairKey(edge.from, edge.to);
    if (!undirectedPairs.has(pairKey)) {
      undirectedPairs.set(pairKey, {
        from: pairKey.split("\t")[0],
        to: pairKey.split("\t")[1],
        weight: pairMetrics.get(pairKey)?.weight || 0
      });
    }
    adjacency.get(edge.from)?.add(edge.to);
    adjacency.get(edge.to)?.add(edge.from);
  }

  const isolatedNodes = Object.values(nodesById)
    .filter((node) => (directedDegree.get(node.id) || 0) <= 1)
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((node) => ({
      id: node.id,
      label: node.label,
      degree: directedDegree.get(node.id) || 0,
      community: communityAssignments.get(node.id) || null
    }));

  const bridgeNodes = [];
  for (const node of Object.values(nodesById).sort((left, right) => left.id.localeCompare(right.id))) {
    const ownCommunity = communityAssignments.get(node.id) || null;
    const connectedCommunities = sortedUnique(
      Array.from(adjacency.get(node.id) || [])
        .map((neighborId) => communityAssignments.get(neighborId) || null)
        .filter((c) => c && c !== ownCommunity)
    );

    if (connectedCommunities.length >= 2) {
      bridgeNodes.push({
        id: node.id,
        label: node.label,
        community: ownCommunity,
        connected_communities: connectedCommunities,
        community_count: connectedCommunities.length
      });
    }
  }

  const communityMembers = new Map();
  for (const node of Object.values(nodesById)) {
    const communityId = communityAssignments.get(node.id) || null;
    if (!communityId) continue;
    if (!communityMembers.has(communityId)) communityMembers.set(communityId, []);
    communityMembers.get(communityId).push(node.id);
  }

  const sparseCommunities = [];
  for (const [communityId, members] of Array.from(communityMembers.entries()).sort((left, right) => left[0].localeCompare(right[0]))) {
    if (members.length < 3) continue;

    const memberSet = new Set(members);
    let internalEdges = 0;
    for (const pair of undirectedPairs.values()) {
      if (memberSet.has(pair.from) && memberSet.has(pair.to)) internalEdges += 1;
    }

    const possibleEdges = (members.length * (members.length - 1)) / 2;
    const density = possibleEdges === 0 ? 0 : internalEdges / possibleEdges;
    if (density < 0.15) {
      sparseCommunities.push({
        id: communityId,
        label: nodesById[communityId]?.label || communityId,
        node_count: members.length,
        density: roundNumber(density),
        members: members.sort(),
        internal_edges: internalEdges
      });
    }
  }

  const surprisingConnections = Array.from(undirectedPairs.values())
    .filter((pair) => {
      const fromCommunity = communityAssignments.get(pair.from) || null;
      const toCommunity = communityAssignments.get(pair.to) || null;
      return fromCommunity && toCommunity && fromCommunity !== toCommunity && pair.weight >= 0.75;
    })
    .sort((left, right) => {
      if (right.weight !== left.weight) return right.weight - left.weight;
      if (left.from !== right.from) return left.from.localeCompare(right.from);
      return left.to.localeCompare(right.to);
    })
    .slice(0, 8)
    .map((pair) => ({
      from: pair.from,
      to: pair.to,
      weight: pair.weight,
      from_community: communityAssignments.get(pair.from) || null,
      to_community: communityAssignments.get(pair.to) || null
    }));

  const degraded = options.nodeCount > options.maxInsightNodes || options.edgeCount > options.maxInsightEdges;
  if (degraded) {
    return {
      surprising_connections: [],
      isolated_nodes: isolatedNodes,
      bridge_nodes: [],
      sparse_communities: [],
      meta: {
        degraded: true,
        node_count: options.nodeCount,
        edge_count: options.edgeCount,
        max_insight_nodes: options.maxInsightNodes,
        max_insight_edges: options.maxInsightEdges
      }
    };
  }

  return {
    surprising_connections: surprisingConnections,
    isolated_nodes: isolatedNodes,
    bridge_nodes: bridgeNodes,
    sparse_communities: sparseCommunities,
    meta: {
      degraded: false,
      node_count: options.nodeCount,
      edge_count: options.edgeCount,
      max_insight_nodes: options.maxInsightNodes,
      max_insight_edges: options.maxInsightEdges
    }
  };
}

function buildLearning(analyzedNodes, analyzedEdges) {
  const degreeMap = new Map();
  for (const edge of analyzedEdges) {
    degreeMap.set(edge.from, (degreeMap.get(edge.from) || 0) + 1);
    degreeMap.set(edge.to, (degreeMap.get(edge.to) || 0) + 1);
  }

  const communityGroups = new Map();
  for (const node of analyzedNodes) {
    if (node.community == null) continue;
    if (!communityGroups.has(node.community)) communityGroups.set(node.community, []);
    communityGroups.get(node.community).push(node);
  }

  const communities = [];
  for (const [cid, members] of communityGroups.entries()) {
    const memberIds = new Set(members.map(n => n.id));
    let totalWeight = 0;
    for (const edge of analyzedEdges) {
      if (memberIds.has(edge.from) && memberIds.has(edge.to)) totalWeight += edge.weight;
    }
    const isWeak = members.length < 3;
    const startNode = members.slice().sort((a, b) => {
      const degDiff = (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0);
      if (degDiff !== 0) return degDiff;
      return a.id.localeCompare(b.id);
    })[0];

    communities.push({
      id: cid,
      label: (members.find(n => n.id === cid) || members[0]).label,
      node_count: members.length,
      source_count: members.filter(n => n.type === "source").length,
      internal_edge_weight: roundNumber(totalWeight),
      is_primary: false,
      is_weak: isWeak,
      recommended_start_node_id: startNode.id
    });
  }

  communities.sort((a, b) => {
    if (b.node_count !== a.node_count) return b.node_count - a.node_count;
    if (b.internal_edge_weight !== a.internal_edge_weight) return b.internal_edge_weight - a.internal_edge_weight;
    return a.id.localeCompare(b.id);
  });

  if (communities.length > 0) communities[0].is_primary = true;

  const primary = communities.length > 0 ? communities[0] : null;
  const startNodeId = primary ? primary.recommended_start_node_id : null;

  let pathNodeIds = [];
  let pathDegraded = false;
  if (primary && !primary.is_weak && startNodeId) {
    const primaryMemberIds = new Set(communityGroups.get(primary.id).map(n => n.id));
    const neighbors = analyzedEdges
      .filter(e => (e.from === startNodeId && primaryMemberIds.has(e.to)) ||
                   (e.to === startNodeId && primaryMemberIds.has(e.from)))
      .map(e => e.from === startNodeId ? e.to : e.from);
    pathNodeIds = [startNodeId, ...sortedUnique(neighbors).filter(id => id !== startNodeId)];
    if (pathNodeIds.length < 2) pathDegraded = true;
  } else {
    pathDegraded = true;
  }

  let communityNodeIds = [];
  let communityDegraded = false;
  if (primary && !primary.is_weak) {
    communityNodeIds = communityGroups.get(primary.id).map(n => n.id).sort();
  } else {
    communityDegraded = true;
  }

  const globalNodeIds = analyzedNodes.slice().sort((a, b) => {
    const degDiff = (degreeMap.get(b.id) || 0) - (degreeMap.get(a.id) || 0);
    if (degDiff !== 0) return degDiff;
    return a.id.localeCompare(b.id);
  }).map(n => n.id);

  const defaultMode = "global";

  return {
    version: 1,
    entry: {
      recommended_start_node_id: startNodeId,
      recommended_start_reason: startNodeId ? "community_hub" : null,
      default_mode: defaultMode
    },
    views: {
      path: {
        enabled: !pathDegraded,
        start_node_id: pathDegraded ? null : startNodeId,
        node_ids: pathDegraded ? [] : pathNodeIds,
        degraded: pathDegraded
      },
      community: {
        enabled: !communityDegraded,
        community_id: primary && !communityDegraded ? primary.id : null,
        label: primary && !communityDegraded ? primary.label : null,
        node_ids: communityDegraded ? [] : communityNodeIds,
        is_weak: primary ? primary.is_weak : false,
        degraded: communityDegraded
      },
      global: {
        enabled: true,
        node_ids: globalNodeIds,
        degraded: false
      }
    },
    communities,
    degraded: {
      path_to_community: pathDegraded,
      community_to_global: communityDegraded
    }
  };
}

function analyzeGraph(nodes, edges, options = {}) {
  const degraded = options.degraded === true;
  const maxLines = options.maxLines || 500;
  const maxInsightNodes = options.maxInsightNodes || 250;
  const maxInsightEdges = options.maxInsightEdges || 1000;

  const nodesById = loadNodeDetails(nodes, degraded, maxLines);
  const pairMetrics = computePairMetrics(nodesById, edges);
  const nodeIds = nodes.map((node) => node.id);
  const communityAssignments = chooseCommunityLabels(
    nodeIds,
    runLouvain(nodeIds, pairMetrics),
    nodesById,
    edges
  );

  const analyzedNodes = nodes.map((node) => ({
    id: node.id,
    label: node.label,
    type: node.type,
    source_path: node.source_path,
    community: communityAssignments.get(node.id) || null,
    content: nodesById[node.id].content
  }));

  const analyzedEdges = edges.map((edge) => {
    const pairKey = sortedPairKey(edge.from, edge.to);
    const metrics = pairMetrics.get(pairKey) || {
      weight: 0,
      signals: { co_citation: 0, source_overlap: null, type_affinity: 0.5 },
      source_signal_available: false
    };

    return {
      id: edge.id,
      from: edge.from,
      to: edge.to,
      type: edge.type,
      confidence: edge.confidence || edge.type,
      relation_type: edge.relation_type || "依赖",
      weight: metrics.weight,
      source_signal_available: metrics.source_signal_available,
      signals: metrics.signals
    };
  });

  const insights = buildInsights(nodesById, analyzedEdges, pairMetrics, communityAssignments, {
    nodeCount: analyzedNodes.length,
    edgeCount: analyzedEdges.length,
    maxInsightNodes,
    maxInsightEdges
  });

  const learning = buildLearning(analyzedNodes, analyzedEdges);

  return { nodes: analyzedNodes, edges: analyzedEdges, insights, learning };
}

function main(argv) {
  if (argv.length < 7) {
    console.error("Usage: node graph-analysis.js <nodes.json> <edges.json> <output.json> <degraded:0|1> <max-lines> <max-insight-nodes> <max-insight-edges>");
    process.exit(1);
  }

  const timer = setTimeout(() => {
    console.error("ERROR: graph analysis timed out (120s)");
    process.exit(2);
  }, 120_000);
  timer.unref();

  const [, , nodesPath, edgesPath, outputPath, degradedRaw, maxLinesRaw, maxInsightNodesRaw, maxInsightEdgesRaw] = argv;

  for (const p of [nodesPath, edgesPath]) {
    if (!fs.existsSync(p)) {
      console.error(`ERROR: File not found: ${p}`);
      process.exit(1);
    }
  }

  const analyzed = analyzeGraph(readJson(nodesPath), readJson(edgesPath), {
    degraded: degradedRaw === "1",
    maxLines: Number(maxLinesRaw) || 500,
    maxInsightNodes: Number(maxInsightNodesRaw) || 250,
    maxInsightEdges: Number(maxInsightEdgesRaw) || 1000
  });

  writeJson(outputPath, analyzed);
  clearTimeout(timer);
}

if (require.main === module) {
  try {
    main(process.argv);
  } catch (error) {
    const code = error && error.code;
    if (code === "ENOENT") {
      console.error(`ERROR: File not found: ${error.path || "(unknown)"}`);
    } else if (error instanceof SyntaxError) {
      console.error(`ERROR: Invalid JSON in input: ${error.message}`);
    } else {
      console.error(`ERROR: ${error && error.message ? error.message : String(error)}`);
    }
    process.exit(1);
  }
}

module.exports = {
  analyzeGraph,
  buildInsights,
  buildLearning,
  chooseCommunityLabels,
  computePairMetrics,
  extractFrontmatter,
  normalizeBody,
  parseSourcesFrontmatter,
  runLouvain,
  typeAffinity
};
