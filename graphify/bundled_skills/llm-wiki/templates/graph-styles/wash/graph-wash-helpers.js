/* DEPRECATED: Legacy wash helpers retained for one release cycle after Stage 4 engine HTML migration. Do not extend; use packages/graph-engine instead. */
(function (root) {
  "use strict";

  var LABEL_CJK_WIDTH = 15;
  var LABEL_LATIN_WIDTH = 8.5;
  var LABEL_PADDING = 22;
  var LABEL_MIN_WIDTH = 72;
  var LABEL_MAX_WIDTH = 180;
  var LABEL_ELLIPSIS = "…";
  var LABEL_ELLIPSIS_WIDTH = 8;
  var ATLAS_WORLD_WIDTH = 1000;
  var ATLAS_WORLD_HEIGHT = 680;
  var ATLAS_MIN_SCALE = 0.62;
  var ATLAS_MAX_SCALE = 3.2;
  var MINIMAP_VIEWBOX = { x: 5, y: 3, width: 150, height: 48 };

  var labelSegmenter =
    typeof Intl !== "undefined" && Intl.Segmenter
      ? new Intl.Segmenter("zh", { granularity: "grapheme" })
      : null;

  function isVariationSelector(grapheme) {
    var code = grapheme.codePointAt(0);
    return code >= 0xFE00 && code <= 0xFE0F;
  }

  function isCombiningMark(grapheme) {
    var code = grapheme.codePointAt(0);
    return (code >= 0x0300 && code <= 0x036F)
      || (code >= 0x1AB0 && code <= 0x1AFF)
      || (code >= 0x1DC0 && code <= 0x1DFF)
      || (code >= 0x20D0 && code <= 0x20FF)
      || (code >= 0xFE20 && code <= 0xFE2F);
  }

  function isEmojiModifier(grapheme) {
    var code = grapheme.codePointAt(0);
    return code >= 0x1F3FB && code <= 0x1F3FF;
  }

  function splitLabelGraphemes(label) {
    if (labelSegmenter) {
      return Array.from(labelSegmenter.segment(label), function (s) {
        return s.segment;
      });
    }

    var parts = Array.from(label);
    if (!parts.length) return [];

    var graphemes = [parts[0]];
    for (var i = 1; i < parts.length; i++) {
      var current = parts[i];
      var previous = parts[i - 1];
      if (
        current === "‍"
        || previous === "‍"
        || isVariationSelector(current)
        || isCombiningMark(current)
        || isEmojiModifier(current)
      ) {
        graphemes[graphemes.length - 1] += current;
      } else {
        graphemes.push(current);
      }
    }

    return graphemes;
  }

  function labelCharWidth(grapheme) {
    return /[一-鿿]/.test(grapheme) ? LABEL_CJK_WIDTH : LABEL_LATIN_WIDTH;
  }

  function measureLabelWidth(graphemes) {
    var width = 0;
    for (var i = 0; i < graphemes.length; i++) {
      width += labelCharWidth(graphemes[i]);
    }
    return width;
  }

  function truncateLabel(label, maxWidth) {
    if (!label || typeof label !== "string") {
      return { text: "", truncated: false };
    }

    var graphemes = splitLabelGraphemes(label);
    var totalWidth = measureLabelWidth(graphemes);
    if (totalWidth + LABEL_PADDING <= maxWidth) {
      return { text: label, truncated: false };
    }

    var out = "";
    var width = 0;
    for (var i = 0; i < graphemes.length; i++) {
      var gw = labelCharWidth(graphemes[i]);
      if (width + gw + LABEL_ELLIPSIS_WIDTH + LABEL_PADDING > maxWidth) break;
      out += graphemes[i];
      width += gw;
    }
    return { text: out + LABEL_ELLIPSIS, truncated: true };
  }

  function cardDims(n) {
    var label = n.label || n.id;
    var widthByLabel = measureLabelWidth(splitLabelGraphemes(label));
    var width = Math.max(LABEL_MIN_WIDTH, Math.min(LABEL_MAX_WIDTH, widthByLabel + LABEL_PADDING));
    var height = 36;
    if (n.type === "topic") { height = 40; width += 6; }
    if (n.type === "source") { height = 32; }
    return { w: width, h: height };
  }

  function createSafeStorage(storage, logger) {
    return {
      get: function (key) {
        try { return storage.getItem(key); }
        catch (err) { if (logger) logger("[wiki] storage.get failed:", key, err); return null; }
      },
      set: function (key, value) {
        try { storage.setItem(key, value); }
        catch (err) { if (logger) logger("[wiki] storage.set failed:", key, err); }
      }
    };
  }

  function normalizeStorageSegment(value) {
    return String(value == null ? "" : value)
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9一-鿿]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 48);
  }

  function hashString(value) {
    var input = String(value == null ? "" : value);
    var hash = 0;
    for (var i = 0; i < input.length; i++) {
      hash = ((hash << 5) - hash + input.charCodeAt(i)) >>> 0;
    }
    return hash.toString(36);
  }

  function getWikiStorageNamespace(meta, pathname) {
    var title = normalizeStorageSegment(meta && meta.wiki_title ? meta.wiki_title : "");
    var basis = typeof pathname === "string" && pathname
      ? pathname
      : (meta && meta.wiki_title) || title || "default";
    return "llm-wiki:" + (title || "default") + ":" + hashString(basis);
  }

  function defaultQueue() {
    return {
      version: 1,
      favorites: [],
      notes: [],
      recentNoteIds: []
    };
  }

  function normalizeQueue(raw) {
    if (!raw || typeof raw !== "object") return defaultQueue();
    var d = defaultQueue();
    var favorites = Array.isArray(raw.favorites) ? raw.favorites : d.favorites;
    var notes = Array.isArray(raw.notes) ? raw.notes : d.notes;
    var recentNoteIds = Array.isArray(raw.recentNoteIds) ? raw.recentNoteIds : d.recentNoteIds;
    var seenFavorites = {};
    var normalizedFavorites = favorites
      .map(function (nodeId) {
        return nodeId == null ? null : String(nodeId);
      })
      .filter(function (nodeId) {
        if (!nodeId || seenFavorites[nodeId]) return false;
        seenFavorites[nodeId] = true;
        return true;
      });
    var normalizedNotes = notes
      .map(function (note) {
        if (!note || typeof note !== "object" || note.id == null || note.node_id == null) return null;
        return {
          id: String(note.id),
          node_id: String(note.node_id),
          label: note.label == null ? String(note.node_id) : String(note.label),
          text: note.text == null ? "" : String(note.text),
          created_at: note.created_at == null ? null : String(note.created_at)
        };
      })
      .filter(function (note) {
        return !!note;
      });
    var noteIdSet = {};
    for (var i = 0; i < normalizedNotes.length; i++) {
      noteIdSet[normalizedNotes[i].id] = true;
    }
    var seenRecent = {};
    var normalizedRecentNoteIds = recentNoteIds
      .map(function (noteId) {
        return noteId == null ? null : String(noteId);
      })
      .filter(function (noteId) {
        if (!noteId || !noteIdSet[noteId] || seenRecent[noteId]) return false;
        seenRecent[noteId] = true;
        return true;
      });
    if (!normalizedRecentNoteIds.length && normalizedNotes.length) {
      normalizedRecentNoteIds = normalizedNotes.map(function (note) {
        return note.id;
      });
    }
    return {
      version: d.version,
      favorites: normalizedFavorites,
      notes: normalizedNotes,
      recentNoteIds: normalizedRecentNoteIds
    };
  }

  function toggleQueueFavorite(queue, nodeId) {
    var safe = normalizeQueue(queue);
    var favoriteNodeId = nodeId == null ? "" : String(nodeId);
    if (!favoriteNodeId) return safe;
    var favorites = safe.favorites.slice();
    var existingIndex = favorites.indexOf(favoriteNodeId);
    if (existingIndex === -1) {
      favorites.unshift(favoriteNodeId);
    } else {
      favorites.splice(existingIndex, 1);
    }
    return {
      version: safe.version,
      favorites: favorites,
      notes: safe.notes.slice(),
      recentNoteIds: safe.recentNoteIds.slice()
    };
  }

  function appendQueueNote(queue, note, limit) {
    var safe = normalizeQueue(queue);
    if (!note || typeof note !== "object" || note.id == null || note.node_id == null) return safe;
    var noteLimit = Number.isFinite(Number(limit)) ? Math.max(1, Math.round(Number(limit))) : 50;
    var normalizedNote = {
      id: String(note.id),
      node_id: String(note.node_id),
      label: note.label == null ? String(note.node_id) : String(note.label),
      text: note.text == null ? "" : String(note.text),
      created_at: note.created_at == null ? null : String(note.created_at)
    };
    var notes = [normalizedNote].concat(safe.notes.filter(function (item) {
      return item.id !== normalizedNote.id;
    })).slice(0, noteLimit);
    var recentNoteIds = [normalizedNote.id].concat(safe.recentNoteIds.filter(function (noteId) {
      return noteId !== normalizedNote.id;
    })).slice(0, Math.min(noteLimit, 12));
    return {
      version: safe.version,
      favorites: safe.favorites.slice(),
      notes: notes,
      recentNoteIds: recentNoteIds
    };
  }

  function summarizeQueue(queue, nodesById, limit) {
    var safe = normalizeQueue(queue);
    var maxItems = Number.isFinite(Number(limit)) ? Math.max(1, Math.round(Number(limit))) : 4;
    var byId = nodesById && typeof nodesById === "object" ? nodesById : {};
    var notesById = {};
    var recentItems = [];
    var i;

    for (i = 0; i < safe.notes.length; i++) {
      notesById[safe.notes[i].id] = safe.notes[i];
    }

    for (i = 0; i < safe.recentNoteIds.length && recentItems.length < maxItems; i++) {
      var note = notesById[safe.recentNoteIds[i]];
      if (!note) continue;
      var noteNode = byId[note.node_id];
      recentItems.push({
        kind: "note",
        node_id: note.node_id,
        label: note.label || (noteNode && (noteNode.label || noteNode.id)) || note.node_id,
        text: note.text || ""
      });
    }

    for (i = 0; i < safe.favorites.length && recentItems.length < maxItems; i++) {
      var favoriteNodeId = safe.favorites[i];
      var favoriteNode = byId[favoriteNodeId];
      recentItems.push({
        kind: "favorite",
        node_id: favoriteNodeId,
        label: favoriteNode && (favoriteNode.label || favoriteNode.id) ? (favoriteNode.label || favoriteNode.id) : favoriteNodeId,
        text: ""
      });
    }

    return {
      favorite_count: safe.favorites.length,
      note_count: safe.notes.length,
      recent_items: recentItems
    };
  }

  function defaultLearning() {
    return {
      version: 1,
      entry: { recommended_start_node_id: null, recommended_start_reason: null, default_mode: "global" },
      views: {
        path: { enabled: false, start_node_id: null, node_ids: [], degraded: true },
        community: { enabled: false, community_id: null, label: null, node_ids: [], is_weak: false, degraded: true },
        global: { enabled: true, node_ids: [], degraded: false }
      },
      communities: [],
      degraded: { path_to_community: true, community_to_global: true }
    };
  }

  function normalizeLearning(raw) {
    if (!raw || typeof raw !== "object") return defaultLearning();
    var d = defaultLearning();
    function pick(obj, key, fallback) {
      return obj && obj[key] != null ? obj[key] : fallback;
    }
    return {
      version: pick(raw, "version", d.version),
      entry: {
        recommended_start_node_id: pick(raw.entry, "recommended_start_node_id", d.entry.recommended_start_node_id),
        recommended_start_reason: pick(raw.entry, "recommended_start_reason", d.entry.recommended_start_reason),
        default_mode: pick(raw.entry, "default_mode", d.entry.default_mode)
      },
      views: {
        path: {
          enabled: pick(raw.views && raw.views.path, "enabled", d.views.path.enabled),
          start_node_id: pick(raw.views && raw.views.path, "start_node_id", d.views.path.start_node_id),
          node_ids: Array.isArray(raw.views && raw.views.path && raw.views.path.node_ids) ? raw.views.path.node_ids : d.views.path.node_ids,
          degraded: pick(raw.views && raw.views.path, "degraded", d.views.path.degraded)
        },
        community: {
          enabled: pick(raw.views && raw.views.community, "enabled", d.views.community.enabled),
          community_id: pick(raw.views && raw.views.community, "community_id", d.views.community.community_id),
          label: pick(raw.views && raw.views.community, "label", d.views.community.label),
          node_ids: Array.isArray(raw.views && raw.views.community && raw.views.community.node_ids) ? raw.views.community.node_ids : d.views.community.node_ids,
          is_weak: pick(raw.views && raw.views.community, "is_weak", d.views.community.is_weak),
          degraded: pick(raw.views && raw.views.community, "degraded", d.views.community.degraded)
        },
        global: {
          enabled: pick(raw.views && raw.views.global, "enabled", d.views.global.enabled),
          node_ids: Array.isArray(raw.views && raw.views.global && raw.views.global.node_ids) ? raw.views.global.node_ids : d.views.global.node_ids,
          degraded: pick(raw.views && raw.views.global, "degraded", d.views.global.degraded)
        }
      },
      communities: Array.isArray(raw.communities) ? raw.communities : d.communities,
      degraded: {
        path_to_community: pick(raw.degraded, "path_to_community", d.degraded.path_to_community),
        community_to_global: pick(raw.degraded, "community_to_global", d.degraded.community_to_global)
      }
    };
  }

  function resolveInitialMode(learning) {
    return "global";
  }

  function getCommunityNodeIds(nodes, communityId) {
    if (!Array.isArray(nodes) || !communityId) return [];
    return nodes
      .filter(function (node) {
        return node && node.community != null && String(node.community) === String(communityId);
      })
      .map(function (node) {
        return node.id;
      })
      .sort();
  }

  function getVisibleNodeIds(learning, mode) {
    if (!learning || !learning.views) return [];
    var view = learning.views[mode];
    if (!view || !view.enabled) return [];
    return Array.isArray(view.node_ids) ? view.node_ids : [];
  }

  function getVisibleLinks(allLinks, visibleIds) {
    if (!visibleIds || !visibleIds.length) return allLinks;
    var idSet = {};
    for (var i = 0; i < visibleIds.length; i++) idSet[visibleIds[i]] = true;
    return allLinks.filter(function (l) {
      var s = l.source.id || l.source;
      var t = l.target.id || l.target;
      return idSet[s] && idSet[t];
    });
  }

  function buildSearchHaystack(node) {
    return ((node && (node.label || node.id || "")) + "\n" + (((node && node.content) || "").slice(0, 500))).toLowerCase();
  }

  function buildSearchIndex(nodes) {
    if (!Array.isArray(nodes)) return [];
    return nodes.map(function (node) {
      return { node: node, haystack: buildSearchHaystack(node) };
    });
  }

  function filterLinksByTypes(allLinks, filters) {
    if (!Array.isArray(allLinks)) return [];
    if (!filters || typeof filters !== "object") return allLinks.slice();
    return allLinks.filter(function (link) {
      var type = link && link.type ? link.type : "EXTRACTED";
      return filters[type] !== false;
    });
  }

  function applySearchToNodeIds(searchIndex, query) {
    if (!Array.isArray(searchIndex)) return [];
    var normalizedQuery = typeof query === "string" ? query.trim().toLowerCase() : "";
    var matches = !normalizedQuery
      ? searchIndex
      : searchIndex.filter(function (entry) {
          return entry && typeof entry.haystack === "string" && entry.haystack.indexOf(normalizedQuery) !== -1;
        });
    return matches
      .map(function (entry) {
        return entry && entry.node ? entry.node.id : null;
      })
      .filter(function (id) {
        return id != null;
      });
  }

  function getLinkEndpointIds(link) {
    return {
      sourceId: link && link.source && link.source.id ? link.source.id : link && link.source,
      targetId: link && link.target && link.target.id ? link.target.id : link && link.target
    };
  }

  function sortNodeIdsByScore(nodeIds, scores, nodesById) {
    return nodeIds.slice().sort(function (left, right) {
      var scoreDiff = (scores[right] || 0) - (scores[left] || 0);
      if (scoreDiff) return scoreDiff;
      var leftDegree = nodesById[left] && Number.isFinite(Number(nodesById[left].degree)) ? Number(nodesById[left].degree) : 0;
      var rightDegree = nodesById[right] && Number.isFinite(Number(nodesById[right].degree)) ? Number(nodesById[right].degree) : 0;
      if (rightDegree !== leftDegree) return rightDegree - leftDegree;
      return String(left).localeCompare(String(right));
    });
  }

  function applyFocusMode(options) {
    var safe = options && typeof options === "object" ? options : {};
    var nodes = Array.isArray(safe.nodes) ? safe.nodes : [];
    var links = Array.isArray(safe.links) ? safe.links : [];
    var nodeIds = Array.isArray(safe.nodeIds) ? safe.nodeIds.slice() : [];
    var mode = safe.mode || "all";
    var anchorNodeId = safe.anchorNodeId != null ? String(safe.anchorNodeId) : null;
    var highConfidenceThreshold = Number.isFinite(Number(safe.highConfidenceThreshold)) ? Number(safe.highConfidenceThreshold) : 0.75;
    var nodesById = {};
    var idSet = {};
    var i;

    for (i = 0; i < nodes.length; i++) {
      if (nodes[i] && nodes[i].id != null) nodesById[nodes[i].id] = nodes[i];
    }
    for (i = 0; i < nodeIds.length; i++) idSet[nodeIds[i]] = true;

    if (!nodeIds.length) return { node_ids: [], links: [] };

    var scopedLinks = getVisibleLinks(links, nodeIds);
    if (mode === "all") return { node_ids: nodeIds.slice(), links: scopedLinks };

    if (mode === "high_confidence") {
      var strongLinks = scopedLinks.filter(function (link) {
        var weight = Number(link && link.weight);
        return Number.isFinite(weight) && weight >= highConfidenceThreshold;
      });
      var strongIdSet = {};
      for (i = 0; i < strongLinks.length; i++) {
        var strongEdge = getLinkEndpointIds(strongLinks[i]);
        if (idSet[strongEdge.sourceId]) strongIdSet[strongEdge.sourceId] = true;
        if (idSet[strongEdge.targetId]) strongIdSet[strongEdge.targetId] = true;
      }
      if (anchorNodeId && idSet[anchorNodeId]) strongIdSet[anchorNodeId] = true;
      var strongNodeIds = nodeIds.filter(function (id) {
        return !!strongIdSet[id];
      });
      return { node_ids: strongNodeIds, links: getVisibleLinks(strongLinks, strongNodeIds) };
    }

    if (mode === "one_hop") {
      var hopAnchorNodeId = anchorNodeId && idSet[anchorNodeId] ? anchorNodeId : nodeIds[0] || null;
      if (!hopAnchorNodeId) return { node_ids: [], links: [] };
      var hopIdSet = {};
      hopIdSet[hopAnchorNodeId] = true;
      for (i = 0; i < scopedLinks.length; i++) {
        var hopEdge = getLinkEndpointIds(scopedLinks[i]);
        if (hopEdge.sourceId === hopAnchorNodeId && idSet[hopEdge.targetId]) hopIdSet[hopEdge.targetId] = true;
        if (hopEdge.targetId === hopAnchorNodeId && idSet[hopEdge.sourceId]) hopIdSet[hopEdge.sourceId] = true;
      }
      var hopNodeIds = nodeIds.filter(function (id) {
        return !!hopIdSet[id];
      });
      return { node_ids: hopNodeIds, links: getVisibleLinks(scopedLinks, hopNodeIds) };
    }

    if (mode === "core") {
      if (nodeIds.length <= 3) return { node_ids: nodeIds.slice(), links: scopedLinks };
      var scores = {};
      for (i = 0; i < nodeIds.length; i++) scores[nodeIds[i]] = 0;
      for (i = 0; i < scopedLinks.length; i++) {
        var coreEdge = getLinkEndpointIds(scopedLinks[i]);
        var weight = Number(scopedLinks[i] && scopedLinks[i].weight);
        var score = Number.isFinite(weight) ? 1 + weight : 1.5;
        if (scores[coreEdge.sourceId] != null) scores[coreEdge.sourceId] += score;
        if (scores[coreEdge.targetId] != null) scores[coreEdge.targetId] += score;
      }
      var coreLimit = Number.isFinite(Number(safe.coreLimit)) ? Number(safe.coreLimit) : Math.max(3, Math.min(8, Math.round(nodeIds.length * 0.5)));
      coreLimit = Math.max(1, Math.min(nodeIds.length, Math.round(coreLimit)));
      var coreNodeIds = sortNodeIdsByScore(nodeIds, scores, nodesById).slice(0, coreLimit);
      return { node_ids: coreNodeIds, links: getVisibleLinks(scopedLinks, coreNodeIds) };
    }

    return { node_ids: nodeIds.slice(), links: scopedLinks };
  }

  function resolveVisibleSnapshot(options) {
    var safe = options && typeof options === "object" ? options : {};
    var nodes = Array.isArray(safe.nodes) ? safe.nodes : [];
    var links = Array.isArray(safe.links) ? safe.links : [];
    var baseNodeIds = Array.isArray(safe.baseNodeIds)
      ? safe.baseNodeIds.slice()
      : nodes.map(function (node) { return node.id; });
    var filteredLinks = filterLinksByTypes(links, safe.filters);
    var scopedLinks = getVisibleLinks(filteredLinks, baseNodeIds);
    var focusResult = applyFocusMode({
      mode: safe.focusMode,
      nodes: nodes,
      links: scopedLinks,
      nodeIds: baseNodeIds,
      anchorNodeId: safe.anchorNodeId,
      highConfidenceThreshold: safe.highConfidenceThreshold,
      coreLimit: safe.coreLimit
    });
    var focusNodeIds = focusResult.node_ids || [];
    if (!focusNodeIds.length && safe.focusMode && safe.focusMode !== "all") {
        return { node_ids: [], nodes: [], links: [], searchIndex: [] };
    }
    if (!focusNodeIds.length) focusNodeIds = baseNodeIds;
    var focusNodes = nodes.filter(function (node) {
      return focusNodeIds.indexOf(node.id) !== -1;
    });
    var searchIndex = buildSearchIndex(focusNodes);
    var query = typeof safe.searchQuery === "string" ? safe.searchQuery.trim() : "";
    var finalNodeIds = query ? applySearchToNodeIds(searchIndex, query) : focusNodeIds;
    var idSet = {};
    for (var i = 0; i < finalNodeIds.length; i++) idSet[finalNodeIds[i]] = true;
    return {
      node_ids: finalNodeIds,
      nodes: nodes.filter(function (node) {
        return !!idSet[node.id];
      }),
      links: finalNodeIds.length
        ? getVisibleLinks(focusResult.links && focusResult.links.length ? focusResult.links : scopedLinks, finalNodeIds)
        : [],
      searchIndex: searchIndex
    };
  }

  function shouldAutoOpenDrawer(mode) {
    return mode === "path";
  }

  var ATLAS_CONFIDENCE_LABELS = {
    EXTRACTED: "直接提取",
    INFERRED: "推断关联",
    AMBIGUOUS: "存在歧义",
    UNVERIFIED: "未核实"
  };

  var ATLAS_TYPE_LABELS = {
    topic: "主题",
    entity: "实体",
    source: "来源"
  };

  var ATLAS_TYPE_KINDS = {
    topic: "TOPIC",
    entity: "ENTITY",
    source: "SOURCE"
  };

  function normalizeAtlasType(type) {
    var normalized = String(type || "entity").toLowerCase();
    return ATLAS_TYPE_LABELS[normalized] ? normalized : "entity";
  }

  function normalizeAtlasConfidence(confidence) {
    var normalized = String(confidence || "EXTRACTED").toUpperCase();
    return ATLAS_CONFIDENCE_LABELS[normalized] ? normalized : "EXTRACTED";
  }

  function atlasConfidenceLabel(confidence) {
    var normalized = normalizeAtlasConfidence(confidence);
    return ATLAS_CONFIDENCE_LABELS[normalized];
  }

  function atlasTypeLabel(type) {
    var normalized = normalizeAtlasType(type);
    return ATLAS_TYPE_LABELS[normalized];
  }

  function atlasNodeKind(type) {
    var normalized = normalizeAtlasType(type);
    return ATLAS_TYPE_KINDS[normalized];
  }

  function clampAtlasNumber(value, fallback, min, max) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) numeric = fallback;
    if (Number.isFinite(Number(min))) numeric = Math.max(Number(min), numeric);
    if (Number.isFinite(Number(max))) numeric = Math.min(Number(max), numeric);
    return numeric;
  }

  function normalizeAtlasViewportSize(size) {
    var safe = size && typeof size === "object" ? size : {};
    return {
      width: clampAtlasNumber(safe.width, ATLAS_WORLD_WIDTH, 1, 100000),
      height: clampAtlasNumber(safe.height, ATLAS_WORLD_HEIGHT, 1, 100000)
    };
  }

  function normalizeAtlasViewport(viewport) {
    var safe = viewport && typeof viewport === "object" ? viewport : {};
    return {
      x: clampAtlasNumber(safe.x, 0, -1000000, 1000000),
      y: clampAtlasNumber(safe.y, 0, -1000000, 1000000),
      scale: clampAtlasNumber(safe.scale, 1, ATLAS_MIN_SCALE, ATLAS_MAX_SCALE)
    };
  }

  function atlasNodePoint(node) {
    var safe = node && typeof node === "object" ? node : {};
    return {
      x: clampAtlasNumber(safe.x, 50, 0, 100) / 100 * ATLAS_WORLD_WIDTH,
      y: clampAtlasNumber(safe.y, 50, 0, 100) / 100 * ATLAS_WORLD_HEIGHT
    };
  }

  function getAtlasModelBounds(nodes, padding) {
    var list = Array.isArray(nodes) ? nodes : [];
    var pad = Number.isFinite(Number(padding)) ? Math.max(0, Number(padding)) : 48;
    if (!list.length) {
      return {
        x: 0,
        y: 0,
        width: ATLAS_WORLD_WIDTH,
        height: ATLAS_WORLD_HEIGHT,
        minX: 0,
        minY: 0,
        maxX: ATLAS_WORLD_WIDTH,
        maxY: ATLAS_WORLD_HEIGHT
      };
    }

    var minX = ATLAS_WORLD_WIDTH;
    var minY = ATLAS_WORLD_HEIGHT;
    var maxX = 0;
    var maxY = 0;
    list.forEach(function (node) {
      var point = atlasNodePoint(node);
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    });

    minX = clampAtlasNumber(minX - pad, 0, 0, ATLAS_WORLD_WIDTH);
    minY = clampAtlasNumber(minY - pad, 0, 0, ATLAS_WORLD_HEIGHT);
    maxX = clampAtlasNumber(maxX + pad, ATLAS_WORLD_WIDTH, 0, ATLAS_WORLD_WIDTH);
    maxY = clampAtlasNumber(maxY + pad, ATLAS_WORLD_HEIGHT, 0, ATLAS_WORLD_HEIGHT);

    return {
      x: minX,
      y: minY,
      width: Math.max(1, maxX - minX),
      height: Math.max(1, maxY - minY),
      minX: minX,
      minY: minY,
      maxX: maxX,
      maxY: maxY
    };
  }

  function clampAtlasViewport(viewport, viewportSize, options) {
    var size = normalizeAtlasViewportSize(viewportSize);
    var safe = normalizeAtlasViewport(viewport);
    var opts = options && typeof options === "object" ? options : {};
    var minScale = clampAtlasNumber(opts.minScale, ATLAS_MIN_SCALE, 0.1, ATLAS_MAX_SCALE);
    var maxScale = clampAtlasNumber(opts.maxScale, ATLAS_MAX_SCALE, minScale, 10);
    var marginX = clampAtlasNumber(opts.marginX, size.width * 0.38, 0, size.width);
    var marginY = clampAtlasNumber(opts.marginY, size.height * 0.38, 0, size.height);
    var scale = clampAtlasNumber(safe.scale, 1, minScale, maxScale);
    var scaledWidth = size.width * scale;
    var scaledHeight = size.height * scale;
    var minX = size.width - scaledWidth - marginX;
    var maxX = marginX;
    var minY = size.height - scaledHeight - marginY;
    var maxY = marginY;

    if (scaledWidth <= size.width) {
      var centerX = (size.width - scaledWidth) / 2;
      minX = centerX - marginX;
      maxX = centerX + marginX;
    }
    if (scaledHeight <= size.height) {
      var centerY = (size.height - scaledHeight) / 2;
      minY = centerY - marginY;
      maxY = centerY + marginY;
    }

    return {
      x: clampAtlasNumber(safe.x, 0, minX, maxX),
      y: clampAtlasNumber(safe.y, 0, minY, maxY),
      scale: scale
    };
  }

  function fitAtlasViewport(bounds, viewportSize, options) {
    var safeBounds = bounds && typeof bounds === "object" ? bounds : getAtlasModelBounds([]);
    var size = normalizeAtlasViewportSize(viewportSize);
    var opts = options && typeof options === "object" ? options : {};
    var padding = clampAtlasNumber(opts.padding, 0.84, 0.2, 1);
    var minScale = clampAtlasNumber(opts.minScale, ATLAS_MIN_SCALE, 0.1, ATLAS_MAX_SCALE);
    var maxScale = clampAtlasNumber(opts.maxScale, 2.15, minScale, ATLAS_MAX_SCALE);
    var widthScale = ATLAS_WORLD_WIDTH * padding / Math.max(1, safeBounds.width || 1);
    var heightScale = ATLAS_WORLD_HEIGHT * padding / Math.max(1, safeBounds.height || 1);
    var scale = clampAtlasNumber(Math.min(widthScale, heightScale), 1, minScale, maxScale);
    var centerX = (safeBounds.minX != null && safeBounds.maxX != null)
      ? (safeBounds.minX + safeBounds.maxX) / 2
      : (safeBounds.x || 0) + (safeBounds.width || ATLAS_WORLD_WIDTH) / 2;
    var centerY = (safeBounds.minY != null && safeBounds.maxY != null)
      ? (safeBounds.minY + safeBounds.maxY) / 2
      : (safeBounds.y || 0) + (safeBounds.height || ATLAS_WORLD_HEIGHT) / 2;

    return clampAtlasViewport({
      x: size.width / 2 - scale * (centerX / ATLAS_WORLD_WIDTH * size.width),
      y: size.height / 2 - scale * (centerY / ATLAS_WORLD_HEIGHT * size.height),
      scale: scale
    }, size, opts);
  }

  function centerAtlasViewportOnPoint(point, viewportSize, scale, options) {
    var safePoint = point && typeof point === "object" ? point : { x: ATLAS_WORLD_WIDTH / 2, y: ATLAS_WORLD_HEIGHT / 2 };
    var size = normalizeAtlasViewportSize(viewportSize);
    var viewportScale = clampAtlasNumber(scale, 1, ATLAS_MIN_SCALE, ATLAS_MAX_SCALE);
    return clampAtlasViewport({
      x: size.width / 2 - viewportScale * (safePoint.x / ATLAS_WORLD_WIDTH * size.width),
      y: size.height / 2 - viewportScale * (safePoint.y / ATLAS_WORLD_HEIGHT * size.height),
      scale: viewportScale
    }, size, options);
  }

  function zoomAtlasViewport(viewport, factor, screenPoint, viewportSize, options) {
    var size = normalizeAtlasViewportSize(viewportSize);
    var safe = normalizeAtlasViewport(viewport);
    var point = screenPoint && typeof screenPoint === "object"
      ? { x: clampAtlasNumber(screenPoint.x, size.width / 2, 0, size.width), y: clampAtlasNumber(screenPoint.y, size.height / 2, 0, size.height) }
      : { x: size.width / 2, y: size.height / 2 };
    var zoomFactor = clampAtlasNumber(factor, 1, 0.2, 5);
    var opts = options && typeof options === "object" ? options : {};
    var minScale = clampAtlasNumber(opts.minScale, ATLAS_MIN_SCALE, 0.1, ATLAS_MAX_SCALE);
    var maxScale = clampAtlasNumber(opts.maxScale, ATLAS_MAX_SCALE, minScale, 10);
    var nextScale = clampAtlasNumber(safe.scale * zoomFactor, safe.scale, minScale, maxScale);
    var ratio = nextScale / safe.scale;
    return clampAtlasViewport({
      x: point.x - (point.x - safe.x) * ratio,
      y: point.y - (point.y - safe.y) * ratio,
      scale: nextScale
    }, size, opts);
  }

  function atlasViewportRect(viewport, viewportSize) {
    var size = normalizeAtlasViewportSize(viewportSize);
    var safe = normalizeAtlasViewport(viewport);
    var x = (0 - safe.x) / safe.scale / size.width * ATLAS_WORLD_WIDTH;
    var y = (0 - safe.y) / safe.scale / size.height * ATLAS_WORLD_HEIGHT;
    var width = size.width / safe.scale / size.width * ATLAS_WORLD_WIDTH;
    var height = size.height / safe.scale / size.height * ATLAS_WORLD_HEIGHT;
    var minX = clampAtlasNumber(x, 0, 0, ATLAS_WORLD_WIDTH);
    var minY = clampAtlasNumber(y, 0, 0, ATLAS_WORLD_HEIGHT);
    var maxX = clampAtlasNumber(x + width, ATLAS_WORLD_WIDTH, 0, ATLAS_WORLD_WIDTH);
    var maxY = clampAtlasNumber(y + height, ATLAS_WORLD_HEIGHT, 0, ATLAS_WORLD_HEIGHT);
    return {
      x: minX,
      y: minY,
      width: Math.max(1, maxX - minX),
      height: Math.max(1, maxY - minY),
      minX: minX,
      minY: minY,
      maxX: maxX,
      maxY: maxY
    };
  }

  function atlasPointToMinimap(point) {
    var safePoint = point && typeof point === "object" ? point : { x: 0, y: 0 };
    return {
      x: MINIMAP_VIEWBOX.x + clampAtlasNumber(safePoint.x, 0, 0, ATLAS_WORLD_WIDTH) / ATLAS_WORLD_WIDTH * MINIMAP_VIEWBOX.width,
      y: MINIMAP_VIEWBOX.y + clampAtlasNumber(safePoint.y, 0, 0, ATLAS_WORLD_HEIGHT) / ATLAS_WORLD_HEIGHT * MINIMAP_VIEWBOX.height
    };
  }

  function minimapPointToAtlasPoint(point) {
    var safePoint = point && typeof point === "object" ? point : { x: MINIMAP_VIEWBOX.x, y: MINIMAP_VIEWBOX.y };
    return {
      x: clampAtlasNumber((safePoint.x - MINIMAP_VIEWBOX.x) / MINIMAP_VIEWBOX.width * ATLAS_WORLD_WIDTH, 0, 0, ATLAS_WORLD_WIDTH),
      y: clampAtlasNumber((safePoint.y - MINIMAP_VIEWBOX.y) / MINIMAP_VIEWBOX.height * ATLAS_WORLD_HEIGHT, 0, 0, ATLAS_WORLD_HEIGHT)
    };
  }

  function atlasViewportToMinimapRect(viewport, viewportSize) {
    var rect = atlasViewportRect(viewport, viewportSize);
    var topLeft = atlasPointToMinimap({ x: rect.x, y: rect.y });
    var bottomRight = atlasPointToMinimap({ x: rect.x + rect.width, y: rect.y + rect.height });
    return {
      x: topLeft.x,
      y: topLeft.y,
      width: Math.max(2, bottomRight.x - topLeft.x),
      height: Math.max(2, bottomRight.y - topLeft.y)
    };
  }

  function atlasEndpointId(value) {
    if (value && typeof value === "object" && value.id != null) return String(value.id);
    return value == null ? "" : String(value);
  }

  function stripAtlasMarkdown(raw) {
    return String(raw || "")
      .replace(/^---[\s\S]*?---\s*/m, "")
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/!\[[^\]]*\]\([^)]+\)/g, " ")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\[\[([^\]|]+)\|?([^\]]*)\]\]/g, function (_, target, label) {
        return label || target;
      })
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/^[-*+]\s+/gm, "")
      .replace(/^\d+\.\s+/gm, "")
      .replace(/[*_`>#]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function deriveAtlasSummary(node, content) {
    var explicitSummary = node && node.summary != null ? String(node.summary).trim() : "";
    if (explicitSummary) return explicitSummary.length > 170 ? explicitSummary.slice(0, 170).trim() + "…" : explicitSummary;
    var summarySource = String(content || (node && node.content) || "").replace(/^#\s+.*(?:\r?\n)+/, "");
    var stripped = stripAtlasMarkdown(summarySource);
    if (!stripped) return "";
    return stripped.length > 170 ? stripped.slice(0, 170).trim() + "…" : stripped;
  }

  function normalizeAtlasNode(rawNode, index) {
    var raw = rawNode && typeof rawNode === "object" ? rawNode : {};
    var id = raw.id == null ? "node-" + index : String(raw.id);
    var label = raw.label == null || String(raw.label).trim() === "" ? id : String(raw.label).trim();
    var content = raw.content == null ? "" : String(raw.content);
    var type = normalizeAtlasType(raw.type);
    var community = raw.community == null || raw.community === "" ? "_none" : String(raw.community);
    var x = Number(raw.x);
    var y = Number(raw.y);
    var hasX = (typeof raw.x === "number" || (typeof raw.x === "string" && raw.x.trim() !== "")) && Number.isFinite(x);
    var hasY = (typeof raw.y === "number" || (typeof raw.y === "string" && raw.y.trim() !== "")) && Number.isFinite(y);
    return {
      id: id,
      label: label,
      type: type,
      type_label: atlasTypeLabel(type),
      kind: atlasNodeKind(type),
      community: community,
      source_path: raw.source_path || raw.source || raw.path || "",
      confidence: normalizeAtlasConfidence(raw.confidence || raw.type_confidence),
      confidence_label: atlasConfidenceLabel(raw.confidence || raw.type_confidence),
      content: content,
      summary: deriveAtlasSummary(raw, content),
      unavailable: raw.unavailable === true || raw.available === false,
      degree: 0,
      weight: clampAtlasNumber(raw.weight != null ? raw.weight : raw.score, 50, 0, 100),
      priority: 0,
      idx: index,
      x: hasX ? x : null,
      y: hasY ? y : null
    };
  }

  function normalizeAtlasEdge(rawEdge, index) {
    var raw = rawEdge && typeof rawEdge === "object" ? rawEdge : {};
    var sourceId = atlasEndpointId(raw.from != null ? raw.from : raw.source);
    var targetId = atlasEndpointId(raw.to != null ? raw.to : raw.target);
    return {
      id: raw.id == null ? "edge-" + index : String(raw.id),
      source: sourceId,
      target: targetId,
      from: sourceId,
      to: targetId,
      type: normalizeAtlasConfidence(raw.type || raw.confidence),
      confidence_label: atlasConfidenceLabel(raw.type || raw.confidence),
      weight: clampAtlasNumber(raw.weight, 0.6, 0, 1),
      signals: raw.signals && typeof raw.signals === "object" ? raw.signals : {},
      source_signal_available: raw.source_signal_available === true
    };
  }

  function buildAtlasSearchHaystack(node) {
    return [
      node && node.label,
      node && node.id,
      node && node.type_label,
      node && node.source_path,
      node && node.summary,
      node && stripAtlasMarkdown(node.content)
    ].join("\n").toLowerCase();
  }

  function buildAtlasSearchIndex(nodes) {
    if (!Array.isArray(nodes)) return [];
    return nodes.map(function (node) {
      return { node: node, haystack: buildAtlasSearchHaystack(node) };
    });
  }

  function deriveAtlasCommunities(rawGraph, nodes, communityById) {
    var learning = normalizeLearning(rawGraph && rawGraph.learning);
    var fromLearning = Array.isArray(learning.communities) ? learning.communities : [];
    var communities = [];
    var seen = {};

    fromLearning.forEach(function (community) {
      if (!community || community.id == null) return;
      var id = String(community.id);
      var derived = communityById[id] || { nodes: [] };
      seen[id] = true;
      communities.push({
        id: id,
        label: community.label || id,
        node_count: Number.isFinite(Number(community.node_count)) ? Number(community.node_count) : derived.nodes.length,
        source_count: Number.isFinite(Number(community.source_count)) ? Number(community.source_count) : 0,
        is_primary: community.is_primary === true,
        recommended_start_node_id: community.recommended_start_node_id || null,
        color_index: communities.length
      });
    });

    Object.keys(communityById).sort().forEach(function (id) {
      if (seen[id]) return;
      var group = communityById[id];
      var topic = group.nodes.find(function (node) { return node.type === "topic"; });
      communities.push({
        id: id,
        label: id === "_none" ? "未分组" : (topic && topic.label) || id,
        node_count: group.nodes.length,
        source_count: group.nodes.filter(function (node) { return node.type === "source"; }).length,
        is_primary: communities.length === 0,
        recommended_start_node_id: null,
        color_index: communities.length
      });
    });

    communities.sort(function (left, right) {
      if (!!right.is_primary !== !!left.is_primary) return right.is_primary ? 1 : -1;
      if ((right.node_count || 0) !== (left.node_count || 0)) return (right.node_count || 0) - (left.node_count || 0);
      return String(left.label || left.id).localeCompare(String(right.label || right.id));
    });
    communities.forEach(function (community, index) {
      community.color_index = index;
    });
    return communities;
  }

  function buildAtlasStarts(rawGraph, nodes, byId, communities) {
    var starts = [];
    var seen = {};
    function add(id, reason) {
      if (id == null) return;
      var nodeId = String(id);
      if (!byId[nodeId] || seen[nodeId]) return;
      seen[nodeId] = true;
      starts.push({ node: byId[nodeId], reason: reason || "" });
    }
    var learning = normalizeLearning(rawGraph && rawGraph.learning);
    add(learning.entry && learning.entry.recommended_start_node_id, "全局推荐起点");
    communities.forEach(function (community) {
      add(community.recommended_start_node_id, community.label + " · 推荐起点");
    });
    nodes.slice().sort(function (left, right) {
      return (right.priority || 0) - (left.priority || 0);
    }).forEach(function (node) {
      if (starts.length < 6) add(node.id, atlasTypeLabel(node.type) + " · " + atlasConfidenceLabel(node.confidence));
    });
    return starts.slice(0, 6);
  }

  function normalizeAtlasInsights(insights) {
    var safe = insights && typeof insights === "object" ? insights : {};
    return {
      surprising_connections: Array.isArray(safe.surprising_connections) ? safe.surprising_connections : [],
      isolated_nodes: Array.isArray(safe.isolated_nodes) ? safe.isolated_nodes : [],
      bridge_nodes: Array.isArray(safe.bridge_nodes) ? safe.bridge_nodes : [],
      sparse_communities: Array.isArray(safe.sparse_communities) ? safe.sparse_communities : [],
      meta: safe.meta && typeof safe.meta === "object" ? safe.meta : { degraded: false }
    };
  }

  function buildAtlasModel(rawGraph) {
    var raw = rawGraph && typeof rawGraph === "object" ? rawGraph : {};
    var nodes = Array.isArray(raw.nodes) ? raw.nodes.map(normalizeAtlasNode) : [];
    var byId = {};
    var communityById = {};
    nodes.forEach(function (node) {
      byId[node.id] = node;
      if (!communityById[node.community]) communityById[node.community] = { id: node.community, nodes: [] };
      communityById[node.community].nodes.push(node);
    });

    var edges = (Array.isArray(raw.edges) ? raw.edges : [])
      .map(normalizeAtlasEdge)
      .filter(function (edge) {
        return !!(byId[edge.source] && byId[edge.target]);
      });

    edges.forEach(function (edge) {
      byId[edge.source].degree += 1;
      byId[edge.target].degree += 1;
    });
    nodes.forEach(function (node) {
      node.priority = node.degree * 12 + node.weight + (node.type === "topic" ? 12 : node.type === "source" ? 6 : 0);
    });

    var communities = deriveAtlasCommunities(raw, nodes, communityById);
    var communityMap = {};
    communities.forEach(function (community) {
      communityMap[community.id] = community;
    });

    return {
      meta: {
        wiki_title: raw.meta && raw.meta.wiki_title ? String(raw.meta.wiki_title) : "知识库",
        total_nodes: nodes.length,
        total_edges: edges.length,
        build_date: raw.meta && raw.meta.build_date ? String(raw.meta.build_date) : ""
      },
      nodes: nodes,
      edges: edges,
      byId: byId,
      communities: communities,
      communityById: communityMap,
      starts: buildAtlasStarts(raw, nodes, byId, communities),
      searchIndex: buildAtlasSearchIndex(nodes),
      insights: normalizeAtlasInsights(raw.insights)
    };
  }

  function deriveAtlasLayout(model) {
    var safe = model && typeof model === "object" ? model : { nodes: [], communities: [] };
    var centers = [
      { x: 50, y: 48 },
      { x: 30, y: 34 },
      { x: 70, y: 36 },
      { x: 30, y: 72 },
      { x: 72, y: 70 },
      { x: 18, y: 52 },
      { x: 84, y: 52 },
      { x: 50, y: 78 }
    ];
    var communityIndex = {};
    (safe.communities || []).forEach(function (community, index) {
      communityIndex[community.id] = index;
    });
    var grouped = {};
    (safe.nodes || []).forEach(function (node) {
      if (!grouped[node.community]) grouped[node.community] = [];
      grouped[node.community].push(node);
    });
    Object.keys(grouped).forEach(function (communityId) {
      grouped[communityId].sort(function (left, right) {
        return (right.priority || 0) - (left.priority || 0);
      });
      var center = centers[(communityIndex[communityId] || 0) % centers.length];
      var count = grouped[communityId].length;
      grouped[communityId].forEach(function (node, index) {
        if (node.x != null && node.y != null && Number.isFinite(Number(node.x)) && Number.isFinite(Number(node.y))) {
          node.x = clampAtlasNumber(node.x, center.x, 5, 95);
          node.y = clampAtlasNumber(node.y, center.y, 8, 92);
          return;
        }
        var ring = Math.floor(index / 8);
        var ringIndex = index % 8;
        var angle = ((ringIndex / Math.min(8, Math.max(1, count))) * Math.PI * 2) + ring * 0.42;
        var radiusX = 7 + ring * 5 + Math.min(5, count * 0.16);
        var radiusY = 5 + ring * 4 + Math.min(4, count * 0.12);
        node.x = clampAtlasNumber(center.x + Math.cos(angle) * radiusX, center.x, 5, 95);
        node.y = clampAtlasNumber(center.y + Math.sin(angle) * radiusY, center.y, 8, 92);
      });
    });
    return {
      nodes: (safe.nodes || []).slice(),
      edges: (safe.edges || []).slice(),
      nodePositions: (safe.nodes || []).reduce(function (out, node) {
        out[node.id] = { x: node.x, y: node.y };
        return out;
      }, {})
    };
  }

  function getAtlasDensityMode(count) {
    var nodeCount = Number.isFinite(Number(count)) ? Number(count) : 0;
    if (nodeCount > 500) return "overview";
    if (nodeCount > 200) return "point-plus-focus";
    if (nodeCount > 80) return "compact-card";
    return "card";
  }

  function atlasLabelBudget(mode, count) {
    if (mode === "overview") return 40;
    if (mode === "point-plus-focus") return 60;
    if (mode === "compact-card") return Math.min(120, count);
    return count;
  }

  function atlasEdgeBudget(mode, count) {
    if (mode === "overview") return 1000;
    if (mode === "point-plus-focus") return 800;
    return count;
  }

  function resolveAtlasVisibleSnapshot(model, layout, uiState) {
    var safeModel = model && typeof model === "object" ? model : buildAtlasModel({});
    var safeUI = uiState && typeof uiState === "object" ? uiState : {};
    var activeCommunityId = safeUI.activeCommunityId == null ? "all" : String(safeUI.activeCommunityId);
    var query = typeof safeUI.query === "string" ? safeUI.query.trim().toLowerCase() : "";
    var focusMode = safeUI.focusMode || "all";
    var selectedNodeId = safeUI.selectedNodeId == null ? null : String(safeUI.selectedNodeId);
    var filters = safeUI.filters && typeof safeUI.filters === "object" ? safeUI.filters : {};

    var baseNodes = safeModel.nodes.filter(function (node) {
      if (activeCommunityId !== "all" && node.community !== activeCommunityId) return false;
      if (focusMode === "source" && node.type !== "source") return false;
      return true;
    });

    if (focusMode === "core" && baseNodes.length > 8) {
      var keepCount = Math.max(8, Math.ceil(baseNodes.length * 0.45));
      var keep = {};
      baseNodes.slice().sort(function (left, right) {
        return (right.priority || 0) - (left.priority || 0);
      }).slice(0, keepCount).forEach(function (node) {
        keep[node.id] = true;
      });
      if (selectedNodeId && safeModel.byId[selectedNodeId]) keep[selectedNodeId] = true;
      baseNodes = baseNodes.filter(function (node) { return !!keep[node.id]; });
    }

    var baseIdSet = {};
    baseNodes.forEach(function (node) { baseIdSet[node.id] = true; });
    var searchIndex = buildAtlasSearchIndex(baseNodes);
    var matchedIds = {};
    var visibleNodes = !query
      ? baseNodes
      : searchIndex.filter(function (entry) {
          return entry.haystack.indexOf(query) !== -1;
        }).map(function (entry) {
          matchedIds[entry.node.id] = true;
          return entry.node;
        });
    var visibleIdSet = {};
    visibleNodes.forEach(function (node) { visibleIdSet[node.id] = true; });

    var visibleEdges = safeModel.edges.filter(function (edge) {
      var edgeType = edge.type || "EXTRACTED";
      if (filters[edgeType] === false) return false;
      return !!(visibleIdSet[edge.source] && visibleIdSet[edge.target]);
    });

    var densityMode = getAtlasDensityMode(visibleNodes.length);
    var labelBudget = atlasLabelBudget(densityMode, visibleNodes.length);
    var labelNodeIds = {};
    var startNodeIds = {};
    var importantNodeIds = {};
    var visibleStartEntries = safeModel.starts.filter(function (entry) {
      return !!(entry && entry.node && visibleIdSet[entry.node.id]) &&
        (activeCommunityId === "all" || entry.node.community === activeCommunityId);
    });

    visibleStartEntries.forEach(function (entry) {
      startNodeIds[entry.node.id] = true;
      importantNodeIds[entry.node.id] = true;
    });

    visibleNodes.slice().sort(function (left, right) {
      return (right.priority || 0) - (left.priority || 0);
    }).slice(0, Math.max(0, Math.min(8, Math.ceil(visibleNodes.length * 0.08)))).forEach(function (node) {
      importantNodeIds[node.id] = true;
    });

    visibleNodes.slice().sort(function (left, right) {
      var leftForced = (selectedNodeId === left.id || matchedIds[left.id] || importantNodeIds[left.id]) ? 1 : 0;
      var rightForced = (selectedNodeId === right.id || matchedIds[right.id] || importantNodeIds[right.id]) ? 1 : 0;
      if (rightForced !== leftForced) return rightForced - leftForced;
      return (right.priority || 0) - (left.priority || 0);
    }).slice(0, labelBudget).forEach(function (node) {
      labelNodeIds[node.id] = true;
    });
    if (selectedNodeId && visibleIdSet[selectedNodeId]) labelNodeIds[selectedNodeId] = true;
    Object.keys(matchedIds).forEach(function (id) {
      if (visibleIdSet[id]) {
        labelNodeIds[id] = true;
        importantNodeIds[id] = true;
      }
    });
    Object.keys(startNodeIds).forEach(function (id) {
      if (visibleIdSet[id]) labelNodeIds[id] = true;
    });
    if (selectedNodeId && visibleIdSet[selectedNodeId]) importantNodeIds[selectedNodeId] = true;

    var edgeBudget = atlasEdgeBudget(densityMode, visibleEdges.length);
    visibleEdges = visibleEdges.slice().sort(function (left, right) {
      var leftSelected = selectedNodeId && (left.source === selectedNodeId || left.target === selectedNodeId) ? 1 : 0;
      var rightSelected = selectedNodeId && (right.source === selectedNodeId || right.target === selectedNodeId) ? 1 : 0;
      if (rightSelected !== leftSelected) return rightSelected - leftSelected;
      return (right.weight || 0) - (left.weight || 0);
    }).slice(0, edgeBudget);

    return {
      node_ids: visibleNodes.map(function (node) { return node.id; }),
      nodes: visibleNodes,
      edges: visibleEdges,
      links: visibleEdges,
      searchIndex: searchIndex,
      densityMode: densityMode,
      labelNodeIds: labelNodeIds,
      matchedNodeIds: matchedIds,
      importantNodeIds: importantNodeIds,
      startNodeIds: startNodeIds,
      starts: visibleStartEntries,
      counts: {
        visible_nodes: visibleNodes.length,
        visible_edges: visibleEdges.length,
        total_nodes: safeModel.nodes.length,
        total_edges: safeModel.edges.length,
        total_communities: safeModel.communities.length
      }
    };
  }

  function resolveAtlasSelectedNodeId(model, visibleSnapshot, selectedNodeId) {
    var safeModel = model && typeof model === "object" ? model : buildAtlasModel({});
    var selected = selectedNodeId == null ? null : String(selectedNodeId);
    var visible = visibleSnapshot && typeof visibleSnapshot === "object" ? visibleSnapshot : null;
    var visibleIds = {};
    if (visible && Array.isArray(visible.node_ids)) {
      visible.node_ids.forEach(function (id) { visibleIds[String(id)] = true; });
    }

    if (selected && safeModel.byId && safeModel.byId[selected] && (!visible || visibleIds[selected])) {
      return selected;
    }
    return null;
  }

  var helpers = {
    splitLabelGraphemes: splitLabelGraphemes,
    labelCharWidth: labelCharWidth,
    measureLabelWidth: measureLabelWidth,
    truncateLabel: truncateLabel,
    cardDims: cardDims,
    createSafeStorage: createSafeStorage,
    getWikiStorageNamespace: getWikiStorageNamespace,
    defaultQueue: defaultQueue,
    normalizeQueue: normalizeQueue,
    toggleQueueFavorite: toggleQueueFavorite,
    appendQueueNote: appendQueueNote,
    summarizeQueue: summarizeQueue,
    defaultLearning: defaultLearning,
    normalizeLearning: normalizeLearning,
    resolveInitialMode: resolveInitialMode,
    getCommunityNodeIds: getCommunityNodeIds,
    getVisibleNodeIds: getVisibleNodeIds,
    getVisibleLinks: getVisibleLinks,
    buildSearchHaystack: buildSearchHaystack,
    buildSearchIndex: buildSearchIndex,
    filterLinksByTypes: filterLinksByTypes,
    applySearchToNodeIds: applySearchToNodeIds,
    applyFocusMode: applyFocusMode,
    resolveVisibleSnapshot: resolveVisibleSnapshot,
    shouldAutoOpenDrawer: shouldAutoOpenDrawer,
    buildAtlasModel: buildAtlasModel,
    deriveAtlasLayout: deriveAtlasLayout,
    resolveAtlasVisibleSnapshot: resolveAtlasVisibleSnapshot,
    resolveAtlasSelectedNodeId: resolveAtlasSelectedNodeId,
    getAtlasDensityMode: getAtlasDensityMode,
    normalizeAtlasViewport: normalizeAtlasViewport,
    atlasNodePoint: atlasNodePoint,
    getAtlasModelBounds: getAtlasModelBounds,
    clampAtlasViewport: clampAtlasViewport,
    fitAtlasViewport: fitAtlasViewport,
    centerAtlasViewportOnPoint: centerAtlasViewportOnPoint,
    zoomAtlasViewport: zoomAtlasViewport,
    atlasViewportRect: atlasViewportRect,
    atlasPointToMinimap: atlasPointToMinimap,
    minimapPointToAtlasPoint: minimapPointToAtlasPoint,
    atlasViewportToMinimapRect: atlasViewportToMinimapRect,
    atlasConfidenceLabel: atlasConfidenceLabel,
    atlasTypeLabel: atlasTypeLabel,
    atlasNodeKind: atlasNodeKind,
    stripAtlasMarkdown: stripAtlasMarkdown
  };

  root.WikiGraphWashHelpers = helpers;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = helpers;
  }
})(typeof window !== "undefined" ? window : this);
