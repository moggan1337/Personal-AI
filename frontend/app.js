"use strict";

const api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  },
  async del(url) {
    const r = await fetch(url, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(r.statusText);
  },
};

const CATEGORY_HINTS = {
  writing: "Paste emails, messages, posts, or notes you've written.",
  decisions: "Describe choices you've made and the reasoning behind them.",
  knowledge: "Facts, expertise, opinions, and things you know well.",
  personality: "How you come across — traits, humor, values, quirks.",
};

const state = {
  meta: null,
  user: null, // {id, username} or null
  seeds: [],
  twins: [],
  current: null, // TwinDetail
  conversations: [],
  conversationId: null, // active conversation, or null for an unsaved new chat
  chat: [], // {role, content}
  streaming: false,
  authMode: "login", // "login" | "register"
};

// ---- elements ----
const el = (id) => document.getElementById(id);
const twinList = el("twinList");
const emptyState = el("emptyState");
const twinDetail = el("twinDetail");

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  state.meta = await api.get("/api/meta");
  el("modelLabel").textContent = `powered by ${state.meta.model}`;
  populateModes();
  state.seeds = await api.get("/api/seeds");
  renderSeeds();
  state.user = await api.get("/api/auth/me");
  renderAuth();
  await refreshTwins();
  wireGlobalUI();
}

function renderSeeds() {
  el("seedList").innerHTML = state.seeds
    .map(
      (s) => `<button class="seed-item" data-key="${s.key}">
                <strong>${escapeHtml(s.name)}${
        s.pretrained ? ' <span class="chip">ready to chat</span>' : ""
      }</strong>
                <span>${escapeHtml(s.tagline)}</span>
              </button>`
    )
    .join("");
  el("seedList").querySelectorAll(".seed-item").forEach((b) => {
    b.onclick = () => instantiateSeed(b.dataset.key);
  });
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
function renderAuth() {
  if (state.user) {
    el("authStatus").textContent = "@" + state.user.username;
    el("authBtn").textContent = "Sign out";
  } else {
    el("authStatus").textContent = "";
    el("authBtn").textContent = "Sign in";
  }
}

function openAuthModal() {
  state.authMode = "login";
  applyAuthMode();
  el("authError").textContent = "";
  el("authForm").reset();
  el("authModal").classList.remove("hidden");
  el("authUser").focus();
}

function applyAuthMode() {
  const register = state.authMode === "register";
  el("authTitle").textContent = register ? "Create account" : "Sign in";
  el("authSubmit").textContent = register ? "Create account" : "Sign in";
  el("authToggle").textContent = register ? "Have an account? Sign in" : "Create account";
}

async function submitAuth() {
  const username = el("authUser").value.trim();
  const password = el("authPass").value;
  const path = state.authMode === "register" ? "register" : "login";
  try {
    state.user = await api.post(`/api/auth/${path}`, { username, password });
    el("authModal").classList.add("hidden");
    renderAuth();
    await onScopeChanged();
  } catch (err) {
    el("authError").textContent = err.message;
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  state.user = null;
  renderAuth();
  await onScopeChanged();
}

// When the visible set of twins changes (login/logout), reset the workspace.
async function onScopeChanged() {
  state.current = null;
  twinDetail.classList.add("hidden");
  emptyState.classList.remove("hidden");
  await refreshTwins();
}

async function instantiateSeed(key) {
  const created = await api.post(`/api/seeds/${key}/instantiate`);
  el("modal").classList.add("hidden");
  await refreshTwins();
  await openTwin(created.id);
  el("trainStatus").textContent =
    "Loaded with example data — click “Synthesize persona” to bring this twin to life.";
}

function populateModes() {
  const sel = el("modeSelect");
  sel.innerHTML = state.meta.modes
    .map((m) => `<option value="${m}">${m}</option>`)
    .join("");
}

async function refreshTwins() {
  state.twins = await api.get("/api/twins");
  renderTwinList();
}

function renderTwinList() {
  if (!state.twins.length) {
    twinList.innerHTML = `<p class="muted">No twins yet. Create one to begin.</p>`;
    return;
  }
  twinList.innerHTML = state.twins
    .map(
      (t) => `
      <div class="twin-card ${state.current && state.current.id === t.id ? "active" : ""}" data-id="${t.id}">
        <h3>${escapeHtml(t.name)}</h3>
        <div class="meta">
          <span class="dot ${t.trained ? "trained" : "untrained"}"></span>
          <span class="muted">${t.trained ? "trained" : "untrained"} · ${t.sample_count} samples</span>
        </div>
      </div>`
    )
    .join("");
  twinList.querySelectorAll(".twin-card").forEach((card) => {
    card.onclick = () => openTwin(Number(card.dataset.id));
  });
}

// ---------------------------------------------------------------------------
// Twin detail
// ---------------------------------------------------------------------------
async function openTwin(id) {
  state.current = await api.get(`/api/twins/${id}`);
  newChat();
  emptyState.classList.add("hidden");
  twinDetail.classList.remove("hidden");
  renderTwinList();
  renderDetail();
  await refreshConversations();
  selectTab("train");
}

function renderDetail() {
  const t = state.current;
  el("detailName").textContent = t.name;
  el("detailTagline").textContent = t.tagline || t.owner || "";
  const badge = el("trainedBadge");
  badge.textContent = t.trained ? "Trained" : "Not trained";
  badge.className = "badge" + (t.trained ? " trained" : "");
  renderCategories();
  renderPersona();
  renderChat();
}

function renderCategories() {
  const t = state.current;
  el("categoryGrid").innerHTML = state.meta.categories
    .map((cat) => {
      const samples = (t.samples_by_category[cat] || [])
        .map(
          (s) => `<li><span>${escapeHtml(s.content)}</span>
                   <button class="x" data-cat="${cat}" data-id="${s.id}" title="Remove">×</button></li>`
        )
        .join("");
      return `
        <div class="category-card">
          <h3>${cat}</h3>
          <p class="hint muted">${CATEGORY_HINTS[cat] || ""}</p>
          <textarea data-cat="${cat}" rows="3" placeholder="Add a ${cat} sample…"></textarea>
          <div class="add-row">
            <button class="btn" data-add="${cat}">Add sample</button>
          </div>
          <ul class="sample-list">${samples}</ul>
        </div>`;
    })
    .join("");

  el("categoryGrid").querySelectorAll("[data-add]").forEach((btn) => {
    btn.onclick = () => addSample(btn.dataset.add);
  });
  el("categoryGrid").querySelectorAll(".x").forEach((btn) => {
    btn.onclick = () => removeSample(btn.dataset.id);
  });
}

async function addSample(cat) {
  const ta = el("categoryGrid").querySelector(`textarea[data-cat="${cat}"]`);
  const content = ta.value.trim();
  if (!content) return;
  await api.post(`/api/twins/${state.current.id}/samples`, { category: cat, content });
  ta.value = "";
  await reloadCurrent();
}

async function removeSample(id) {
  await api.del(`/api/twins/${state.current.id}/samples/${id}`);
  await reloadCurrent();
}

async function reloadCurrent() {
  const id = state.current.id;
  state.current = await api.get(`/api/twins/${id}`);
  renderDetail();
  await refreshTwins();
}

async function trainTwin() {
  const btn = el("trainBtn");
  const status = el("trainStatus");
  btn.disabled = true;
  status.textContent = "Synthesizing persona… this can take a moment.";
  try {
    state.current = await api.post(`/api/twins/${state.current.id}/train`);
    status.textContent = "Done — persona updated.";
    renderDetail();
    await refreshTwins();
    selectTab("persona");
  } catch (e) {
    status.textContent = "Error: " + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Persona
// ---------------------------------------------------------------------------
function renderPersona() {
  const p = state.current.persona;
  const view = el("personaView");
  if (!p) {
    view.innerHTML = `<p class="muted">No persona yet. Add training samples and synthesize.</p>`;
    return;
  }
  view.innerHTML = `
    <div class="persona-summary">${escapeHtml(p.summary || "")}</div>
    ${section("Writing style", p.writing_style)}
    ${section("Decision-making", p.decision_making)}
    ${section("Knowledge", p.knowledge)}
    ${section("Personality", p.personality)}
  `;
}

function section(title, obj) {
  if (!obj) return "";
  const rows = Object.entries(obj)
    .map(([k, v]) => {
      const label = k.replace(/_/g, " ");
      let val;
      if (Array.isArray(v)) {
        val = `<div class="chips">${v.map((x) => `<span class="chip">${escapeHtml(String(x))}</span>`).join("")}</div>`;
      } else {
        val = `<div class="v">${escapeHtml(String(v))}</div>`;
      }
      return `<div class="k">${label}</div>${val}`;
    })
    .join("");
  return `<div class="persona-section">
            <h3>${title}</h3>
            <div class="kv">${rows}</div>
          </div>`;
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------
async function refreshConversations() {
  state.conversations = await api.get(`/api/twins/${state.current.id}/conversations`);
  renderConversations();
}

function renderConversations() {
  const list = el("conversationList");
  if (!state.conversations.length) {
    list.innerHTML = `<p class="muted" style="font-size:.78rem">No saved chats yet.</p>`;
    return;
  }
  list.innerHTML = state.conversations
    .map(
      (c) => `<div class="conversation-item ${c.id === state.conversationId ? "active" : ""}" data-id="${c.id}">
                <div class="title">
                  <div>${escapeHtml(c.title)}</div>
                  <div class="mode">${c.mode} · ${c.message_count} msgs</div>
                </div>
                <button class="x" data-del="${c.id}" title="Delete">×</button>
              </div>`
    )
    .join("");
  list.querySelectorAll(".conversation-item").forEach((item) => {
    item.onclick = (e) => {
      if (e.target.dataset.del) return;
      openConversation(Number(item.dataset.id));
    };
  });
  list.querySelectorAll("[data-del]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      await api.del(`/api/conversations/${btn.dataset.del}`);
      if (Number(btn.dataset.del) === state.conversationId) newChat();
      await refreshConversations();
    };
  });
}

async function openConversation(id) {
  const conv = await api.get(`/api/conversations/${id}`);
  state.conversationId = conv.id;
  state.chat = conv.messages.map((m) => ({ role: m.role, content: m.content }));
  el("modeSelect").value = conv.mode;
  el("chatTitle").textContent = conv.title;
  renderConversations();
  renderChat();
}

function newChat() {
  state.conversationId = null;
  state.chat = [];
  el("chatTitle").textContent = "New chat";
  const si = el("searchInput");
  if (si) si.value = "";
  renderChat();
  renderConversations();
}

// ---------------------------------------------------------------------------
// Chat (streaming)
// ---------------------------------------------------------------------------
function renderChat() {
  const win = el("chatWindow");
  if (!state.chat.length) {
    win.innerHTML = `<p class="muted" style="margin:auto">Say hello to ${escapeHtml(
      state.current ? state.current.name : "your twin"
    )}.</p>`;
  } else {
    win.innerHTML = state.chat
      .map((m) => `<div class="bubble ${m.role}">${escapeHtml(m.content)}</div>`)
      .join("");
    win.scrollTop = win.scrollHeight;
  }
  updateRegenButton();
}

function updateRegenButton() {
  const last = state.chat[state.chat.length - 1];
  const canRegen =
    !state.streaming &&
    state.conversationId &&
    last &&
    last.role === "assistant" &&
    last.content &&
    !last.content.startsWith("[error");
  el("regenBtn").hidden = !canRegen;
}

async function regenerate() {
  if (!state.conversationId || state.streaming) return;
  if (state.chat.length && state.chat[state.chat.length - 1].role === "assistant") {
    state.chat.pop(); // the server will drop and replace it too
  }
  state.chat.push({ role: "assistant", content: "" });
  const idx = state.chat.length - 1;
  state.streaming = true;
  el("sendBtn").disabled = true;
  renderChat();
  try {
    const resp = await fetch(`/api/conversations/${state.conversationId}/regenerate`, {
      method: "POST",
    });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      state.chat[idx].content += decoder.decode(value, { stream: true });
      renderChat();
    }
  } catch (err) {
    state.chat[idx].content = "[error: " + err.message + "]";
  } finally {
    state.streaming = false;
    el("sendBtn").disabled = false;
    renderChat();
    await refreshConversations();
  }
}

// ---------------------------------------------------------------------------
// Cross-conversation search
// ---------------------------------------------------------------------------
let searchTimer = null;
function onSearchInput(value) {
  clearTimeout(searchTimer);
  const q = value.trim();
  if (!q) {
    renderConversations();
    return;
  }
  searchTimer = setTimeout(() => runSearch(q), 200);
}

async function runSearch(q) {
  const hits = await api.get(
    `/api/twins/${state.current.id}/search?q=${encodeURIComponent(q)}`
  );
  const list = el("conversationList");
  if (!hits.length) {
    list.innerHTML = `<p class="muted" style="font-size:.78rem">No matches.</p>`;
    return;
  }
  list.innerHTML = hits
    .map(
      (h) => `<div class="conversation-item" data-id="${h.conversation_id}">
                <div class="title">
                  <div>${escapeHtml(h.conversation_title)}</div>
                  <div class="mode">${h.role}: ${escapeHtml(h.snippet)}</div>
                </div>
              </div>`
    )
    .join("");
  list.querySelectorAll(".conversation-item").forEach((item) => {
    item.onclick = () => {
      el("searchInput").value = "";
      openConversation(Number(item.dataset.id));
    };
  });
}

async function sendChat(e) {
  e.preventDefault();
  if (state.streaming) return;
  const input = el("chatInput");
  const text = input.value.trim();
  if (!text) return;
  if (!state.current.trained) {
    alert("Train this twin before chatting with it.");
    return;
  }
  input.value = "";
  state.chat.push({ role: "user", content: text });
  state.chat.push({ role: "assistant", content: "" });
  renderChat();

  const idx = state.chat.length - 1;
  state.streaming = true;
  el("sendBtn").disabled = true;

  try {
    const resp = await fetch(`/api/twins/${state.current.id}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: el("modeSelect").value,
        content: text,
        conversation_id: state.conversationId, // null starts a new thread
      }),
    });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);

    // The server tells us which conversation this turn belongs to.
    const cid = resp.headers.get("X-Conversation-Id");
    if (cid) state.conversationId = Number(cid);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      state.chat[idx].content += decoder.decode(value, { stream: true });
      renderChat();
    }
  } catch (err) {
    state.chat[idx].content = "[error: " + err.message + "]";
    renderChat();
  } finally {
    state.streaming = false;
    el("sendBtn").disabled = false;
    await refreshConversations(); // pick up the new title / ordering
  }
}

// ---------------------------------------------------------------------------
// Export / import
// ---------------------------------------------------------------------------
async function exportTwin() {
  const data = await api.get(`/api/twins/${state.current.id}/export`);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safe = data.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  a.href = url;
  a.download = `twin-${safe || "export"}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function importTwinFromFile(file) {
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const created = await api.post("/api/twins/import", {
      name: data.name,
      owner: data.owner || "",
      tagline: data.tagline || "",
      persona: data.persona || null,
      samples_by_category: data.samples_by_category || {},
    });
    await refreshTwins();
    await openTwin(created.id);
  } catch (err) {
    alert("Import failed: " + err.message);
  }
}

// ---------------------------------------------------------------------------
// Tabs & global UI
// ---------------------------------------------------------------------------
function selectTab(name) {
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name)
  );
  document.querySelectorAll(".tab-panel").forEach((p) =>
    p.classList.toggle("hidden", p.dataset.panel !== name)
  );
}

function wireGlobalUI() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => selectTab(t.dataset.tab);
  });
  el("trainBtn").onclick = trainTwin;
  el("chatForm").onsubmit = sendChat;
  el("newChatBtn").onclick = newChat;
  el("regenBtn").onclick = regenerate;
  el("searchInput").oninput = (e) => onSearchInput(e.target.value);
  el("exportTwinBtn").onclick = exportTwin;

  // Auth
  el("authBtn").onclick = () => (state.user ? logout() : openAuthModal());
  el("authCancel").onclick = () => el("authModal").classList.add("hidden");
  el("authToggle").onclick = () => {
    state.authMode = state.authMode === "register" ? "login" : "register";
    applyAuthMode();
    el("authError").textContent = "";
  };
  el("authForm").onsubmit = (e) => {
    e.preventDefault();
    submitAuth();
  };
  el("importBtn").onclick = () => el("importFile").click();
  el("importFile").onchange = (e) => {
    const file = e.target.files[0];
    if (file) importTwinFromFile(file);
    e.target.value = "";
  };
  el("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat(e);
    }
  });

  el("deleteTwinBtn").onclick = async () => {
    if (!confirm(`Delete ${state.current.name} and all its training data?`)) return;
    await api.del(`/api/twins/${state.current.id}`);
    state.current = null;
    twinDetail.classList.add("hidden");
    emptyState.classList.remove("hidden");
    await refreshTwins();
  };

  // Modal
  el("newTwinBtn").onclick = () => el("modal").classList.remove("hidden");
  el("cancelModal").onclick = () => el("modal").classList.add("hidden");
  el("newTwinForm").onsubmit = async (e) => {
    e.preventDefault();
    const payload = {
      name: el("twinName").value.trim(),
      owner: el("twinOwner").value.trim(),
      tagline: el("twinTagline").value.trim(),
    };
    const created = await api.post("/api/twins", payload);
    el("modal").classList.add("hidden");
    el("newTwinForm").reset();
    await refreshTwins();
    await openTwin(created.id);
  };
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

boot().catch((e) => {
  document.body.innerHTML = `<div style="padding:40px;color:#ff6b6b">Failed to start: ${e.message}</div>`;
});
