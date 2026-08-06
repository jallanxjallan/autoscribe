# Plan Index

```dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(vaultRoot, "_control", ...relativePath.split("/")));
const { listPlanRecords } = loadControl("scripts/plans/plan-store.js");

function text(value) {
  return String(value ?? "").trim();
}

function planPayload(record) {
  return record?.payload && typeof record.payload === "object" ? record.payload : record;
}

function orderedSteps(payload) {
  const raw = payload?.steps;
  if (Array.isArray(raw)) return raw;
  if (!raw || typeof raw !== "object") return [];
  return Object.entries(raw)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([, step]) => step);
}

const instructionFiles = new Map();
for (const file of app.vault.getMarkdownFiles()) {
  const cache = app.metadataCache.getFileCache(file);
  const slug = text(cache?.frontmatter?.slug);
  if (!slug) continue;
  instructionFiles.set(slug, { path: file.path, label: text(cache?.frontmatter?.title) || file.basename });
}

function instructionTarget(slug) {
  const value = text(slug);
  if (!value) return null;
  return instructionFiles.get(value) || { path: value, label: value };
}

function appendWikiLink(parent, slug) {
  const target = instructionTarget(slug);
  if (!target) return;
  const link = parent.createEl("a", {
    cls: "internal-link",
    text: target.label,
    attr: { href: target.path, "data-href": target.path },
  });
  link.style.overflowWrap = "anywhere";
}

function instructionGroups(step) {
  const groups = step?.instruction_slugs;
  if (groups && typeof groups === "object" && !Array.isArray(groups)) {
    return {
      standing: Array.isArray(groups.standing) ? groups.standing.filter(Boolean) : [],
      role: Array.isArray(groups.role) ? groups.role.filter(Boolean) : [],
      context: Array.isArray(groups.context) ? groups.context.filter(Boolean) : [],
      task: Array.isArray(groups.task) ? groups.task.filter(Boolean) : [],
    };
  }

  const legacy = text(step?.instruction);
  return { standing: [], role: [], context: [], task: legacy ? [legacy] : [] };
}

function executor(step) {
  const kind = text(step?.kind || step?.type || "llm").toLowerCase();
  if (kind === "llm") {
    return [text(step?.engine), text(step?.model)].filter(Boolean).join(" / ") || "LLM";
  }
  if (kind === "script") return text(step?.script) || "Script not set";
  if (kind === "rag") return text(step?.rag_profile) || "RAG profile not set";
  return kind || "Unknown";
}

function makeCell(row, tag = "td") {
  const cell = row.createEl(tag);
  cell.style.verticalAlign = "top";
  cell.style.padding = ".45rem .65rem";
  cell.style.borderBottom = "1px solid var(--background-modifier-border)";
  return cell;
}

function renderInstructionList(cell, slugs) {
  if (!slugs.length) {
    cell.textContent = "—";
    cell.style.color = "var(--text-faint)";
    return;
  }

  const list = cell.createEl("ul");
  list.style.cssText = "margin:0;padding-left:1.1rem;";
  for (const slug of slugs) {
    const item = list.createEl("li");
    item.style.cssText = "margin:0 0 .2rem 0;overflow-wrap:anywhere;";
    appendWikiLink(item, slug);
  }
}

function renderPlanIndex() {
  let plans;
  try {
    plans = listPlanRecords(app);
  } catch (error) {
    console.error("Plan Index failed:", error);
    dv.paragraph(`**Unable to read plans:** ${error?.message || error}`);
    return;
  }

  if (!plans.length) {
    dv.paragraph("*No plans found in `_plans`.*");
    return;
  }

  const hasStanding = plans.some((record) =>
    orderedSteps(planPayload(record)).some((step) => instructionGroups(step).standing.length)
  );
  let showStanding = false;

  const toolbar = dv.el("div", "", {
    attr: { style: "display:flex;align-items:center;gap:.75rem;margin-bottom:.75rem;" },
  });
  const count = toolbar.createEl("span", {
    text: `${plans.length} plan${plans.length === 1 ? "" : "s"}`,
  });
  count.style.color = "var(--text-muted)";

  let standingButton = null;
  if (hasStanding) {
    standingButton = toolbar.createEl("button", { text: "Show standing" });
    standingButton.setAttribute("type", "button");
  }

  const table = dv.el("table", "", {
    attr: { style: "width:100%;border-collapse:collapse;table-layout:fixed;" },
  });
  const body = table.createEl("tbody");

  function setStandingVisibility() {
    table.querySelectorAll("[data-standing-column]").forEach((cell) => {
      cell.style.display = showStanding ? "table-cell" : "none";
    });
    table.querySelectorAll("[data-plan-span]").forEach((cell) => {
      cell.colSpan = showStanding ? 6 : 5;
    });
    if (standingButton) standingButton.textContent = showStanding ? "Hide standing" : "Show standing";
  }

  for (const record of plans) {
    const payload = planPayload(record);
    const steps = orderedSteps(payload);
    const label = text(payload?.label) || text(record?.slug) || "Untitled plan";
    const slug = text(record?.slug || record?.record_identity);
    const type = text(payload?.type);
    const description = text(payload?.description);

    const planRow = body.createEl("tr");
    const planCell = makeCell(planRow, "th");
    planCell.colSpan = 5;
    planCell.dataset.planSpan = "true";
    planCell.style.cssText += ";padding-top:1rem;background:var(--background-secondary);text-align:left;";
    planCell.createEl("strong", { text: label });
    if (type) planCell.createEl("span", { text: ` · ${type}` });
    if (slug) {
      const slugEl = planCell.createEl("code", { text: slug });
      slugEl.style.cssText = "margin-left:.7rem;font-size:.8em;";
    }

    const descriptionRow = body.createEl("tr");
    const descriptionCell = makeCell(descriptionRow);
    descriptionCell.colSpan = 5;
    descriptionCell.dataset.planSpan = "true";
    descriptionCell.style.cssText += ";color:var(--text-muted);padding-bottom:.75rem;";
    descriptionCell.textContent = description || "No description.";

    const headings = body.createEl("tr");
    const columns = [
      ["Step", "18%", false],
      ["Executor", "17%", false],
      ["Standing", "17%", true],
      ["Role", "21%", false],
      ["Context", "22%", false],
      ["Task", "22%", false],
    ];
    for (const [title, width, isStanding] of columns) {
      if (isStanding && !hasStanding) continue;
      const cell = makeCell(headings, "th");
      cell.style.cssText += `;text-align:left;width:${width};background:var(--background-primary-alt);`;
      if (isStanding) cell.dataset.standingColumn = "true";
      cell.textContent = title;
    }

    if (!steps.length) {
      const emptyRow = body.createEl("tr");
      const emptyCell = makeCell(emptyRow);
      emptyCell.colSpan = 5;
      emptyCell.dataset.planSpan = "true";
      emptyCell.createEl("em", { text: "No steps" });
      continue;
    }

    steps.forEach((step, index) => {
      const row = body.createEl("tr");
      const groups = instructionGroups(step);

      const stepCell = makeCell(row);
      stepCell.createEl("strong", { text: text(step?.label) || `Step ${index + 1}` });
      const kind = text(step?.kind || step?.type || "llm");
      if (kind) {
        const kindLine = stepCell.createEl("div", { text: kind });
        kindLine.style.cssText = "font-size:.85em;color:var(--text-muted);";
      }

      const executorCell = makeCell(row);
      executorCell.textContent = executor(step);
      if (step?.args && typeof step.args === "object" && Object.keys(step.args).length) {
        const args = executorCell.createEl("div", { text: JSON.stringify(step.args) });
        args.style.cssText = "margin-top:.3rem;font-size:.8em;color:var(--text-muted);overflow-wrap:anywhere;";
      }

      if (hasStanding) {
        const standingCell = makeCell(row);
        standingCell.dataset.standingColumn = "true";
        renderInstructionList(standingCell, groups.standing);
      }
      renderInstructionList(makeCell(row), groups.role);
      renderInstructionList(makeCell(row), groups.context);
      renderInstructionList(makeCell(row), groups.task);
    });
  }

  setStandingVisibility();
  standingButton?.addEventListener("click", () => {
    showStanding = !showStanding;
    setStandingVisibility();
  });
}

renderPlanIndex();
```
