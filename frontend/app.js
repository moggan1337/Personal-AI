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
  twins: [],
  current: null, // TwinDetail
  chat: [], // {role, content}
  streaming: false,
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
  await refreshTwins();
  wireGlobalUI();
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
  state.chat = [];
  emptyState.classList.add("hidden");
  twinDetail.classList.remove("hidden");
  renderTwinList();
  renderDetail();
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
// Chat (streaming)
// ---------------------------------------------------------------------------
function renderChat() {
  const win = el("chatWindow");
  win.innerHTML = state.chat
    .map((m) => `<div class="bubble ${m.role}">${escapeHtml(m.content)}</div>`)
    .join("");
  win.scrollTop = win.scrollHeight;
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
        messages: state.chat.slice(0, idx), // history excluding the empty assistant turn
      }),
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
    renderChat();
  } finally {
    state.streaming = false;
    el("sendBtn").disabled = false;
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
  el("clearChatBtn").onclick = () => {
    state.chat = [];
    renderChat();
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
