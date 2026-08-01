"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const runtimeApp = globalThis.app;
const controlVaultRoot = runtimeApp.vault.adapter.getBasePath?.() || runtimeApp.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const { el, clear, button } = loadControl("scripts/lib/dom.js");
const {
  responseHistoryForPath,
  getArchivedResponseReview,
  reconsiderResponse,
} = loadControl("scripts/lib/git-transport.js");
const { renderDiff } = loadControl("scripts/lib/diff-view.js");

function renderFileState({ app, container }) {
  clear(container);

  const active = app.workspace.getActiveFile();
  if (!active || active.extension !== "md") {
    container.appendChild(el("p", {
      text: "Open a Markdown file, then invoke File State again.",
    }));
    return;
  }

  container.appendChild(el("h2", { text: active.basename }));
  container.appendChild(el("p", { text: active.path }));

  let history;
  try {
    history = responseHistoryForPath(app, active.path);
  } catch (error) {
    container.appendChild(el("pre", { text: error.message || String(error) }));
    return;
  }

  if (!history.length) {
    container.appendChild(el("p", {
      text: "No retained pipeline response was found for this file.",
    }));
    return;
  }

  const latest = history[0];
  let review;
  try {
    review = getArchivedResponseReview(app, latest.branch, latest.record.identity);
  } catch (error) {
    container.appendChild(el("pre", { text: error.message || String(error) }));
    return;
  }

  const outcome = latest.decision?.outcome || "pending";
  container.appendChild(el("p", {
    text: `Run ${latest.run_identity} · ${latest.plan_identity || "unknown plan"} · current decision: ${outcome}`,
  }));

  renderDiff(container, review);

  const controls = el("div");
  controls.style.display = "flex";
  controls.style.gap = "0.75rem";
  controls.style.marginTop = "0.75rem";

  const reconsider = (nextOutcome) => {
    try {
      const verb = nextOutcome === "accepted" ? "accept" : "roll back";
      if (!window.confirm(`Are you sure you want to ${verb} the retained response for ${active.path}?`)) {
        return;
      }
      reconsiderResponse(app, latest.branch, latest.record.identity, nextOutcome);
      new Notice(
        nextOutcome === "accepted"
          ? "Response accepted and marked for review."
          : "Accepted response rolled back.",
      );
      renderFileState({ app, container });
    } catch (error) {
      console.error(error);
      new Notice(`Could not reconsider response: ${error.message}`, 10000);
    }
  };

  if (outcome === "declined") {
    controls.appendChild(button("Accept response after all", () => reconsider("accepted")));
  } else if (outcome === "accepted") {
    controls.appendChild(button("Roll back accepted response", () => reconsider("declined")));
  } else {
    controls.appendChild(button("Accept response", () => reconsider("accepted")));
    controls.appendChild(button("Decline response", () => reconsider("declined")));
  }

  container.appendChild(controls);
}

module.exports = { renderFileState };
