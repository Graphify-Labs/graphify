"use strict";

const $ = (id) => document.getElementById(id);
const statusName = { queued: "Đang chờ", running: "Đang phân tích", ready: "Sẵn sàng", failed: "Thất bại" };
const labels = {
  query: "Câu hỏi",
  explain: "Tên nút hoặc ID",
  path: "Nút bắt đầu",
  affected: "Tên nút bị thay đổi",
  section: "Tiêu đề mục Markdown",
};
const exportNames = {
  markdown: "Báo cáo Markdown", json: "Đồ thị JSON", html: "Đồ thị HTML",
  graphml: "GraphML", callflow: "Sơ đồ luồng gọi", tree: "Cây mã nguồn",
  obsidian: "Obsidian ZIP", wiki: "Wiki ZIP", cypher: "Neo4j / FalkorDB Cypher", svg: "Đồ thị SVG",
};
const number = new Intl.NumberFormat("vi");
const canvas = $("graph-canvas");
const state = {
  user: null, projects: [], projectId: null, tab: "graph", admin: false,
  preview: null, nodes: [], selected: null, points: [], credential: null,
  account: null, polling: false, loadingGraph: false,
};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function api(path, options = {}) {
  const { json, ...init } = options;
  const headers = new Headers(init.headers);
  headers.set("X-Graphify-Request", "1");
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(json);
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const error = new Error(err.error || `Yêu cầu thất bại (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return response;
}

function feedback(target, message = "", isError = false) {
  target.textContent = message;
  target.classList.toggle("error", isError);
}

function notice(message) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

function projectPath(suffix = "", projectId = state.projectId) {
  return `/api/projects/${projectId}${suffix}`;
}

function loggedOut() {
  state.user = null;
  state.projects = [];
  state.projectId = null;
  state.admin = false;
  clearCredential();
  $("app-view").hidden = true;
  $("login-view").hidden = false;
  for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
}

async function initialize() {
  try {
    state.user = await (await api("/api/me")).json();
  } catch (error) {
    loggedOut();
    if (error.status !== 401) feedback($("login-form").querySelector(".feedback"), error.message, true);
    return;
  }
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  $("identity-name").textContent = state.user.username;
  $("identity-avatar").textContent = state.user.username.slice(0, 2).toUpperCase();
  $("admin-open").hidden = !state.user.admin;
  await refresh();
}

function renderProjectList() {
  const list = $("project-list");
  list.replaceChildren();
  $("project-count").textContent = state.projects.length;
  for (const project of state.projects) {
    const button = element("button", undefined, "project-link");
    button.type = "button";
    button.setAttribute("aria-current", String(!state.admin && state.projectId === project.id));
    button.title = `${project.title} · ${statusName[project.status]}`;
    const dot = element("span", undefined, `dot ${project.status}`);
    dot.setAttribute("aria-hidden", "true");
    button.append(dot, element("span", project.title));
    button.addEventListener("click", () => selectProject(project.id));
    list.append(button);
  }
  $("admin-open").setAttribute("aria-current", String(state.admin));
}

async function refresh() {
  if (!state.user || state.polling) return;
  state.polling = true;
  try {
    state.projects = await (await api("/api/projects")).json();
    if (!state.user) return;
    if (!state.projects.some((project) => project.id === state.projectId)) {
      selectProject(state.projects[0]?.id ?? null, state.admin);
    } else {
      renderProjectList();
      renderWorkspace();
    }
    if (state.admin) await adminDashboard();
  } catch (error) {
    if (error.status === 401) loggedOut();
    else notice(error.message);
  } finally {
    state.polling = false;
  }
}

function clearCredential() {
  state.credential = null;
  $("mcp-config").hidden = true;
  $("mcp-config-text").value = "";
  feedback($("mcp-feedback"));
}

function selectProject(id, admin = false) {
  state.projectId = id;
  state.admin = admin;
  state.preview = null;
  state.nodes = [];
  state.selected = null;
  state.points = [];
  state.loadingGraph = false;
  state.tab = "graph";
  $("node-search").value = "";
  $("report-details").open = false;
  $("report-text").textContent = "";
  $("query-result").hidden = true;
  $("query-form").reset();
  setTool();
  feedback($("query-form").querySelector(".feedback"));
  feedback($("export-feedback"));
  clearCredential();
  notice("");
  renderProjectList();
  renderWorkspace();
}

function renderWorkspace() {
  const project = state.projects.find((item) => item.id === state.projectId);
  $("admin-view").hidden = !state.admin;
  $("empty-view").hidden = state.admin || Boolean(project);
  $("project-view").hidden = state.admin || !project;
  if (state.admin || !project) return;
  $("project-title").textContent = project.title;
  $("project-detail").textContent = project.detail && project.status === "ready" ? project.detail : "";
  $("project-status").className = `status ${project.status}`;
  $("project-status").textContent = statusName[project.status];
  $("ready-view").hidden = project.status !== "ready";
  $("delete-project").disabled = project.status === "running";
  $("build-state").hidden = project.status === "ready";
  $("build-state").textContent = {
    queued: "Repo đang chờ máy chủ phân tích.",
    running: "Graphify đang lập bản đồ mã nguồn. Trang này tự cập nhật khi hoàn tất.",
    failed: project.detail || "Không thể phân tích repo.",
  }[project.status] || "";
  if (project.status !== "ready") return;
  $("mcp-url").value = `${location.origin}/mcp/${project.id}`;
  const active = project.token_expires > Date.now() / 1000;
  $("mcp-status").textContent = active
    ? `Token đang hoạt động, hết hạn vào ${new Date(project.token_expires * 1000).toLocaleDateString("vi")}.`
    : "Dự án chưa có token hoạt động.";
  $("token-create").textContent = active ? "Tạo token mới" : "Tạo token";
  $("token-revoke").hidden = !active;
  showTab(state.tab);
  if (!state.preview && !state.loadingGraph) loadGraph(project.id);
}

function showTab(tab) {
  const changed = tab !== state.tab;
  state.tab = tab;
  for (const control of document.querySelectorAll("[data-tab]")) {
    const active = control.dataset.tab === tab;
    control.setAttribute("aria-current", String(active));
    $(`tab-${control.dataset.tab}`).hidden = !active;
  }
  if (tab === "graph" && changed) requestAnimationFrame(drawGraph);
}

async function loadGraph(projectId) {
  state.loadingGraph = true;
  $("graph-caption").textContent = "Đang tải đồ thị…";
  for (const type of ["nodes", "edges", "communities"]) $(`metric-${type}`).textContent = "—";
  $("node-select").replaceChildren();
  $("node-detail").replaceChildren();
  $("node-explain").hidden = true;
  drawGraph();
  try {
    const preview = await (await api(projectPath("/files/preview", projectId))).json();
    if (projectId !== state.projectId || state.admin) return;
    state.preview = preview;
    state.nodes = [...preview.nodes].sort((a, b) => String(a.label).localeCompare(String(b.label)));
    for (const [type, amount] of Object.entries(preview.counts)) $(`metric-${type}`).textContent = number.format(amount);
    $("graph-caption").textContent = preview.nodes.length < preview.counts.nodes
      ? `Hiển thị ${preview.nodes.length} nút kết nối nhiều nhất. Dùng Truy vấn để tìm trên toàn đồ thị.`
      : "Chọn một nút để xem vị trí và màu nhóm.";
    filterNodes();
  } catch (error) {
    if (projectId === state.projectId) $("graph-caption").textContent = error.message;
  } finally {
    if (projectId === state.projectId) state.loadingGraph = false;
  }
}

function filterNodes() {
  const query = $("node-search").value.trim().toLowerCase();
  const nodes = state.nodes.filter((node) => `${node.label} ${node.source_file || ""}`.toLowerCase().includes(query));
  $("node-select").replaceChildren(...nodes.map((node) => new Option(node.label || node.id, node.id)));
  if (!nodes.some((node) => node.id === state.selected)) state.selected = nodes[0]?.id ?? null;
  showNode(state.selected);
}

function showNode(id) {
  state.selected = id;
  $("node-select").value = id || "";
  const node = state.nodes.find((candidate) => candidate.id === id);
  $("node-detail").replaceChildren();
  if (node) {
    $("node-detail").append(element("strong", node.label || node.id));
    if (node.source_file) $("node-detail").append(element("span", [node.source_file, node.source_location].filter(Boolean).join(" · ")));
    if (node.community != null) $("node-detail").append(element("span", `Nhóm ${node.community}`));
  }
  $("node-explain").hidden = !node;
  drawGraph();
}

function drawGraph() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  if (!state.preview) return;
  const { nodes, edges } = state.preview;
  const groups = [...new Set(nodes.map((node) => node.community))];
  const selection = new Set([...$("node-select").options].map((option) => option.value));
  const positions = new Map();
  const palette = ["#078476", "#6272b7", "#ae633b", "#4879ac", "#9368a6", "#578244", "#b4566c"];
  const byGroup = new Map(groups.map((group) => [group, nodes.filter((node) => node.community === group)]));
  for (const [index, group] of groups.entries()) {
    const angle = 2 * Math.PI * index / groups.length - Math.PI / 2;
    const factor = groups.length === 1 ? 0 : 0.29;
    const centerX = width / 2 + Math.cos(angle) * width * factor;
    const centerY = height / 2 + Math.sin(angle) * height * factor;
    const spread = Math.min(width, height) * (groups.length > 8 ? .075 : groups.length > 1 ? .17 : .38);
    const members = byGroup.get(group);
    for (const [memberIndex, node] of members.entries()) {
      const radius = spread * Math.sqrt(memberIndex / members.length);
      const theta = 2.39996 * memberIndex;
      positions.set(node.id, {
        id: node.id, label: node.label, color: palette[index % palette.length],
        x: centerX + Math.cos(theta) * radius, y: centerY + Math.sin(theta) * radius,
      });
    }
  }
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.strokeStyle = "#a8b7c46b";
  for (const edge of edges) {
    const from = positions.get(edge.source);
    const to = positions.get(edge.target);
    if (from && to && selection.has(edge.source) && selection.has(edge.target)) {
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
    }
  }
  ctx.stroke();
  for (const node of positions.values()) {
    const active = state.selected === node.id;
    ctx.beginPath();
    ctx.globalAlpha = selection.has(node.id) ? 1 : .14;
    ctx.fillStyle = node.color;
    ctx.arc(node.x, node.y, active ? 8 : 4.5, 0, 2 * Math.PI);
    ctx.fill();
    if (active) {
      ctx.strokeStyle = "#17243a";
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
  const active = positions.get(state.selected);
  if (active) {
    const message = String(active.label || active.id).slice(0, 47);
    ctx.font = "600 12px system-ui";
    const messageWidth = ctx.measureText(message).width + 14;
    const x = Math.max(4, Math.min(active.x + 11, width - messageWidth - 4));
    const y = Math.max(4, active.y - 26);
    ctx.fillStyle = "#142135";
    ctx.fillRect(x, y, messageWidth, 23);
    ctx.fillStyle = "#fff";
    ctx.fillText(message, x + 7, y + 16);
  }
  state.points = [...positions.values()].filter((point) => selection.has(point.id));
}

function setTool() {
  const action = $("query-action").value;
  $("query-first-label").hidden = !(action in labels);
  $("query-first-title").textContent = labels[action] || "";
  $("query-first").required = action in labels;
  $("query-second-label").hidden = action !== "path";
  $("query-second").required = action === "path";
}

function actionButton(text, handler) {
  const button = element("button", text, "secondary");
  button.type = "button";
  button.addEventListener("click", handler);
  return button;
}

for (const [kind, name] of Object.entries(exportNames)) {
  $("export-list").append(actionButton(name, async (event) => {
    const feedbackTarget = $("export-feedback");
    const button = event.currentTarget;
    const project = state.projectId;
    button.disabled = true;
    feedback(feedbackTarget, `Đang chuẩn bị ${name}…`);
    try {
      const response = await api(projectPath(`/files/${kind}`, project));
      const url = URL.createObjectURL(await response.blob());
      const link = element("a");
      link.href = url;
      link.download = /filename="([^"]+)"/i.exec(response.headers.get("content-disposition") || "")?.[1] || name;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      if (project === state.projectId) feedback(feedbackTarget, `Đã tải ${name}.`);
    } catch (error) {
      if (project === state.projectId) feedback(feedbackTarget, error.message, true);
    } finally {
      button.disabled = false;
    }
  }));
}

async function adminDashboard() {
  const { users, jobs } = await (await api("/api/admin/users")).json();
  if (!state.admin) return;
  const metricData = [
    ["Tài khoản hoạt động", users.filter((account) => account.active).length],
    ["Đang chờ / chạy", (jobs.queued || 0) + (jobs.running || 0)],
    ["Đồ thị sẵn sàng", jobs.ready || 0],
    ["Phân tích lỗi", jobs.failed || 0],
  ];
  $("admin-metrics").replaceChildren(...metricData.map(([label, amount]) => {
    const card = element("div", undefined, "panel metric");
    card.append(element("span", label), element("strong", number.format(amount)));
    return card;
  }));
  $("account-list").replaceChildren(...users.map((account) => {
    const row = element("tr");
    for (const value of [account.username, account.admin ? "Quản trị" : "Người dùng", account.projects,
      account.active ? "Hoạt động" : "Đã khóa"]) row.append(element("td", value));
    const actions = element("td");
    if (!account.admin) {
      actions.append(actionButton("Đổi mật khẩu", () => openAccount(account)));
      actions.append(actionButton(account.active ? "Khóa" : "Mở khóa", async () => {
        if (account.active && !confirm(`Khóa ${account.username} và thu hồi các phiên, token của tài khoản?`)) return;
        try {
          await api(`/api/admin/users/${account.id}`, { method: "PATCH", json: { active: !account.active } });
          await adminDashboard();
        } catch (error) {
          notice(error.message);
        }
      }));
    }
    row.append(actions);
    return row;
  }));
}

function openAccount(account = null) {
  state.account = account;
  const form = $("account-form");
  form.reset();
  $("account-title").textContent = account ? "Đổi mật khẩu" : "Tạo tài khoản";
  form.elements.username.disabled = Boolean(account);
  form.elements.username.value = account?.username || "";
  feedback(form.querySelector(".feedback"));
  $("account-dialog").showModal();
}

function bindForm(id, handler) {
  const form = $(id);
  const output = form.querySelector(".feedback");
  const button = form.querySelector("[type=submit]");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    feedback(output, "Đang xử lý…");
    try {
      await handler(form);
      feedback(output);
    } catch (error) {
      feedback(output, error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

bindForm("login-form", async (form) => {
  await api("/api/login", { method: "POST", json: Object.fromEntries(new FormData(form)) });
  form.reset();
  await initialize();
});

bindForm("upload-form", async (form) => {
  const title = form.elements.title.value.trim();
  const file = form.elements.repo.files[0];
  if (!file?.name.toLowerCase().endsWith(".zip")) throw new Error("Hãy chọn một file ZIP.");
  if (file.size > 50 * 1024 * 1024) throw new Error("File ZIP vượt giới hạn 50 MB.");
  const { id } = await (await api(`/api/projects?title=${encodeURIComponent(title)}`, {
    method: "POST", body: file, headers: { "Content-Type": "application/zip" },
  })).json();
  $("upload-dialog").close();
  state.projects = await (await api("/api/projects")).json();
  selectProject(id);
});

bindForm("query-form", async () => {
  const project = state.projectId;
  const action = $("query-action").value;
  const values = action in labels ? [$("query-first").value.trim()] : [];
  if (action === "path") values.push($("query-second").value.trim());
  $("query-result").hidden = true;
  const result = await (await api(projectPath("/actions", project), { method: "POST", json: { action, values } })).json();
  if (project !== state.projectId || state.admin) return;
  $("query-result").textContent = result.output || `Graphify kết thúc với mã ${result.status}.`;
  $("query-result").hidden = false;
});

bindForm("account-form", async (form) => {
  const password = form.elements.password.value;
  const username = form.elements.username.value;
  if (state.account) {
    await api(`/api/admin/users/${state.account.id}`, { method: "PATCH", json: { password } });
  } else {
    await api("/api/admin/users", { method: "POST", json: { username, password } });
  }
  $("account-dialog").close();
  form.reset();
  await adminDashboard();
});

const openUpload = () => {
  $("upload-form").reset();
  feedback($("upload-form").querySelector(".feedback"));
  $("upload-dialog").showModal();
};
$("new-project").addEventListener("click", openUpload);
$("empty-upload").addEventListener("click", openUpload);
$("upload-form").elements.repo.addEventListener("change", () => {
  const { repo, title } = $("upload-form").elements;
  if (!title.value && repo.files[0]) title.value = repo.files[0].name.slice(0, -4).slice(0, 100);
});
$("logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
    loggedOut();
  } catch (error) {
    notice(error.message);
  }
});
$("delete-project").addEventListener("click", async () => {
  const project = state.projects.find((item) => item.id === state.projectId);
  if (!project || !confirm(`Xóa dự án “${project.title}”, đồ thị và token MCP?`)) return;
  try {
    await api(projectPath("", project.id), { method: "DELETE" });
    await refresh();
  } catch (error) {
    notice(error.message);
  }
});
$("admin-open").addEventListener("click", async () => {
  selectProject(state.projectId, true);
  try {
    await adminDashboard();
  } catch (error) {
    notice(error.message);
  }
});
$("account-new").addEventListener("click", () => openAccount());
$("query-action").addEventListener("change", setTool);
$("node-search").addEventListener("input", filterNodes);
$("node-select").addEventListener("change", (event) => showNode(event.currentTarget.value));
$("node-explain").addEventListener("click", () => {
  showTab("tools");
  $("query-action").value = "explain";
  setTool();
  $("query-first").value = state.selected || "";
  $("query-form").requestSubmit();
});
canvas.addEventListener("click", (event) => {
  const nearest = state.points.reduce((best, point) => {
    const distance = Math.hypot(point.x - event.offsetX, point.y - event.offsetY);
    return distance < best.distance ? { point, distance } : best;
  }, { distance: 18 });
  if (nearest.point) showNode(nearest.point.id);
});
new ResizeObserver(drawGraph).observe(canvas);
for (const button of document.querySelectorAll("[data-tab]")) button.addEventListener("click", () => showTab(button.dataset.tab));
for (const button of document.querySelectorAll("[data-close]")) button.addEventListener("click", () => $(button.dataset.close).close());

$("report-details").addEventListener("toggle", async () => {
  if (!$("report-details").open) return;
  const project = state.projectId;
  $("report-text").textContent = "Đang tải…";
  try {
    const report = await (await api(projectPath("/files/report", project))).text();
    if (state.projectId === project) $("report-text").textContent = report;
  } catch (error) {
    if (state.projectId === project) $("report-text").textContent = error.message;
  }
});

$("token-create").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const project = state.projectId;
  button.disabled = true;
  try {
    const credential = await (await api(projectPath("/token", project), { method: "POST" })).json();
    if (project !== state.projectId || state.admin) return;
    state.credential = credential;
    $("mcp-config-text").value = JSON.stringify({
      mcpServers: { graphify: { type: "http", url: credential.url, headers: { Authorization: `Bearer ${credential.token}` } } },
    }, null, 2);
    $("mcp-config").hidden = false;
    feedback($("mcp-feedback"), "Đã tạo token cho dự án.");
    await refresh();
  } catch (error) {
    if (project === state.projectId) feedback($("mcp-feedback"), error.message, true);
  } finally {
    button.disabled = false;
  }
});
$("token-revoke").addEventListener("click", async () => {
  if (!confirm("Thu hồi token MCP đang dùng cho dự án này?")) return;
  try {
    await api(projectPath("/token"), { method: "DELETE" });
    clearCredential();
    feedback($("mcp-feedback"), "Đã thu hồi token.");
    await refresh();
  } catch (error) {
    feedback($("mcp-feedback"), error.message, true);
  }
});
$("token-copy").addEventListener("click", async () => {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText($("mcp-config-text").value);
      feedback($("mcp-feedback"), "Đã sao chép cấu hình.");
      return;
    } catch (_) {
      // Fall back to selecting the config in browsers that block clipboard access.
    }
  }
  $("mcp-config-text").select();
  feedback($("mcp-feedback"), "Đã chọn cấu hình. Nhấn Ctrl+C hoặc ⌘C để sao chép.");
});
$("mcp-test").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const credential = state.credential;
  if (!credential) return;
  button.disabled = true;
  feedback($("mcp-feedback"), "Đang kiểm tra endpoint MCP…");
  try {
    const headers = {
      "Content-Type": "application/json", Accept: "application/json, text/event-stream",
      Authorization: `Bearer ${credential.token}`,
    };
    const call = async (id, method, params) => {
      const response = await fetch(credential.url, {
        method: "POST", headers, body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
      });
      if (!response.ok) throw new Error(`MCP trả về HTTP ${response.status}.`);
      const result = await response.json();
      if (result.error || result.result?.isError) throw new Error("MCP từ chối truy vấn.");
      return result.result;
    };
    await call(1, "initialize", {
      protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "graphify-pilot", version: "1" },
    });
    const result = await call(2, "tools/call", { name: "graph_stats", arguments: {} });
    if (credential === state.credential) feedback($("mcp-feedback"), `Kết nối thành công. ${result.content?.[0]?.text?.split("\n")[0] || ""}`);
  } catch (error) {
    if (credential === state.credential) feedback($("mcp-feedback"), error.message, true);
  } finally {
    button.disabled = false;
  }
});

initialize().catch((error) => notice(error.message));
setInterval(() => {
  if (state.projects.some((project) => ["queued", "running"].includes(project.status))) refresh();
}, 1800);
