/** Pure utility functions for jsoncrm UI — no DOM, no fetch, no globals. */

export function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function buildPageUrl(stage, { offset = 0, limit = 100, q = "", sortKey = "", sortDir = "asc" } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (q) params.set("q", q);
  if (sortKey) {
    params.set("sort_key", sortKey);
    params.set("sort_dir", sortDir);
  }
  return `/api/data/${stage}?${params}`;
}

export function coerceValue(raw, type) {
  if (raw === "") return null;
  if (type === "int") {
    const n = parseInt(raw, 10);
    return Number.isNaN(n) ? null : n;
  }
  if (type === "float") {
    const n = parseFloat(raw);
    return Number.isNaN(n) ? null : n;
  }
  if (type === "bool") return raw === "true";
  return raw;
}

export function formatCellValue(value, columnKey) {
  if (columnKey === "score" && typeof value === "string" && value.startsWith("⭐")) {
    return { html: `<span class="score-stars">${esc(value)}</span>`, text: value };
  }
  if (columnKey === "score" && value === "❌") {
    return { html: `<span class="score-x">${esc(value)}</span>`, text: value };
  }
  if (value === null || value === undefined) {
    return { html: `<span class="null-val">null</span>`, text: "null" };
  }
  const str = String(value);
  return { html: esc(str), text: str };
}

export function highlightMatch(text, query) {
  if (!query) return esc(text);
  const q = query.toLowerCase();
  const str = String(text);
  if (!str.toLowerCase().includes(q)) return esc(str);
  const re = new RegExp(esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  return esc(str).replace(re, m => `<mark>${m}</mark>`);
}

export function isCompetitor(company, competitorList) {
  if (!company || !competitorList || !competitorList.length) return false;
  const lower = company.toLowerCase();
  return competitorList.some(c => c.name && lower.includes(c.name.toLowerCase()));
}

export function renderPaginationHTML(total, offset, limit) {
  const start = total > 0 ? offset + 1 : 0;
  const end = Math.min(offset + limit, total);
  const pages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;
  return `
    <button onclick="goToPage(${currentPage - 1})" ${currentPage <= 1 ? "disabled" : ""}>← Prev</button>
    <span>Page <strong>${currentPage}</strong> of ${pages}</span>
    <button onclick="goToPage(${currentPage + 1})" ${currentPage >= pages ? "disabled" : ""}>Next →</button>
    <span style="color:var(--text-muted)">Showing ${start}–${end} of ${total}</span>
  `;
}

export function sortRows(rows, key, dir) {
  const sorted = [...rows];
  sorted.sort((a, b) => {
    const ra = a[key];
    const rb = b[key];
    if (ra === null && rb !== null) return 1;
    if (rb === null && ra !== null) return -1;
    const va = ra ?? "";
    const vb = rb ?? "";
    if (va < vb) return dir === "asc" ? -1 : 1;
    if (va > vb) return dir === "asc" ? 1 : -1;
    return 0;
  });
  return sorted;
}

export function filterRows(rows, query) {
  if (!query) return rows;
  const q = query.toLowerCase();
  return rows.filter(r =>
    Object.values(r).some(v =>
      String(v ?? "").toLowerCase().includes(q)
    )
  );
}
