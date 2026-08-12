---
cssclasses:
  - autoscribe-dashboard
---

# Dashboard

```dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(vaultRoot, "_control", ...relativePath.split("/")));
const { openFileInMain } = loadControl("scripts/lib/workspace.js");
const { readSystemState } = loadControl("scripts/lib/system-state.js");

let notify = (message) => new Notice(message);
try {
  ({ notify } = loadControl("scripts/lib/notify.js"));
} catch (error) {
  console.debug("Dashboard: using Obsidian notices", error);
}

const dashboard = dv.container;
const style = dashboard.createEl("style");
style.textContent = `
  .autoscribe-dashboard .dashboard-toolbar { display:flex; gap:.6rem; flex-wrap:wrap; margin:.6rem 0 1rem; }
  .autoscribe-dashboard .dashboard-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(16rem,1fr)); gap:.75rem; margin:.5rem 0 1.2rem; }
  .autoscribe-dashboard .dashboard-card { border:1px solid var(--background-modifier-border); border-radius:8px; padding:.75rem .9rem; background:var(--background-secondary); }
  .autoscribe-dashboard .dashboard-card h3 { margin:0 0 .45rem; font-size:1rem; }
  .autoscribe-dashboard .dashboard-card p { margin:.2rem 0; }
  .autoscribe-dashboard .dashboard-muted { color:var(--text-muted); }
  .autoscribe-dashboard .dashboard-good { color:var(--color-green); }
  .autoscribe-dashboard .dashboard-warn { color:var(--color-orange); }
  .autoscribe-dashboard .dashboard-bad { color:var(--color-red); }
  .autoscribe-dashboard .dashboard-actions { display:grid; grid-template-columns:repeat(auto-fit,minmax(13rem,1fr)); gap:.5rem; margin:.5rem 0 1.2rem; }
  .autoscribe-dashboard .dashboard-actions button { width:100%; min-height:2.4rem; text-align:left; }
  .autoscribe-dashboard .dashboard-section { margin-top:1.35rem; }
`;

function section(title) {
  return dashboard.createEl("section", { cls: "dashboard-section" }).createEl("h2", { text: title }).parentElement;
}

function card(parent, title) {
  const el = parent.createEl("div", { cls: "dashboard-card" });
  el.createEl("h3", { text: title });
  return el;
}

function line(parent, label, value, cls = "") {
  const row = parent.createEl("p");
  row.createEl("strong", { text: `${label}: ` });
  row.createSpan({ text: String(value), cls });
}

async function openInMain(path) {
  try { await openFileInMain(app, path, { mode: "preview" }); }
  catch (error) { notify(error?.message || String(error), 10000); }
}

function addLink(parent, label, path) {
  const row = parent.createEl("div");
  const anchor = row.createEl("a", { text: label, href: "#" });
  anchor.onclick = async (event) => {
    event.preventDefault();
    await openInMain(path);
  };
}

function addCommand(parent, label, macroPath) {
  const button = parent.createEl("button", { text: label });
  button.onclick = async () => {
    button.disabled = true;
    notify(`Opening ${label}…`);
    try {
      const implementation = pathMod.join(vaultRoot, "_control", ...macroPath.split("/"));
      try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}
      const run = nodeRequire(implementation);
      await run({ app });
    } catch (error) {
      console.error(`${label} failed:`, error);
      notify(`${label} failed: ${error?.message || error}`, 10000);
    } finally {
      button.disabled = false;
    }
  };
}

const stateSection = section("System state");
const toolbar = stateSection.createEl("div", { cls: "dashboard-toolbar" });
const refresh = toolbar.createEl("button", { text: "Refresh state" });
const statusLink = toolbar.createEl("button", { text: "Open full System Status" });
statusLink.onclick = () => openInMain("_control/panels/System Status.md");
const stateGrid = stateSection.createEl("div", { cls: "dashboard-grid" });

async function renderState() {
  refresh.disabled = true;
  refresh.setText("Refreshing…");
  stateGrid.empty();

  const gitCard = card(stateGrid, "Git");
  line(gitCard, "Status", "Loading…", "dashboard-muted");

  const pipelineCard = card(stateGrid, "Pipeline");
  line(pipelineCard, "Status", "Loading…", "dashboard-muted");

  try {
    const system = readSystemState(app);
    if (!system.git) throw new Error(system.errors.git || "Git state unavailable");
    const state = system.git;
    gitCard.empty();
    gitCard.createEl("h3", { text: "Git" });
    const dirty = state.staged + state.modified + state.untracked;
    line(gitCard, "Status", dirty ? `${dirty} changed file${dirty === 1 ? "" : "s"}` : "Clean", dirty ? "dashboard-warn" : "dashboard-good");
    line(gitCard, "Branch", state.branch);
    line(gitCard, "Staged", state.staged);
    line(gitCard, "Modified", state.modified);
    line(gitCard, "Untracked", state.untracked);
    if (state.conflicted) line(gitCard, "Conflicts", state.conflicted, "dashboard-bad");
    line(gitCard, "Remote", state.ahead == null ? "No upstream" : `${state.ahead} ahead / ${state.behind} behind`);
    line(gitCard, "Latest", state.latest || "No commits");

    pipelineCard.empty();
    pipelineCard.createEl("h3", { text: "Pipeline" });
    if (!system.pipeline) {
      pipelineCard.createEl("p", { text: system.errors.pipeline || "Pipeline state unavailable", cls: "dashboard-bad" });
    } else {
      const { counts, feeder_error: feederError, handoffs } = system.pipeline;
      const active = (counts.unclaimed || 0) + (counts.waiting || 0) + (counts.response_pending || 0);
      line(pipelineCard, "Active runs", active, active ? "dashboard-warn" : "dashboard-good");
      line(pipelineCard, "Unclaimed", counts.unclaimed || 0);
      line(pipelineCard, "Processing", counts.waiting || 0);
      line(pipelineCard, "Responses ready", counts.response_pending || 0,
        counts.response_pending ? "dashboard-good" : "");
      line(pipelineCard, "Recent handoffs", handoffs.length);
      line(pipelineCard, "Feeder", feederError ? "Unavailable" : "Connected",
        feederError ? "dashboard-bad" : "dashboard-good");
      if (feederError) pipelineCard.createEl("p", { text: feederError, cls: "dashboard-muted" });
    }
    addLink(pipelineCard, "Open diagnostics", "_control/panels/System Status.md");
  } catch (error) {
    gitCard.empty();
    gitCard.createEl("h3", { text: "Git" });
    gitCard.createEl("p", { text: error?.message || String(error), cls: "dashboard-bad" });
    pipelineCard.empty();
    pipelineCard.createEl("h3", { text: "Pipeline" });
    pipelineCard.createEl("p", { text: "State refresh did not complete.", cls: "dashboard-bad" });
    addLink(pipelineCard, "Open diagnostics", "_control/panels/System Status.md");
  } finally {
    refresh.disabled = false;
    refresh.setText("Refresh state");
  }
}

refresh.onclick = renderState;
await renderState();

const workflow = section("Operations");
const actions = workflow.createEl("div", { cls: "dashboard-actions" });
for (const [label, macro] of [
  ["Create Note", "macros/autoscribe-create-note.js"],
  ["Stage Files", "macros/autoscribe-stage-files.js"],
  ["Define Plan", "macros/autoscribe-define-plan.js"],
  ["Dispatch Run", "macros/autoscribe-dispatch-run.js"],
  ["Write Responses", "macros/autoscribe-write-responses.js"],
  ["Plan History", "macros/autoscribe-plan-history.js"],
  ["File State", "macros/autoscribe-file-state.js"],
  ["File History", "macros/autoscribe-file-history.js"],
]) addCommand(actions, label, macro);

function normalizePath(path) {
  return path.replace(/^\/+|\/+$/g, "").toLowerCase();
}

function resolveFolderPath(requestedPath) {
  const exact = app.vault.getAbstractFileByPath(requestedPath);
  if (exact?.children) return exact.path;
  const wanted = normalizePath(requestedPath);
  return app.vault.getAllLoadedFiles().find((item) => item?.children && normalizePath(item.path) === wanted)?.path ?? null;
}

const deprecatedDashboardFiles = new Set(["content index", "content status"]);

function addFolder(parent, title, requestedPath) {
  const box = card(parent, title);
  const folderPath = resolveFolderPath(requestedPath);
  if (!folderPath) {
    box.createEl("p", { text: `Folder not found: ${requestedPath}`, cls: "dashboard-muted" });
    return;
  }
  const files = app.vault.getFiles()
    .filter((file) => file.parent?.path === folderPath)
    .filter((file) => !deprecatedDashboardFiles.has(file.basename.toLowerCase()))
    .sort((a, b) => a.basename.localeCompare(b.basename, undefined, { numeric: true, sensitivity: "base" }));
  if (!files.length) {
    box.createEl("p", { text: "No files found.", cls: "dashboard-muted" });
    return;
  }
  for (const file of files) addLink(box, file.basename, file.path);
}

const resources = section("Vault resources");
const resourceGrid = resources.createEl("div", { cls: "dashboard-grid" });
addFolder(resourceGrid, "Queries", "_control/queries");
addFolder(resourceGrid, "Views", "views");
```
