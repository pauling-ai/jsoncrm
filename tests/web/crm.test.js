import { describe, it, expect } from "vitest";
import {
  esc,
  buildPageUrl,
  coerceValue,
  formatCellValue,
  highlightMatch,
  isCompetitor,
  renderPaginationHTML,
  sortRows,
  filterRows,
} from "../../src/web/crm.js";

describe("esc", () => {
  it("escapes HTML entities", () => {
    expect(esc("<script>alert(1)</script>")).toBe("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(esc("a & b")).toBe("a &amp; b");
  });
});

describe("buildPageUrl", () => {
  it("builds basic URL", () => {
    expect(buildPageUrl("leads")).toBe("/api/data/leads?limit=100&offset=0");
  });

  it("includes search query", () => {
    expect(buildPageUrl("leads", { q: "alice" })).toBe("/api/data/leads?limit=100&offset=0&q=alice");
  });

  it("includes sort params", () => {
    expect(buildPageUrl("leads", { sortKey: "company", sortDir: "desc" }))
      .toBe("/api/data/leads?limit=100&offset=0&sort_key=company&sort_dir=desc");
  });

  it("includes pagination", () => {
    expect(buildPageUrl("leads", { offset: 50, limit: 25 }))
      .toBe("/api/data/leads?limit=25&offset=50");
  });
});

describe("coerceValue", () => {
  it("parses int", () => {
    expect(coerceValue("42", "int")).toBe(42);
    expect(coerceValue("", "int")).toBeNull();
    expect(coerceValue("abc", "int")).toBeNull();
  });

  it("parses float", () => {
    expect(coerceValue("3.14", "float")).toBe(3.14);
    expect(coerceValue("", "float")).toBeNull();
  });

  it("parses bool", () => {
    expect(coerceValue("true", "bool")).toBe(true);
    expect(coerceValue("false", "bool")).toBe(false);
    expect(coerceValue("", "bool")).toBeNull();
  });

  it("returns string as-is", () => {
    expect(coerceValue("hello", "str")).toBe("hello");
    expect(coerceValue("", "str")).toBeNull();
  });
});

describe("formatCellValue", () => {
  it("formats stars", () => {
    const result = formatCellValue("⭐⭐⭐⭐", "score");
    expect(result.html).toContain("score-stars");
    expect(result.text).toBe("⭐⭐⭐⭐");
  });

  it("formats disqualified", () => {
    const result = formatCellValue("❌", "score");
    expect(result.html).toContain("score-x");
  });

  it("formats null", () => {
    const result = formatCellValue(null, "name");
    expect(result.html).toContain("null-val");
  });

  it("formats plain string", () => {
    const result = formatCellValue("Alice", "name");
    expect(result.html).toBe("Alice");
  });
});

describe("highlightMatch", () => {
  it("highlights matching text", () => {
    expect(highlightMatch("Alice Testerson", "ali")).toContain("<mark>Ali</mark>");
  });

  it("returns escaped text when no match", () => {
    expect(highlightMatch("Bob", "ali")).toBe("Bob");
  });

  it("returns empty for empty query", () => {
    expect(highlightMatch("Alice", "")).toBe("Alice");
  });
});

describe("isCompetitor", () => {
  const competitors = [
    { name: "Schrödinger" },
    { name: "BioTech Corp" },
  ];

  it("detects competitor by substring", () => {
    expect(isCompetitor("Schrödinger Inc", competitors)).toBe(true);
    expect(isCompetitor("BioTech Corp Ltd", competitors)).toBe(true);
  });

  it("returns false for non-competitor", () => {
    expect(isCompetitor("Acme Pharma", competitors)).toBe(false);
  });

  it("returns false for empty company", () => {
    expect(isCompetitor("", competitors)).toBe(false);
    expect(isCompetitor(null, competitors)).toBe(false);
  });
});

describe("renderPaginationHTML", () => {
  it("renders first page", () => {
    const html = renderPaginationHTML(250, 0, 100);
    expect(html).toContain("Page <strong>1</strong> of 3");
    expect(html).toContain("disabled");
    expect(html).toContain("Showing 1–100 of 250");
  });

  it("renders middle page", () => {
    const html = renderPaginationHTML(250, 100, 100);
    expect(html).toContain("Page <strong>2</strong> of 3");
    expect(html).not.toContain('disabled">← Prev');
    expect(html).not.toContain('disabled">Next →');
  });

  it("renders last page", () => {
    const html = renderPaginationHTML(250, 200, 100);
    expect(html).toContain("Page <strong>3</strong> of 3");
    expect(html).toContain('disabled>Next →');
    expect(html).toContain("Showing 201–250 of 250");
  });

  it("handles empty dataset", () => {
    const html = renderPaginationHTML(0, 0, 100);
    expect(html).toContain("Showing 0–0 of 0");
  });
});

describe("sortRows", () => {
  const rows = [
    { name: "Charlie", score: 3 },
    { name: "Alice", score: 1 },
    { name: "Bob", score: 2 },
  ];

  it("sorts ascending", () => {
    const sorted = sortRows(rows, "name", "asc");
    expect(sorted.map(r => r.name)).toEqual(["Alice", "Bob", "Charlie"]);
  });

  it("sorts descending", () => {
    const sorted = sortRows(rows, "name", "desc");
    expect(sorted.map(r => r.name)).toEqual(["Charlie", "Bob", "Alice"]);
  });

  it("puts nulls last", () => {
    const withNull = [...rows, { name: null, score: 0 }];
    const sorted = sortRows(withNull, "name", "asc");
    expect(sorted[sorted.length - 1].name).toBeNull();
  });
});

describe("filterRows", () => {
  const rows = [
    { name: "Alice", company: "Acme" },
    { name: "Bob", company: "Bio" },
    { name: "Charlie", company: "Acme Bio" },
  ];

  it("filters by query across all fields", () => {
    expect(filterRows(rows, "alice")).toHaveLength(1);
    expect(filterRows(rows, "acme")).toHaveLength(2);
    expect(filterRows(rows, "bio")).toHaveLength(2);
  });

  it("returns all rows for empty query", () => {
    expect(filterRows(rows, "")).toHaveLength(3);
  });
});
