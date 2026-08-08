"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const runtimeApp = globalThis.app;
const controlVaultRoot = runtimeApp.vault.adapter.getBasePath?.() || runtimeApp.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const { el, clear, button } = loadControl("scripts/lib/dom.js");
const { notify } = loadControl("scripts/lib/notify.js");
const { createInternalLink } = loadControl("scripts/lib/internal-link.js");
const { listTransportRuns } = loadControl("scripts/lib/git-transport.js");
const { listPlanRecords } = loadControl("scripts/plans/plan-store.js");

function formatTimestamp(value) {
  if (!value) return "Unknown timestamp";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function currentPlanLabels(app) {
  try {
    return new Map(listPlanRecords(app).map((record) => [
      record.slug,
      String(record.payload?.label || record.label || record.slug),
    ]));
  } catch (error) {
    console.warn("Plan History could not load current plan labels:", error);
    return new Map();
  }
}

function outcomeMap(run) {
  return new Map((run.decisions || []).map((decision) => [decision.identity, decision.outcome]));
}

function resultSet(run) {
  return new Set((run.results || []).map((record) => record.identity));
}

function runCounts(run) {
  const outcomes = outcomeMap(run);
  let accepted = 0;
  let declined = 0;
  for (const outcome of outcomes.values()) {
    if (outcome === "accepted") accepted += 1;
    else if (outcome === "declined") declined += 1;
  }
  const results = resultSet(run).size;
  const total = run.dispatch?.records?.length || run.count || 0;
  return {
    total,
    results,
    accepted,
    declined,
    pendingReview: Math.max(0, results - accepted - declined),
    awaitingResult: Math.max(0, total - results),
  };
}

function countSummary(run) {
  const counts = runCounts(run);
  const parts = [`${counts.total} file${counts.total === 1 ? "" : "s"}`];
  if (counts.accepted) parts.push(`${counts.accepted} accepted`);
  if (counts.declined) parts.push(`${counts.declined} declined`);
  if (counts.pendingReview) parts.push(`${counts.pendingReview} awaiting review`);
  if (counts.awaitingResult) parts.push(`${counts.awaitingResult} awaiting result`);
  return parts.join(" · ");
}

function recordStatus(run, identity) {
  const decision = outcomeMap(run).get(identity);
  if (decision) return decision;
  if (resultSet(run).has(identity)) return "awaiting review";
  return "awaiting result";
}

function addField(parent, label, value) {
  const row = parent.appendChild(el("div"));
  row.style.margin = "0.2rem 0";
  row.appendChild(el("strong", { text: `${label}: ` }));
  row.appendChild(document.createTextNode(value || "—"));
}

function renderRun(app, parent, run) {
  const details = parent.appendChild(el("details"));
  details.style.margin = "0.6rem 0";
  details.style.padding = "0.55rem 0.7rem";
  details.style.border = "1px solid var(--background-modifier-border)";
  details.style.borderRadius = "6px";

  const summary = details.appendChild(el("summary"));
  summary.style.cursor = "pointer";
  summary.appendChild(el("strong", { text: formatTimestamp(run.created_at) }));
  summary.appendChild(document.createTextNode(` — ${countSummary(run)}`));

  const metadata = details.appendChild(el("div"));
  metadata.style.margin = "0.6rem 0";
  addField(metadata, "Run timestamp", run.created_at);
  addField(metadata, "Run identity", run.run_identity);
  addField(metadata, "Source branch", run.source_branch);
  addField(metadata, "Source commit", run.source_commit);
  addField(metadata, "Transport branch", run.branch);
  addField(metadata, "State", run.status);

  const records = run.dispatch?.records || [];
  if (!records.length) {
    details.appendChild(el("p", { text: "No file records were retained for this run." }));
    return;
  }

  const table = details.appendChild(el("table"));
  table.style.width = "100%";
  table.appendChild(el("thead", {}, [
    el("tr", {}, [
      el("th", { text: "File slug" }),
      el("th", { text: "Path" }),
      el("th", { text: "Outcome" }),
    ]),
  ]));
  const body = table.appendChild(el("tbody"));

  for (const record of records) {
    const row = body.appendChild(el("tr"));
    row.appendChild(el("td", { text: record.identity || "—" }));
    const pathCell = row.appendChild(el("td"));
    const file = record.source_path ? app.vault.getAbstractFileByPath(record.source_path) : null;
    if (file?.extension === "md") {
      createInternalLink(pathCell, app, record.source_path, record.source_path);
    } else {
      pathCell.textContent = record.source_path || "—";
    }
    row.appendChild(el("td", { text: recordStatus(run, record.identity) }));
  }
}

function renderPlanHistory({ app, container }) {
  clear(container);
  container.appendChild(el("h2", { text: "Plan History" }));
  container.appendChild(el("p", {
    text: "Runs are grouped by the durable plan slug. Each occurrence retains its own run timestamp and transport metadata.",
  }));

  const toolbar = container.appendChild(el("div"));
  toolbar.style.display = "flex";
  toolbar.style.gap = "0.5rem";
  toolbar.style.marginBottom = "0.8rem";
  const filter = toolbar.appendChild(el("input", {
    type: "search",
    placeholder: "Filter plan slug or label",
  }));
  filter.style.minWidth = "22rem";
  const refresh = toolbar.appendChild(button("Refresh", () => { notify("Refreshing plan history…"); draw(true); }));
  const output = container.appendChild(el("div"));

  function draw(notifyUser = false) {
    output.replaceChildren();
    let runs;
    try {
      runs = listTransportRuns(app);
    } catch (error) {
      output.appendChild(el("pre", { text: error.message || String(error) }));
      if (notifyUser) notify(`Plan history refresh failed: ${error.message || error}`, 10000);
      return;
    }

    const labels = currentPlanLabels(app);
    const grouped = new Map();
    for (const run of runs) {
      const slug = String(run.plan_identity || "unknown-plan").trim() || "unknown-plan";
      if (!grouped.has(slug)) grouped.set(slug, []);
      grouped.get(slug).push(run);
    }

    const needle = filter.value.trim().toLowerCase();
    const plans = [...grouped.entries()]
      .filter(([slug]) => !needle || slug.toLowerCase().includes(needle) || String(labels.get(slug) || "").toLowerCase().includes(needle))
      .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));

    if (!plans.length) {
      output.appendChild(el("p", { text: runs.length ? "No plans match the filter." : "No dispatch history was found." }));
      return;
    }

    for (const [slug, planRuns] of plans) {
      const card = output.appendChild(el("section"));
      card.style.border = "1px solid var(--background-modifier-border)";
      card.style.borderRadius = "8px";
      card.style.padding = "0.8rem";
      card.style.margin = "0.8rem 0";

      const label = labels.get(slug);
      card.appendChild(el("h3", { text: label && label !== slug ? label : slug }));
      if (label && label !== slug) card.appendChild(el("div", { text: slug }));
      card.appendChild(el("p", { text: `${planRuns.length} run${planRuns.length === 1 ? "" : "s"}` }));

      for (const run of planRuns) renderRun(app, card, run);
    }
    if (notifyUser) notify(`Plan history refreshed: ${runs.length} run(s).`);
  }

  filter.addEventListener("input", draw);
  draw();
}

module.exports = { renderPlanHistory };
