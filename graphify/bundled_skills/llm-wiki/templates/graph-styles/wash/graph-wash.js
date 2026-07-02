/* DEPRECATED: Legacy wash runtime retained for one release cycle after Stage 4 engine HTML migration. Do not extend; use packages/graph-engine instead. */
/* ============================================================
   Knowledge Graph - Oriental editorial atlas runtime
   ============================================================ */
(function () {
  "use strict";

  const helpers = window.WikiGraphWashHelpers;
  if (!helpers) {
    console.error("[wiki] graph-wash-helpers.js is missing or failed to load");
    return;
  }

  const {
    createSafeStorage,
    getWikiStorageNamespace,
    defaultQueue,
    normalizeQueue,
    toggleQueueFavorite,
    appendQueueNote,
    summarizeQueue,
    buildAtlasModel,
    deriveAtlasLayout,
    resolveAtlasVisibleSnapshot,
    resolveAtlasSelectedNodeId,
    atlasNodePoint,
    getAtlasModelBounds,
    fitAtlasViewport,
    centerAtlasViewportOnPoint,
    zoomAtlasViewport,
    atlasViewportToMinimapRect,
    atlasPointToMinimap,
    minimapPointToAtlasPoint,
    atlasConfidenceLabel,
    atlasTypeLabel,
    atlasNodeKind,
    stripAtlasMarkdown
  } = helpers;

  const DENSITY_SMALL_LIMIT = 80;
  const DENSITY_MEDIUM_LIMIT = 200;
  const DENSITY_LARGE_LIMIT = 500;
  const QUEUE_NOTE_LIMIT = 50;
  const NOTE_EXCERPT_LIMIT = 140;
  const COMMUNITY_COLORS = ["#8b2e24", "#315f72", "#4b7564", "#b7791f", "#6f557f", "#3e6b4b", "#9b6a36", "#5d6f91"];

  const dataEl = document.getElementById("graph-data");
  let DATA;
  let dataError = false;
  try {
    DATA = dataEl ? JSON.parse(dataEl.textContent) : window.SAMPLE_GRAPH;
  } catch (err) {
    console.error("[wiki] graph data parse failed:", err);
    DATA = { meta: {}, nodes: [], edges: [], insights: { meta: { degraded: true } } };
    dataError = true;
  }

  const app = document.getElementById("app");
  const atlas = document.getElementById("atlas");
  const nodeLayer = document.getElementById("node-layer");
  const edgeLayer = document.getElementById("edge-layer");
  const communityList = document.getElementById("community-list");
  const startList = document.getElementById("start-list");
  const searchInput = document.getElementById("search");
  const noResults = document.getElementById("no-results");
  const canvasTitle = document.getElementById("canvas-title");
  const canvasSubtitle = document.getElementById("canvas-subtitle");
  const insightTitle = document.getElementById("insight-title");
  const insightCopy = document.getElementById("insight-copy");
  const drawer = document.getElementById("drawer");
  const drawerNeighbors = document.getElementById("neighbor-details");
  const drawerNeighborsHeading = drawerNeighbors ? drawerNeighbors.querySelector("summary") : null;
  const neighborList = document.getElementById("neighbor-list");
  const minimapEl = document.getElementById("minimap");
  const minimapToggle = document.getElementById("minimap-toggle");
  const minimapSvg = document.getElementById("mini-map-svg");

  if (!atlas || !nodeLayer || !edgeLayer) {
    console.error("[wiki] atlas shell is incomplete");
    return;
  }

  let rawLocalStorage = null;
  try {
    rawLocalStorage = window.localStorage;
  } catch (_) {}

  const atlasModel = buildAtlasModel(DATA);
  const atlasLayout = deriveAtlasLayout(atlasModel);
  const safeLocalStorage = createSafeStorage(rawLocalStorage, console.warn);
  const storageNamespace = getWikiStorageNamespace(atlasModel.meta, window.location && window.location.pathname);

  const state = {
    atlasModel,
    atlasLayout,
    queue: loadQueueState(),
    ui: {
      selectedNodeId: null,
      activeCommunityId: "all",
      focusMode: "all",
      query: "",
      dimUnselected: false,
      dataMode: dataError ? "error" : (atlasModel.nodes.length ? "normal" : "empty"),
      neighborExpanded: false,
      filters: { EXTRACTED: true, INFERRED: true, AMBIGUOUS: true, UNVERIFIED: true }
    },
    viewport: { x: 0, y: 0, scale: 1 },
    viewportReady: false,
    visible: null
  };

  let viewportPaintFrame = 0;
  let panState = null;

  function queueStorageKey(name) {
    return storageNamespace + ":" + name;
  }

  function loadQueueState() {
    const raw = safeLocalStorage.get(queueStorageKey("queue"));
    if (!raw) return defaultQueue();
    try {
      return normalizeQueue(JSON.parse(raw));
    } catch (err) {
      console.warn("[wiki] queue storage parse failed:", err);
      return defaultQueue();
    }
  }

  function persistQueueState() {
    safeLocalStorage.set(queueStorageKey("queue"), JSON.stringify(state.queue));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[ch]);
  }

  function clampWeight(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 0.6;
    return Math.max(0, Math.min(1, numeric));
  }

  function edgeStrokeWidth(edge) {
    return 1.1 + clampWeight(edge && edge.weight) * 1.8;
  }

  function edgeOpacity(edge) {
    return 0.32 + clampWeight(edge && edge.weight) * 0.44;
  }

  function edgeStrengthSize(edge) {
    return 6 + clampWeight(edge && edge.weight) * 8;
  }

  function currentDensityMode() {
    return state.visible ? state.visible.densityMode : "card";
  }

  function communityColor(communityId) {
    const community = state.atlasModel.communityById[communityId];
    const index = community ? community.color_index || 0 : 0;
    return COMMUNITY_COLORS[index % COMMUNITY_COLORS.length];
  }

  function getSelectedNode() {
    const selectedNodeId = resolveAtlasSelectedNodeId(state.atlasModel, state.visible, state.ui.selectedNodeId);
    return selectedNodeId ? state.atlasModel.byId[selectedNodeId] || null : null;
  }

  function getPreviewStartEntry(visibleSnapshot) {
    if (state.ui.selectedNodeId) return null;
    const visible = visibleSnapshot || state.visible || refreshVisibleSnapshot();
    const visibleIds = new Set((visible.node_ids || []).map(String));
    const starts = visible.starts && visible.starts.length
      ? visible.starts
      : state.atlasModel.starts.filter((entry) => entry && entry.node && visibleIds.has(entry.node.id));
    if (starts.length) return starts[0];
    const fallback = (visible.nodes || []).slice().filter((node) => {
      return node && (node.summary || node.content || node.source_path);
    }).sort((left, right) => (right.priority || 0) - (left.priority || 0))[0];
    return fallback ? { node: fallback, reason: "当前范围 · 推荐预览" } : null;
  }

  function refreshVisibleSnapshot() {
    state.visible = resolveAtlasVisibleSnapshot(state.atlasModel, state.atlasLayout, state.ui);
    state.ui.selectedNodeId = resolveAtlasSelectedNodeId(state.atlasModel, state.visible, state.ui.selectedNodeId);
    return state.visible;
  }

  function currentViewportSize() {
    const rect = atlas.getBoundingClientRect();
    return {
      width: rect && rect.width ? rect.width : 1000,
      height: rect && rect.height ? rect.height : 680
    };
  }

  function viewportOptions() {
    return { minScale: 0.62, maxScale: 3.2 };
  }

  function edgeTransformForViewport(viewport, size) {
    const safeSize = size || currentViewportSize();
    const x = (viewport.x / safeSize.width) * 1000;
    const y = (viewport.y / safeSize.height) * 680;
    return `translate(${x} ${y}) scale(${viewport.scale})`;
  }

  function applyViewportTransform() {
    const size = currentViewportSize();
    if (nodeLayer) {
      nodeLayer.style.transform = `translate(${state.viewport.x}px, ${state.viewport.y}px) scale(${state.viewport.scale})`;
    }
    if (edgeLayer) {
      edgeLayer.setAttribute("transform", edgeTransformForViewport(state.viewport, size));
    }
    updateMinimapViewport();
  }

  function updateMinimapViewport() {
    if (!minimapSvg) return;
    const rect = minimapSvg.querySelector(".mini-map-viewport");
    if (!rect) return;
    const miniRect = atlasViewportToMinimapRect(state.viewport, currentViewportSize());
    rect.setAttribute("x", String(miniRect.x));
    rect.setAttribute("y", String(miniRect.y));
    rect.setAttribute("width", String(miniRect.width));
    rect.setAttribute("height", String(miniRect.height));
  }

  function scheduleViewportPaint() {
    if (viewportPaintFrame) return;
    viewportPaintFrame = window.requestAnimationFrame(() => {
      viewportPaintFrame = 0;
      applyViewportTransform();
    });
  }

  function setViewport(nextViewport, immediate) {
    state.viewport = helpers.clampAtlasViewport(nextViewport, currentViewportSize(), viewportOptions());
    if (immediate) {
      if (viewportPaintFrame) {
        window.cancelAnimationFrame(viewportPaintFrame);
        viewportPaintFrame = 0;
      }
      applyViewportTransform();
    } else {
      scheduleViewportPaint();
    }
  }

  function fitVisibleViewport() {
    const visible = state.visible || refreshVisibleSnapshot();
    const bounds = getAtlasModelBounds(visible.nodes, visible.nodes.length <= 1 ? 160 : 56);
    setViewport(fitAtlasViewport(bounds, currentViewportSize(), { padding: 0.82, minScale: 0.62, maxScale: 1.18 }), true);
    state.viewportReady = true;
  }

  function centerViewportOnNode(nodeId) {
    const node = state.atlasModel.byId[nodeId];
    if (!node) return;
    const scale = Math.max(1.05, Math.min(state.viewport.scale || 1, 1.6));
    setViewport(centerAtlasViewportOnPoint(atlasNodePoint(node), currentViewportSize(), scale, viewportOptions()), true);
    state.viewportReady = true;
  }

  function makePath(a, b, edge) {
    const sourcePoint = atlasNodePoint(a);
    const targetPoint = atlasNodePoint(b);
    const x1 = sourcePoint.x;
    const y1 = sourcePoint.y;
    const x2 = targetPoint.x;
    const y2 = targetPoint.y;
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const curve = Math.max(-76, Math.min(76, (a.y - b.y) * 1.8 + (clampWeight(edge.weight) - 0.5) * 24));
    return `M ${x1} ${y1} Q ${mx + curve} ${my - 22} ${x2} ${y2}`;
  }

  function edgeClass(edge) {
    return String(edge.type || "EXTRACTED").toLowerCase();
  }

  function connectedIds(id) {
    const out = new Set([id]);
    state.atlasModel.edges.forEach((edge) => {
      if (edge.source === id) out.add(edge.target);
      if (edge.target === id) out.add(edge.source);
    });
    return out;
  }

  function isNodeImportant(node) {
    return !!(node && state.visible && state.visible.importantNodeIds && state.visible.importantNodeIds[node.id]);
  }

  function nodeVisualRole(node, displayMode, previewNodeId) {
    if (!node) return "landmark";
    if (node.id === state.ui.selectedNodeId) return "cinnabar-note";
    if (displayMode === "point" || displayMode === "overview") return "map-pin";
    if (state.visible && state.visible.matchedNodeIds[node.id]) return "index-slip";
    if (previewNodeId && node.id === previewNodeId) return "index-slip";
    if (isNodeImportant(node)) return "index-slip";
    return "landmark";
  }

  function nodeDisplayMode(node, previewNodeId) {
    const mode = currentDensityMode();
    if (!node) return "card";
    if (node.id === state.ui.selectedNodeId) return "card";
    if (state.visible && state.visible.matchedNodeIds[node.id]) return "card";
    if (previewNodeId && node.id === previewNodeId && (mode === "overview" || mode === "point-plus-focus")) return "compact-card";
    if (isNodeImportant(node) && (mode === "overview" || mode === "point-plus-focus")) return "compact-card";
    if (mode === "overview") return state.visible.labelNodeIds[node.id] ? "compact-card" : "overview";
    if (mode === "point-plus-focus") return state.visible.labelNodeIds[node.id] ? "compact-card" : "point";
    return mode;
  }

  function renderTopbar() {
    const title = document.getElementById("wiki-title");
    if (title) title.textContent = `${state.atlasModel.meta.wiki_title} 知识舆图`;
  }

  function renderSidebar() {
    if (!communityList || !startList) return;

    const visible = state.visible || refreshVisibleSnapshot();
    communityList.innerHTML = "";

    const allButton = document.createElement("button");
    allButton.className = "nav-item";
    allButton.type = "button";
    allButton.dataset.community = "all";
    allButton.setAttribute("aria-pressed", state.ui.activeCommunityId === "all" ? "true" : "false");
    allButton.innerHTML = `
      <i class="swatch" style="background:${COMMUNITY_COLORS[0]}"></i>
      <span class="nav-copy"><strong>全部社区</strong><span>${state.atlasModel.nodes.length} 个节点</span></span>
      <span class="count">ALL</span>
    `;
    allButton.addEventListener("click", () => setCommunity("all"));
    communityList.appendChild(allButton);

    state.atlasModel.communities.forEach((community) => {
      const button = document.createElement("button");
      button.className = "nav-item";
      button.type = "button";
      button.dataset.community = community.id;
      button.setAttribute("aria-pressed", state.ui.activeCommunityId === community.id ? "true" : "false");
      button.innerHTML = `
        <i class="swatch" style="background:${communityColor(community.id)}"></i>
        <span class="nav-copy"><strong>${escapeHtml(community.label)}</strong><span>${community.node_count || 0} 个节点</span></span>
        <span class="count">${community.node_count || 0}</span>
      `;
      button.addEventListener("click", () => setCommunity(community.id));
      communityList.appendChild(button);
    });

    startList.innerHTML = "";
    const previewEntry = getPreviewStartEntry(visible);
    const previewNodeId = previewEntry && previewEntry.node ? previewEntry.node.id : null;
    const starts = visible.starts.length ? visible.starts : state.atlasModel.starts;
    starts.slice(0, 4).forEach((entry) => {
      const node = entry.node;
      const button = document.createElement("button");
      button.className = "start-card";
      button.type = "button";
      button.dataset.previewStart = node.id === previewNodeId ? "true" : "false";
      button.innerHTML = `<span class="card-copy"><strong>${escapeHtml(node.label)}</strong><span>${escapeHtml(entry.reason || atlasTypeLabel(node.type))}</span></span>`;
      button.addEventListener("click", () => focusNode(node.id, true));
      startList.appendChild(button);
    });
    if (!startList.children.length) {
      const empty = document.createElement("div");
      empty.className = "note-card";
      empty.textContent = "暂无推荐起点。";
      startList.appendChild(empty);
    }

    const summary = summarizeQueue(state.queue, state.atlasModel.byId, 3);
    const metrics = document.querySelectorAll(".queue-metrics .metric b");
    if (metrics[0]) metrics[0].textContent = summary.favorite_count;
    if (metrics[1]) metrics[1].textContent = summary.note_count;
    const queueList = document.querySelector(".queue-list");
    if (queueList) {
      queueList.innerHTML = "";
      if (!summary.recent_items.length) {
        const empty = document.createElement("div");
        empty.className = "note-card";
        empty.textContent = "选中节点后可加入学习队列。";
        queueList.appendChild(empty);
        return;
      }
      summary.recent_items.slice(0, 3).forEach((item) => {
        const node = state.atlasModel.byId[item.node_id];
        const button = document.createElement("button");
        const kindLabel = item.kind === "note" ? "札记" : "待读";
        const meta = node ? `${atlasTypeLabel(node.type)} · ${atlasConfidenceLabel(node.confidence)}` : "队列条目";
        button.className = "queue-item";
        button.type = "button";
        button.dataset.kind = item.kind;
        button.setAttribute("aria-current", item.node_id === state.ui.selectedNodeId ? "true" : "false");
        button.innerHTML = `
          <i class="queue-item__marker" aria-hidden="true"></i>
          <span class="queue-item__copy"><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(meta)}</span></span>
          <span class="queue-item__badge">${kindLabel}</span>
        `;
        button.addEventListener("click", () => focusNode(item.node_id, true));
        queueList.appendChild(button);
      });
    }
  }

  function renderCanvas() {
    const visible = state.visible || refreshVisibleSnapshot();
    atlas.dataset.mode = state.ui.dataMode;
    atlas.dataset.density = visible.densityMode;

    edgeLayer.innerHTML = "";
    visible.edges.forEach((edge) => {
      const source = state.atlasModel.byId[edge.source];
      const target = state.atlasModel.byId[edge.target];
      if (!source || !target) return;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", makePath(source, target, edge));
      path.setAttribute("class", `edge ${edgeClass(edge)}`);
      path.setAttribute("data-from", edge.source);
      path.setAttribute("data-to", edge.target);
      path.setAttribute("data-edge-id", edge.id);
      path.style.strokeWidth = edgeStrokeWidth(edge);
      path.style.opacity = edgeOpacity(edge);
      edgeLayer.appendChild(path);
    });

    nodeLayer.innerHTML = "";
    const previewEntry = getPreviewStartEntry(visible);
    const previewNodeId = previewEntry && previewEntry.node ? previewEntry.node.id : null;
    visible.nodes.forEach((node) => {
      const displayMode = nodeDisplayMode(node, previewNodeId);
      const visualRole = nodeVisualRole(node, displayMode, previewNodeId);
      const button = document.createElement("button");
      button.className = "node";
      if (node.unavailable) button.classList.add("is-disabled");
      if (displayMode === "compact-card") button.classList.add("is-compact");
      if (displayMode === "point") button.classList.add("is-point");
      if (displayMode === "overview") button.classList.add("is-overview");
      if (visualRole === "index-slip") button.classList.add("is-index-slip");
      if (visualRole === "cinnabar-note") button.classList.add("is-cinnabar-note");
      if (visualRole === "map-pin") button.classList.add("is-map-pin");
      if (node.id === previewNodeId) button.classList.add("is-preview-start");
      if (state.visible && !state.visible.labelNodeIds[node.id]) button.classList.add("is-label-hidden");
      button.type = "button";
      button.dataset.id = node.id;
      button.dataset.type = node.type;
      button.dataset.community = node.community;
      button.dataset.densityMode = displayMode;
      button.dataset.visualRole = visualRole;
      button.dataset.startNode = state.visible && state.visible.startNodeIds[node.id] ? "true" : "false";
      button.dataset.previewStart = node.id === previewNodeId ? "true" : "false";
      button.style.left = `${node.x}%`;
      button.style.top = `${node.y}%`;
      button.title = node.label;
      button.setAttribute("aria-pressed", node.id === state.ui.selectedNodeId ? "true" : "false");
      button.innerHTML = `
        <span class="node-kind">${node.kind}</span>
        <span class="node-name">${escapeHtml(node.label)}</span>
        <span class="node-meta"><i class="spark"></i>${node.unavailable ? "来源暂不可用" : Math.round(node.priority || node.weight || 0)}</span>
      `;
      button.addEventListener("click", () => selectNode(node.id));
      button.addEventListener("mouseenter", () => highlightNeighborhood(node.id));
      button.addEventListener("mouseleave", () => applyFilters());
      nodeLayer.appendChild(button);
    });

    applyFilters();
    renderMinimap();
    applyViewportTransform();
  }

  function setDrawerActions(mode, node) {
    const queueAction = document.getElementById("queue-action");
    const sourceAction = document.getElementById("source-action");
    if (queueAction) {
      queueAction.textContent = mode === "preview" ? "从这里开始" : "加入学习队列";
      queueAction.disabled = mode === "empty";
    }
    if (sourceAction) {
      sourceAction.textContent = "查看来源";
      sourceAction.disabled = !(node && node.source_path);
    }
  }

  function renderStartPreview(entry) {
    const node = entry && entry.node;
    if (!node) return false;
    const neighbors = getNeighbors(node.id);
    const community = state.atlasModel.communityById[node.community];
    const communityLabel = community ? community.label : "未分组";
    const excerpt = stripAtlasMarkdown(node.content || node.summary || "").slice(0, 220);

    document.getElementById("drawer-kind").innerHTML = `<span class="spark"></span>从这里开始 · 预览`;
    document.getElementById("drawer-title").textContent = node.label;
    document.getElementById("drawer-subtitle").textContent = `${entry.reason || atlasTypeLabel(node.type)} · ${communityLabel} · 点击后进入阅读态`;
    document.getElementById("drawer-summary").textContent = node.summary || excerpt || "这个节点适合作为当前图谱的起点。";
    document.getElementById("drawer-neighbor-count").textContent = `${neighbors.length} 个`;

    const content = document.getElementById("drawer-content");
    if (content) {
      content.innerHTML = `
        <p>这是一条推荐起点预览。全局图仍保持中立，点击“从这里开始”或左侧推荐起点后，才会进入选中阅读态。</p>
        <p>${escapeHtml(excerpt || node.summary || "当前节点暂无正文，但可以从相邻节点继续展开。")}</p>
      `;
    }

    if (neighborList) {
      neighborList.innerHTML = "";
      if (!neighbors.length) {
        const empty = document.createElement("div");
        empty.className = "note-card";
        empty.textContent = "这个起点暂时没有相邻节点。";
        neighborList.appendChild(empty);
      }
      neighbors.slice(0, 4).forEach((entryItem) => {
        const neighbor = entryItem.node;
        const button = document.createElement("button");
        button.className = "neighbor-card";
        button.type = "button";
        button.innerHTML = `<span class="card-copy"><strong>${escapeHtml(neighbor.label)}</strong><span>${atlasTypeLabel(neighbor.type)} · ${atlasConfidenceLabel(entryItem.edge.type)}</span></span>`;
        button.addEventListener("click", () => focusNode(neighbor.id, true));
        neighborList.appendChild(button);
      });
    }

    setDrawerActions("preview", node);
    return true;
  }

  function renderDrawer() {
    const selected = getSelectedNode();
    if (!drawer) return;
    const previewEntry = getPreviewStartEntry();
    if (app) {
      app.dataset.reading = selected ? "1" : "0";
      app.dataset.startPreview = !selected && previewEntry ? "1" : "0";
    }
    drawer.dataset.state = selected ? "reading" : (previewEntry ? "start-preview" : "empty");
    if (!selected && previewEntry && renderStartPreview(previewEntry)) return;
    if (!selected) {
      setDrawerActions("empty", null);
      document.getElementById("drawer-kind").innerHTML = `<span class="spark"></span>当前范围`;
      document.getElementById("drawer-title").textContent = "没有匹配节点";
      document.getElementById("drawer-subtitle").textContent = "调整搜索或筛选后查看知识内容";
      document.getElementById("drawer-summary").textContent = "当前范围内没有可显示的节点。";
      document.getElementById("drawer-neighbor-count").textContent = "0 个";
      const content = document.getElementById("drawer-content");
      if (content) content.innerHTML = "<p>清除搜索词或切回全部社区后，可以继续查看节点摘要和知识内容。</p>";
      if (neighborList) {
        neighborList.innerHTML = "";
        const empty = document.createElement("div");
        empty.className = "note-card";
        empty.textContent = "暂无相邻节点。";
        neighborList.appendChild(empty);
      }
      return;
    }
    state.ui.selectedNodeId = selected.id;
    setDrawerActions("reading", selected);

    const neighbors = getNeighbors(selected.id);
    const community = state.atlasModel.communityById[selected.community];
    const communityLabel = community ? community.label : "未分组";

    document.getElementById("drawer-kind").innerHTML = `<span class="spark"></span>${atlasTypeLabel(selected.type)} · 已选中`;
    document.getElementById("drawer-title").textContent = selected.label;
    document.getElementById("drawer-subtitle").textContent = `${communityLabel} · ${atlasConfidenceLabel(selected.confidence)}${selected.source_path ? " · " + selected.source_path : ""}`;
    document.getElementById("drawer-summary").textContent = selected.summary || "暂无摘要。";
    document.getElementById("drawer-neighbor-count").textContent = `${neighbors.length} 个`;

    renderKnowledgeCard(selected, neighbors);

    if (neighborList) {
      neighborList.innerHTML = "";
      if (!neighbors.length) {
        const empty = document.createElement("div");
        empty.className = "note-card";
        empty.textContent = "这个节点暂时没有相邻节点。";
        neighborList.appendChild(empty);
      }
      neighbors.forEach((entry) => {
        const node = entry.node;
        const button = document.createElement("button");
        button.className = "neighbor-card";
        button.type = "button";
        button.innerHTML = `<span class="card-copy"><strong>${escapeHtml(node.label)}</strong><span>${atlasTypeLabel(node.type)} · ${atlasConfidenceLabel(entry.edge.type)}</span></span>`;
        button.addEventListener("click", () => focusNode(node.id, true));
        neighborList.appendChild(button);
      });
    }
  }

  function renderKnowledgeCard(node, neighbors) {
    const content = document.getElementById("drawer-content");
    if (!content) return;
    const rawContent = String(node.content || "").trim();
    if (rawContent) {
      const linked = rawContent.replace(/\[\[([^\]]+)\]\]/g, (_, inner) => {
        const parts = inner.split("|");
        const target = parts[0].trim();
        const label = (parts[1] || parts[0]).trim();
        const exists = state.atlasModel.nodes.some((item) => item.id === target || item.label === target);
        const cls = exists ? "wikilink" : "wikilink wikilink--dead";
        return `<a class="${cls}" data-target="${escapeHtml(target)}">${escapeHtml(label)}</a>`;
      });
      const html = typeof marked === "undefined" ? `<p>${escapeHtml(stripAtlasMarkdown(linked))}</p>` : marked.parse(linked, { breaks: false, gfm: true });
      const safe = typeof DOMPurify === "undefined"
        ? html
        : DOMPurify.sanitize(html, { ADD_ATTR: ["target", "data-target", "tabindex"] });
      content.innerHTML = safe;
    } else {
      const related = neighbors.length
        ? `它当前连接到 ${neighbors.map((entry) => `「${entry.node.label}」`).join("、")}。`
        : "这个节点暂时没有相邻节点。";
      content.innerHTML = `<p>${escapeHtml(node.label)}属于知识库中的「${escapeHtml(atlasTypeLabel(node.type))}」节点。</p><p>${escapeHtml(node.summary || related)}</p>`;
    }

    content.querySelectorAll("a.wikilink").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        if (link.classList.contains("wikilink--dead")) return;
        const target = link.getAttribute("data-target");
        const hit = state.atlasModel.nodes.find((item) => item.id === target || item.label === target);
        if (hit) focusNode(hit.id, true);
      });
    });
  }

  function getNeighbors(nodeId) {
    const out = [];
    state.atlasModel.edges.forEach((edge) => {
      if (edge.source === nodeId && state.atlasModel.byId[edge.target]) {
        out.push({ node: state.atlasModel.byId[edge.target], edge, direction: "to" });
      } else if (edge.target === nodeId && state.atlasModel.byId[edge.source]) {
        out.push({ node: state.atlasModel.byId[edge.source], edge, direction: "from" });
      }
    });
    return out.sort((left, right) => clampWeight(right.edge.weight) - clampWeight(left.edge.weight));
  }

  function renderInsights() {
    if (!insightTitle || !insightCopy) return;
    const visible = state.visible || refreshVisibleSnapshot();
    const insights = state.atlasModel.insights;
    const bridge = insights.bridge_nodes && insights.bridge_nodes[0];
    const surprising = insights.surprising_connections && insights.surprising_connections[0];
    if (surprising) {
      insightTitle.textContent = "发现跨社区强连接";
      insightCopy.textContent = `${surprising.from} 与 ${surprising.to} 的关系权重较高，适合作为下一步阅读线索。`;
    } else if (bridge) {
      insightTitle.textContent = "桥接节点值得优先阅读";
      insightCopy.textContent = `${bridge.label || bridge.id} 连接多个社区，可帮助从局部主题进入全局图谱。`;
    } else if (visible.densityMode === "overview") {
      insightTitle.textContent = "当前视图过密";
      insightCopy.textContent = "建议搜索关键词或筛选社区，先缩小图谱范围再阅读节点内容。";
    } else {
      insightTitle.textContent = "从选中节点进入阅读";
      insightCopy.textContent = "右侧札记会随节点、搜索和社区筛选同步更新。";
    }
  }

  function renderMinimap() {
    if (!minimapSvg) return;
    const visible = state.visible || refreshVisibleSnapshot();
    while (minimapSvg.firstChild) minimapSvg.removeChild(minimapSvg.firstChild);
    const ns = "http://www.w3.org/2000/svg";
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", "M8 40 C34 20 54 36 76 22 C98 8 118 24 150 12");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#cfc4b1");
    path.setAttribute("stroke-width", "1.4");
    minimapSvg.appendChild(path);

    visible.nodes.slice(0, 60).forEach((node) => {
      const point = atlasPointToMinimap(atlasNodePoint(node));
      const circle = document.createElementNS(ns, "circle");
      circle.setAttribute("cx", String(point.x));
      circle.setAttribute("cy", String(point.y));
      circle.setAttribute("r", node.id === state.ui.selectedNodeId ? "3.2" : "2.2");
      circle.setAttribute("fill", communityColor(node.community));
      if (node.id === state.ui.selectedNodeId) circle.classList.add("is-selected");
      minimapSvg.appendChild(circle);
    });

    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("class", "mini-map-viewport");
    rect.setAttribute("rx", "5");
    minimapSvg.appendChild(rect);
    updateMinimapViewport();
  }

  function applyFilters() {
    const visible = state.visible || refreshVisibleSnapshot();
    const visibleIds = new Set(visible.node_ids);
    const selectedIds = state.ui.selectedNodeId ? connectedIds(state.ui.selectedNodeId) : new Set();

    document.querySelectorAll(".node").forEach((nodeEl) => {
      const id = nodeEl.dataset.id;
      const isVisible = visibleIds.has(id);
      nodeEl.classList.toggle("is-hidden", !isVisible);
      const dim = state.ui.dimUnselected && state.ui.selectedNodeId && !selectedIds.has(id);
      nodeEl.classList.toggle("is-dim", isVisible && dim);
      nodeEl.setAttribute("aria-pressed", id === state.ui.selectedNodeId ? "true" : "false");
    });

    document.querySelectorAll(".edge").forEach((edgeEl) => {
      const from = edgeEl.dataset.from;
      const to = edgeEl.dataset.to;
      const visibleEdge = visibleIds.has(from) && visibleIds.has(to);
      const dim = state.ui.dimUnselected && state.ui.selectedNodeId && from !== state.ui.selectedNodeId && to !== state.ui.selectedNodeId;
      edgeEl.classList.toggle("is-dim", !visibleEdge || dim);
    });

    const hasNoResults = !!state.ui.query && visible.nodes.length === 0 && state.ui.dataMode === "normal";
    if (noResults) noResults.classList.toggle("is-visible", hasNoResults);

    const communityName = state.ui.activeCommunityId === "all"
      ? "全局视图"
      : (state.atlasModel.communityById[state.ui.activeCommunityId] || {}).label || "当前社区";
    if (canvasTitle) canvasTitle.textContent = `知识地图 · ${communityName}`;
    if (canvasSubtitle) {
      const densityLabel = ({
        card: "卡片",
        "compact-card": "紧凑卡片",
        "point-plus-focus": "点位聚焦",
        overview: "总览"
      })[visible.densityMode] || "卡片";
      canvasSubtitle.textContent = hasNoResults
        ? "当前筛选没有匹配节点"
        : `${visible.nodes.length} 个节点在当前范围内可见 · ${densityLabel}模式`;
    }
  }

  function highlightNeighborhood(id) {
    if (state.ui.dataMode !== "normal") return;
    const ids = connectedIds(id);
    document.querySelectorAll(".node").forEach((nodeEl) => {
      nodeEl.classList.toggle("is-dim", !ids.has(nodeEl.dataset.id));
    });
    document.querySelectorAll(".edge").forEach((edgeEl) => {
      edgeEl.classList.toggle("is-dim", edgeEl.dataset.from !== id && edgeEl.dataset.to !== id);
    });
  }

  function renderAtlasView(options) {
    const opts = options && typeof options === "object" ? options : {};
    refreshVisibleSnapshot();
    if (app) app.dataset.reading = state.ui.selectedNodeId ? "1" : "0";
    if (opts.fitViewport || !state.viewportReady) fitVisibleViewport();
    renderTopbar();
    renderSidebar();
    renderCanvas();
    renderDrawer();
    renderInsights();
  }

  function selectNode(id) {
    if (!state.atlasModel.byId[id]) return;
    state.ui.selectedNodeId = id;
    renderAtlasView();
  }

  function focusNode(nodeId, openDrawer) {
    if (!state.atlasModel.byId[nodeId]) return;
    state.ui.selectedNodeId = nodeId;
    if (openDrawer !== false && drawer) {
      drawer.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    renderAtlasView();
    centerViewportOnNode(nodeId);
  }

  function closeDrawer() {
    state.ui.selectedNodeId = null;
    renderAtlasView({ fitViewport: true });
  }

  function setCommunity(communityId) {
    state.ui.activeCommunityId = communityId || "all";
    renderAtlasView({ fitViewport: true });
  }

  function buildNoteText(node) {
    const stripped = stripAtlasMarkdown(node && node.content);
    const excerpt = stripped.slice(0, NOTE_EXCERPT_LIMIT);
    return node && node.label ? `${node.label}${excerpt ? "：" + excerpt : ""}` : excerpt;
  }

  function handleQueueAction() {
    const node = getSelectedNode();
    if (!node) {
      const previewEntry = getPreviewStartEntry();
      if (previewEntry && previewEntry.node) focusNode(previewEntry.node.id, true);
      return;
    }
    state.queue = toggleQueueFavorite(state.queue, node.id);
    state.queue = appendQueueNote(state.queue, {
      id: `${node.id}:${Date.now()}`,
      node_id: node.id,
      label: node.label,
      text: buildNoteText(node),
      created_at: new Date().toISOString()
    }, QUEUE_NOTE_LIMIT);
    persistQueueState();
    renderSidebar();
  }

  function setupSearch() {
    if (!searchInput) return;
    searchInput.addEventListener("input", () => {
      state.ui.query = searchInput.value.trim().toLowerCase();
      renderAtlasView({ fitViewport: true });
    });
    searchInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const hit = state.visible && state.visible.nodes[0];
      if (hit) focusNode(hit.id, true);
    });
  }

  function isCanvasPanTarget(target) {
    return !(target && target.closest && target.closest(".node, button, a, input, textarea, summary, details"));
  }

  function setupViewportInteractions() {
    atlas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || !isCanvasPanTarget(event.target)) return;
      panState = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        viewport: { x: state.viewport.x, y: state.viewport.y, scale: state.viewport.scale }
      };
      atlas.classList.add("is-panning");
      atlas.setPointerCapture(event.pointerId);
      event.preventDefault();
    });

    atlas.addEventListener("pointermove", (event) => {
      if (!panState || panState.pointerId !== event.pointerId) return;
      setViewport({
        x: panState.viewport.x + event.clientX - panState.startX,
        y: panState.viewport.y + event.clientY - panState.startY,
        scale: panState.viewport.scale
      });
      event.preventDefault();
    });

    function finishPan(event) {
      if (!panState || panState.pointerId !== event.pointerId) return;
      panState = null;
      atlas.classList.remove("is-panning");
      if (atlas.hasPointerCapture && atlas.hasPointerCapture(event.pointerId)) {
        atlas.releasePointerCapture(event.pointerId);
      }
    }

    atlas.addEventListener("pointerup", finishPan);
    atlas.addEventListener("pointercancel", finishPan);
    atlas.addEventListener("wheel", (event) => {
      if (!isCanvasPanTarget(event.target) && !(event.target && event.target.closest && event.target.closest(".node"))) return;
      const rect = atlas.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * 0.0012);
      setViewport(zoomAtlasViewport(state.viewport, factor, {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top
      }, currentViewportSize(), viewportOptions()));
      event.preventDefault();
    }, { passive: false });
  }

  function setupMinimapNavigation() {
    if (!minimapSvg) return;
    minimapSvg.addEventListener("click", (event) => {
      const matrix = minimapSvg.getScreenCTM && minimapSvg.getScreenCTM();
      if (!matrix) return;
      const point = minimapSvg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const local = point.matrixTransform(matrix.inverse());
      const atlasPoint = minimapPointToAtlasPoint({ x: local.x, y: local.y });
      setViewport(centerAtlasViewportOnPoint(atlasPoint, currentViewportSize(), state.viewport.scale, viewportOptions()), true);
    });
  }

  function setupControls() {
    document.querySelectorAll("[data-focus]").forEach((button) => {
      button.addEventListener("click", () => {
        state.ui.focusMode = button.dataset.focus || "all";
        document.querySelectorAll("[data-focus]").forEach((item) => {
          item.setAttribute("aria-pressed", item === button ? "true" : "false");
        });
        renderAtlasView({ fitViewport: true });
      });
    });

    document.querySelectorAll(".state-button[data-mode]").forEach((button) => {
      button.addEventListener("click", () => {
        state.ui.dataMode = button.dataset.mode || "normal";
        atlas.dataset.mode = state.ui.dataMode;
        document.querySelectorAll(".state-button[data-mode]").forEach((item) => {
          item.setAttribute("aria-pressed", item === button ? "true" : "false");
        });
        applyFilters();
      });
    });

    const dimButton = document.getElementById("toggle-dim");
    if (dimButton) {
      dimButton.addEventListener("click", () => {
        state.ui.dimUnselected = !state.ui.dimUnselected;
        dimButton.textContent = state.ui.dimUnselected ? "显示全部层级" : "弱化未选中";
        applyFilters();
      });
    }

    const fitButton = document.getElementById("fit-view");
    if (fitButton) {
      fitButton.addEventListener("click", () => {
        state.ui.activeCommunityId = "all";
        state.ui.focusMode = "all";
        state.ui.query = "";
        state.ui.selectedNodeId = null;
        state.ui.dataMode = "normal";
        if (searchInput) searchInput.value = "";
        document.querySelectorAll("[data-focus]").forEach((item) => {
          item.setAttribute("aria-pressed", item.dataset.focus === "all" ? "true" : "false");
        });
        document.querySelectorAll(".state-button[data-mode]").forEach((item) => {
          item.setAttribute("aria-pressed", item.dataset.mode === "normal" ? "true" : "false");
        });
        renderAtlasView({ fitViewport: true });
      });
    }

    const queueAction = document.getElementById("queue-action");
    if (queueAction) queueAction.addEventListener("click", handleQueueAction);

    const sourceAction = document.getElementById("source-action");
    if (sourceAction) {
      sourceAction.addEventListener("click", () => {
        const previewEntry = getPreviewStartEntry();
        const node = getSelectedNode() || (previewEntry && previewEntry.node);
        if (node && node.source_path) window.location.href = node.source_path;
      });
    }
  }

  function applyNeighborsCollapsed(collapsed) {
    if (!drawerNeighbors || !drawerNeighborsHeading) return;
    drawerNeighbors.open = !collapsed;
    drawerNeighbors.setAttribute("data-collapsed", collapsed ? "1" : "0");
    drawerNeighborsHeading.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }

  function toggleNeighbors() {
    if (!drawerNeighbors) return;
    const nextCollapsed = drawerNeighbors.open;
    applyNeighborsCollapsed(nextCollapsed);
    safeLocalStorage.set(queueStorageKey("neighbors-collapsed"), nextCollapsed ? "1" : "0");
  }

  function setupNeighborToggle() {
    const storedNeighborsCollapsed = safeLocalStorage.get(queueStorageKey("neighbors-collapsed"));
    applyNeighborsCollapsed(storedNeighborsCollapsed == null ? true : storedNeighborsCollapsed === "1");
    if (!drawerNeighbors || !drawerNeighborsHeading) return;
    drawerNeighbors.addEventListener("toggle", () => {
      state.ui.neighborExpanded = drawerNeighbors.open;
      drawerNeighbors.setAttribute("data-collapsed", drawerNeighbors.open ? "0" : "1");
      drawerNeighborsHeading.setAttribute("aria-expanded", drawerNeighbors.open ? "true" : "false");
    });
    drawerNeighborsHeading.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleNeighbors();
      }
    });
  }

  function applyMinimapCollapsed(collapsed) {
    if (!minimapEl || !minimapToggle) return;
    minimapEl.setAttribute("data-collapsed", collapsed ? "1" : "0");
    minimapToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    minimapToggle.setAttribute("aria-label", collapsed ? "展开小地图" : "折叠小地图");
  }

  setupSearch();
  setupViewportInteractions();
  setupMinimapNavigation();
  setupControls();
  setupNeighborToggle();
  applyMinimapCollapsed(false);
  window.addEventListener("resize", () => renderAtlasView({ fitViewport: true }));
  renderAtlasView({ fitViewport: true });
})();
