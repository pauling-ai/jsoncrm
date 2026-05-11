import { esc, buildPageUrl, coerceValue, formatCellValue, highlightMatch, isCompetitor, renderPaginationHTML } from "./crm.js";

// ── State ─────────────────────────────────────────────────────────────────────
let config = {};
let stages = [];
let activeStage = "";
let rows = {};           // { stage: [current page rows] }
let columns = {};        // { stage: [{key, type}] }
let competitors = { companies: [], people: [] };
let searchQuery = "";
let selectedCell = null; // { stage, ri, ci }
let selectedRow = null;  // { stage, ri }
let currentOffset = 0;
let pageLimit = 100;
let currentSortKey = "";
let currentSortDir = "asc";
let searchDebounceTimer = null;
let resizing = null;

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  const [cfgRes, compRes] = await Promise.all([
    fetch("/api/config").then(r => r.json()),
    fetch("/api/competitors").then(r => r.json()),
  ]);
  config = cfgRes;
  stages = config.stages.map(s => s.name);
  competitors = compRes;
  if (config.github_configured) {
    document.getElementById("btn-pr").style.display = "inline-flex";
  }
  renderStageTabs();
  await loadStage(stages[0]);
}

async function loadStage(stage) {
  activeStage = stage;
  currentOffset = 0;
  searchQuery = "";
  currentSortKey = "";
  currentSortDir = "asc";
  document.getElementById("search").value = "";
  await fetchPage();
}

async function fetchPage() {
  const url = buildPageUrl(activeStage, {
    offset: currentOffset,
    limit: pageLimit,
    q: searchQuery,
    sortKey: currentSortKey,
    sortDir: currentSortDir,
  });
  const [dataRes, schemaRes] = await Promise.all([
    fetch(url).then(r => r.json()),
    fetch(`/api/schema/${activeStage}`).then(r => r.json()),
  ]);
  columns[activeStage] = Object.entries(schemaRes.columns).map(([key, type]) => ({ key, type }));
  rows[activeStage] = dataRes.rows;
  renderStageTabs();
  renderHeader();
  renderBody();
  renderPagination(dataRes.total_filtered, dataRes.offset, dataRes.limit);
}

// ── Stage tabs ────────────────────────────────────────────────────────────────
function renderStageTabs() {
  const container = document.getElementById("stage-tabs");
  container.innerHTML = "";
  stages.forEach(stage => {
    const tab = document.createElement("div");
    tab.className = "stage-tab" + (stage === activeStage ? " active" : "");
    // Fetch total count from a lightweight endpoint would be better, but we can
    // use the current page's total for the active stage and 0 for others
    const count = rows[stage]?.length ?? 0;
    tab.innerHTML = `${esc(stage)} <span class="badge">${count}</span>`;
    tab.onclick = () => loadStage(stage);
    container.appendChild(tab);
  });
}

// ── Render header ─────────────────────────────────────────────────────────────
function renderHeader() {
  const hr = document.getElementById("header-row");
  hr.innerHTML = "";
  const rn = document.createElement("th");
  rn.className = "row-num-col";
  rn.innerHTML = `<div class="th-inner">#</div>`;
  hr.appendChild(rn);

  const cols = columns[activeStage] || [];
  cols.forEach((col, ci) => {
    const th = document.createElement("th");
    th.dataset.ci = ci;
    th.style.position = "relative";
    const sortIndicator = currentSortKey === col.key ? (currentSortDir === "asc" ? "↑" : "↓") : "⇅";
    th.innerHTML = `
      <div class="th-inner">
        ${esc(col.key)}<span class="col-type">${col.type}</span>
        <span class="sort-btn" onclick="toggleSort(${ci})">${sortIndicator}</span>
      </div>
      <div class="resize-handle" data-ci="${ci}"></div>`;
    hr.appendChild(th);

    th.querySelector(".resize-handle").addEventListener("mousedown", e => {
      e.preventDefault();
      const startX = e.clientX;
      const startW = th.offsetWidth;
      th.classList.add("resizing");
      function onMove(e) {
        th.style.minWidth = Math.max(60, startW + e.clientX - startX) + "px";
      }
      function onUp() {
        th.classList.remove("resizing");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
}

// ── Render body ───────────────────────────────────────────────────────────────
function renderBody() {
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = "";
  const q = searchQuery.toLowerCase();
  const stageRows = rows[activeStage] || [];
  const cols = columns[activeStage] || [];

  stageRows.forEach((row, idx) => {
    const ri = currentOffset + idx;
    const tr = document.createElement("tr");
    tr.dataset.ri = ri;

    const score = row.score;
    if (score === "❌") tr.classList.add("disqualified");

    const company = row.company;
    const rowIsCompetitor = isCompetitor(company, competitors.companies);
    if (rowIsCompetitor) tr.classList.add("competitor");

    const rnTd = document.createElement("td");
    rnTd.className = "row-num";
    rnTd.textContent = ri + 1;
    rnTd.title = "Click to select row";
    rnTd.onclick = () => selectRow(ri);
    tr.appendChild(rnTd);

    cols.forEach((col, ci) => {
      const td = document.createElement("td");
      td.dataset.ri = ri; td.dataset.ci = ci;
      const val = row[col.key];
      const display = document.createElement("div");
      display.className = "cell-display";

      const formatted = formatCellValue(val, col.key);
      display.innerHTML = formatted.html;
      if (q) {
        display.innerHTML = highlightMatch(formatted.text, q);
      }

      if (col.key === "company" && rowIsCompetitor) {
        display.innerHTML += ` <span class="competitor-badge">COMPETITOR</span>`;
      }

      display.onclick = () => selectCell(ri, ci);
      display.ondblclick = () => startEdit(ri, ci, td);

      const editor = document.createElement("textarea");
      editor.className = "cell-editor";
      editor.rows = 1;
      editor.value = val === null || val === undefined ? "" : String(val);
      editor.onkeydown = e => handleEditorKey(e, ri, ci, td);
      editor.oninput = () => { editor.style.height = "auto"; editor.style.height = editor.scrollHeight + "px"; };
      editor.onblur = () => commitEdit(ri, ci, td, editor.value);

      td.appendChild(display);
      td.appendChild(editor);
      tr.appendChild(td);
    });

    const actionTd = document.createElement("td");
    actionTd.style.borderRight = "none";
    actionTd.style.whiteSpace = "nowrap";
    const actions = document.createElement("div");
    actions.className = "pipeline-actions";
    const stageIdx = stages.indexOf(activeStage);
    if (stageIdx < stages.length - 1 && row.linkedin_url) {
      const btn = document.createElement("button");
      btn.textContent = "→ " + stages[stageIdx + 1];
      btn.onclick = (e) => { e.stopPropagation(); promoteRow(row.linkedin_url); };
      actions.appendChild(btn);
    }
    if (stageIdx > 0 && row.linkedin_url) {
      const btn = document.createElement("button");
      btn.textContent = "← " + stages[stageIdx - 1];
      btn.onclick = (e) => { e.stopPropagation(); demoteRow(row.linkedin_url); };
      actions.appendChild(btn);
    }
    actionTd.appendChild(actions);
    tr.appendChild(actionTd);

    tbody.appendChild(tr);
  });

  const addRowTr = document.createElement("tr");
  addRowTr.id = "add-row-row";
  const addTd = document.createElement("td");
  addTd.colSpan = cols.length + 2;
  const addBtn = document.createElement("button");
  addBtn.textContent = "＋ Add row";
  addBtn.onclick = () => addRowFn();
  addTd.appendChild(addBtn);
  addRowTr.appendChild(addTd);
  tbody.appendChild(addRowTr);
}

// ── Pagination ────────────────────────────────────────────────────────────────
function renderPagination(total, offset, limit) {
  const container = document.getElementById("pagination");
  if (!container) return;
  container.innerHTML = renderPaginationHTML(total, offset, limit);
}

function goToPage(pageNum) {
  currentOffset = (pageNum - 1) * pageLimit;
  fetchPage();
}

// ── Cell editing ──────────────────────────────────────────────────────────────
function selectCell(ri, ci) {
  clearSelection();
  selectedCell = { stage: activeStage, ri, ci };
  selectedRow = { stage: activeStage, ri };
  const td = document.querySelector(`td[data-ri="${ri}"][data-ci="${ci}"]`);
  if (td) td.classList.add("selected");
  document.getElementById("btn-delete").disabled = false;

  const cols = columns[activeStage] || [];
  const localIdx = ri - currentOffset;
  const val = rows[activeStage][localIdx][cols[ci].key];
  document.getElementById("cell-ref").textContent = `${cols[ci].key}[${ri+1}]`;
  document.getElementById("cell-val").textContent = val === null || val === undefined ? "null" : String(val);
  document.getElementById("statusbar").classList.add("show");
}

function selectRow(ri) {
  clearSelection();
  selectedRow = { stage: activeStage, ri };
  document.querySelectorAll(`td[data-ri="${ri}"]`).forEach(td => td.style.background = "var(--cell-sel)");
  document.getElementById("btn-delete").disabled = false;
}

function clearSelection() {
  document.querySelectorAll("td.selected").forEach(td => td.classList.remove("selected"));
  document.querySelectorAll("td[style*='background: var(--cell-sel)']").forEach(td => td.style.background = "");
  selectedCell = null;
  selectedRow = null;
  document.getElementById("btn-delete").disabled = true;
  document.getElementById("statusbar").classList.remove("show");
}

function startEdit(ri, ci, td) {
  document.querySelectorAll("td.editing").forEach(t => {
    const ri2 = t.dataset.ri, ci2 = t.dataset.ci;
    commitEdit(Number(ri2), Number(ci2), t, t.querySelector(".cell-editor").value);
  });
  td.classList.add("editing");
  const editor = td.querySelector(".cell-editor");
  const cols = columns[activeStage] || [];
  const localIdx = ri - currentOffset;
  editor.value = rows[activeStage][localIdx][cols[ci].key] ?? "";
  editor.style.height = "auto";
  editor.style.height = editor.scrollHeight + "px";
  editor.focus();
  editor.select();
}

function handleEditorKey(e, ri, ci, td) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commitEdit(ri, ci, td, td.querySelector(".cell-editor").value); }
  if (e.key === "Escape") { td.classList.remove("editing"); }
  if (e.key === "Tab") {
    e.preventDefault();
    commitEdit(ri, ci, td, td.querySelector(".cell-editor").value);
    const nci = ci + (e.shiftKey ? -1 : 1);
    const cols = columns[activeStage] || [];
    if (nci >= 0 && nci < cols.length) {
      const ntd = document.querySelector(`td[data-ri="${ri}"][data-ci="${nci}"]`);
      if (ntd) { selectCell(ri, nci); startEdit(ri, nci, ntd); }
    }
  }
}

async function commitEdit(ri, ci, td, rawVal) {
  td.classList.remove("editing");
  const cols = columns[activeStage] || [];
  const col = cols[ci];
  const localIdx = ri - currentOffset;
  let val = rawVal;
  if (val === "" && (rows[activeStage][localIdx][col.key] === null || rows[activeStage][localIdx][col.key] === undefined)) return;

  val = coerceValue(rawVal, col.type);

  const oldVal = rows[activeStage][localIdx][col.key];
  if (JSON.stringify(val) === JSON.stringify(oldVal)) return;

  const record = { ...rows[activeStage][localIdx] };
  record[col.key] = val;

  try {
    const res = await fetch(`/api/data/${activeStage}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates: record }),
    });
    if (!res.ok) {
      const err = await res.json();
      toast("Save failed: " + (err.detail || "unknown"), "error");
      return;
    }
    toast("Saved", "success");
    await fetchPage();
  } catch (e) {
    toast("Save failed: " + e.message, "error");
  }
}

// ── Row ops ───────────────────────────────────────────────────────────────────
async function addRowFn() {
  const cols = columns[activeStage] || [];
  const blank = {};
  cols.forEach(c => { blank[c.key] = null; });

  try {
    const res = await fetch(`/api/data/${activeStage}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record: blank }),
    });
    if (!res.ok) {
      const err = await res.json();
      toast("Add failed: " + (err.detail || "unknown"), "error");
      return;
    }
    toast("Added", "success");
    currentOffset = 0;
    await fetchPage();
    const td = document.querySelector(`td[data-ri="${currentOffset}"][data-ci="0"]`);
    if (td) { selectCell(currentOffset, 0); startEdit(currentOffset, 0, td); }
  } catch (e) {
    toast("Add failed: " + e.message, "error");
  }
}
function addRow() { addRowFn(); }

async function deleteSelectedRow() {
  if (!selectedRow || selectedRow.stage !== activeStage) return;
  const ri = selectedRow.ri;
  const localIdx = ri - currentOffset;
  const row = rows[activeStage][localIdx];
  if (!row) return;

  const identity = {};
  if (row.id) identity.id = row.id;
  else if (row.linkedin_url) identity.linkedin_url = row.linkedin_url;

  try {
    const res = await fetch(`/api/data/${activeStage}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity }),
    });
    if (!res.ok) {
      const err = await res.json();
      toast("Delete failed: " + (err.detail || "unknown"), "error");
      return;
    }
    clearSelection();
    toast("Deleted", "success");
    await fetchPage();
  } catch (e) {
    toast("Delete failed: " + e.message, "error");
  }
}

function revertChanges() {
  if (!confirm("Reload current page from server?")) return;
  fetchPage();
}

// ── Promote / Demote ──────────────────────────────────────────────────────────
async function promoteRow(url) {
  try {
    const res = await fetch("/api/promote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linkedin_url: url }),
    });
    if (!res.ok) {
      const err = await res.json();
      toast("Promote failed: " + (err.detail || "unknown"), "error");
      return;
    }
    toast("Promoted", "success");
    await reloadAllStages();
  } catch (e) {
    toast("Promote failed: " + e.message, "error");
  }
}

async function demoteRow(url) {
  try {
    const res = await fetch("/api/demote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ linkedin_url: url }),
    });
    if (!res.ok) {
      const err = await res.json();
      toast("Demote failed: " + (err.detail || "unknown"), "error");
      return;
    }
    toast("Demoted", "success");
    await reloadAllStages();
  } catch (e) {
    toast("Demote failed: " + e.message, "error");
  }
}

async function reloadAllStages() {
  for (const stage of stages) {
    const dataRes = await fetch(`/api/data/${stage}?limit=${pageLimit}&offset=0`).then(r => r.json());
    rows[stage] = dataRes.rows;
  }
  renderStageTabs();
  renderHeader();
  renderBody();
  renderPagination(rows[activeStage]?.length ?? 0, 0, pageLimit);
}

// ── Sort ──────────────────────────────────────────────────────────────────────
function toggleSort(ci) {
  const cols = columns[activeStage] || [];
  const key = cols[ci].key;
  if (currentSortKey === key) {
    currentSortDir = currentSortDir === "asc" ? "desc" : "asc";
  } else {
    currentSortKey = key;
    currentSortDir = "asc";
  }
  currentOffset = 0;
  fetchPage();
}

// ── Search ────────────────────────────────────────────────────────────────────
function applySearch(q) {
  searchQuery = q;
  currentOffset = 0;
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => fetchPage(), 300);
}

// ── PR modal ──────────────────────────────────────────────────────────────────
function openSaveModal() {
  document.getElementById("diff-summary").innerHTML = `
    <p>All pipeline files will be committed to a new branch and a PR opened.</p>
  `;
  document.getElementById("pr-title").value = `Update CRM via jsoncrm`;
  document.getElementById("modal-overlay").classList.add("open");
  document.getElementById("pr-title").focus();
  document.getElementById("pr-title").select();
}

function closeModal() {
  document.getElementById("modal-overlay").classList.remove("open");
}

async function submitPR() {
  const btn = document.getElementById("btn-submit-pr");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Opening PR…`;

  try {
    const res = await fetch("/api/pr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: document.getElementById("pr-title").value,
        body: document.getElementById("pr-body").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Unknown error");

    closeModal();
    toast(`PR opened → ${data.pr_url}`, "success");
    setTimeout(() => window.open(data.pr_url, "_blank"), 600);
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "Open PR";
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, type = "") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "show " + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ""; }, 3000);
}

// ── Keyboard global ───────────────────────────────────────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { clearSelection(); document.getElementById("modal-overlay").classList.remove("open"); }
  if ((e.metaKey || e.ctrlKey) && e.key === "f") { e.preventDefault(); document.getElementById("search").focus(); }
  if (e.key === "F2" && selectedCell && selectedCell.stage === activeStage) {
    const td = document.querySelector(`td[data-ri="${selectedCell.ri}"][data-ci="${selectedCell.ci}"]`);
    if (td) startEdit(selectedCell.ri, selectedCell.ci, td);
  }
  if (e.key === "Delete" && selectedCell && selectedCell.stage === activeStage && !document.querySelector("td.editing")) {
    commitEdit(selectedCell.ri, selectedCell.ci, document.querySelector(`td[data-ri="${selectedCell.ri}"][data-ci="${selectedCell.ci}"]`), "");
  }
});

function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

init().catch(e => { document.body.innerHTML = `<div style="padding:20px;color:var(--danger)">Error: ${e.message}</div>`; });

// Expose functions needed by inline HTML handlers
window.applySearch = applySearch;
window.addRow = addRow;
window.deleteSelectedRow = deleteSelectedRow;
window.revertChanges = revertChanges;
window.openSaveModal = openSaveModal;
window.closeModal = closeModal;
window.submitPR = submitPR;
window.goToPage = goToPage;
window.toggleSort = toggleSort;

