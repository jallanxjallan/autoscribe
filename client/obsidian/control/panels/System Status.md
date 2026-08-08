# System Status

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));
const { notify } = loadControl("scripts/lib/notify.js");

const fs = require("node:fs");
const path = require("node:path");

function renderSystemStatus({ app, container }) {
  container.empty();
  container.createEl("h2", { text: "System Status" });
  container.createEl("p", { text: "Diagnostic view for feeder handoffs. This panel is intentionally minimal; later revisions can merge server, ledger, export, and Git-derived state." });

  const root = app.vault.adapter.basePath;
  const statusDir = path.join(root, ".autoscribe", "system-status");
  const refresh = container.createEl("button", { text: "Refresh" });
  const output = container.createEl("div");

  function draw(notifyUser = false) {
    if (notifyUser) notify("Refreshing System Status…");
    output.empty();
    let names = [];
    try { names = fs.readdirSync(statusDir).sort().reverse(); }
    catch { output.createEl("p", { text: "No feeder handoffs have been recorded." }); if (notifyUser) notify("System Status refreshed: no feeder handoffs."); return; }
    const requests = names.filter((name) => name.endsWith(".request.json"));
    if (!requests.length) { output.createEl("p", { text: "No feeder handoffs have been recorded." }); if (notifyUser) notify("System Status refreshed: no feeder handoffs."); return; }
    for (const requestName of requests.slice(0, 50)) {
      const stem = requestName.replace(/\.request\.json$/, "");
      const card = output.createEl("div");
      card.style.cssText = "border:1px solid var(--background-modifier-border);padding:.75rem;margin:.75rem 0;border-radius:8px";
      card.createEl("h3", { text: stem });
      for (const suffix of ["request.json", "stdout.log", "stderr.log"]) {
        const file = path.join(statusDir, `${stem}.${suffix}`);
        if (!fs.existsSync(file)) continue;
        const text = fs.readFileSync(file, "utf8").trim();
        card.createEl("h4", { text: suffix });
        const pre = card.createEl("pre", { text: text || "(empty)" });
        pre.style.whiteSpace = "pre-wrap";
      }
    }
    if (notifyUser) notify(`System Status refreshed: ${Math.min(requests.length, 50)} handoff(s) shown.`);
  }

  refresh.addEventListener("click", () => draw(true));
  draw(false);
}

await renderSystemStatus({ app, dv, container: dv.container });
````
