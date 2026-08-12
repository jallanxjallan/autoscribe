# System Status

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));
const { notify } = loadControl("scripts/lib/notify.js");
const { readSystemState } = loadControl("scripts/lib/system-state.js");

function renderSystemStatus({ app, container }) {
  container.empty();
  container.createEl("h2", { text: "System Status" });
  container.createEl("p", { text: "Detailed Git, transport-run, feeder and handoff diagnostics for this project vault." });
  const refresh = container.createEl("button", { text: "Refresh" });
  const output = container.createEl("div");

  function draw(notifyUser = false) {
    if (notifyUser) notify("Refreshing System Status…");
    output.empty();
    const state = readSystemState(app);
    const summary = output.createEl("div");
    if (state.git) summary.createEl("p", { text: `Git: ${state.git.branch}; ${state.git.staged + state.git.modified + state.git.untracked} changed file(s)` });
    else summary.createEl("p", { text: `Git unavailable: ${state.errors.git}` });
    if (state.pipeline) {
      const c = state.pipeline.counts;
      summary.createEl("p", { text: `Runs: ${c.total}; unclaimed ${c.unclaimed || 0}; processing ${c.waiting || 0}; responses ready ${c.response_pending || 0}; reviewed ${c.reviewed || 0}` });
      if (state.pipeline.feeder_error) summary.createEl("p", { text: `Feeder unavailable: ${state.pipeline.feeder_error}` });
    } else summary.createEl("p", { text: `Pipeline unavailable: ${state.errors.pipeline}` });

    const handoffs = state.pipeline?.handoffs || [];
    if (!handoffs.length) output.createEl("p", { text: "No feeder handoffs have been recorded." });
    for (const handoff of handoffs) {
      const card = output.createEl("div");
      card.style.cssText = "border:1px solid var(--background-modifier-border);padding:.75rem;margin:.75rem 0;border-radius:8px";
      card.createEl("h3", { text: handoff.stem });
      for (const [label, text] of [["request.json", JSON.stringify(handoff.request, null, 2)], ["stdout.log", handoff.stdout], ["stderr.log", handoff.stderr]]) {
        if (!text) continue;
        card.createEl("h4", { text: label });
        const pre = card.createEl("pre", { text: text || "(empty)" });
        pre.style.whiteSpace = "pre-wrap";
      }
    }
    if (notifyUser) notify(`System Status refreshed: ${handoffs.length} recent handoff(s) shown.`);
  }

  refresh.addEventListener("click", () => draw(true));
  draw(false);
}

await renderSystemStatus({ app, dv, container: dv.container });
````
