"use strict";

const { el, clear, button } = require("../lib/dom.js");
const { callFeeder } = require("../lib/feeder-ipc.js");
const { getCurrentSelection } = require("../lib/current-selection.js");

function formatDate(timestamp) {
  if (!timestamp) return "";
  return new Date(Number(timestamp) * 1000).toLocaleString();
}

function commitLabel(commit) {
  return `${commit.short_hash || String(commit.hash).slice(0, 8)} — ${commit.subject} — ${formatDate(commit.timestamp)} (${commit.count} file${commit.count === 1 ? "" : "s"})`;
}

function planLabel(plan) {
  const slug = plan.slug || plan.record_identity || "";
  return `${plan.label || slug} — ${slug}`;
}

function selectionPaths(manifest) {
  if (!manifest || !Array.isArray(manifest.items)) return [];
  return [...new Set(manifest.items.map(item => item?.path).filter(path => typeof path === "string" && path.length > 0))];
}

function currentSelectionLabel(manifest, paths) {
  if (!manifest) return "Current selection unavailable";
  const source = manifest.options?.selection_source || manifest.namespace || manifest.queryName || "query";
  return `Current selection — ${source} (${paths.length} file${paths.length === 1 ? "" : "s"})`;
}

function renderFiles(container, files, emptyText = "This source contains no files.") {
  container.innerHTML = "";
  container.appendChild(el("h3", { text: `Files (${files.length})` }));
  if (!files.length) {
    container.appendChild(el("p", { text: emptyText }));
    return;
  }
  const list = el("ul");
  for (const file of files) list.appendChild(el("li", {}, [el("code", { text: file })]));
  container.appendChild(list);
}

async function renderCreateRun({ app, container }) {
  clear(container);
  container.appendChild(el("h2", { text: "Dispatch Run" }));
  container.appendChild(el("p", { text: "Select either the current query selection or a user commit, then choose an uploaded plan." }));

  const status = el("p", { text: "Loading commits and plans…" });
  container.appendChild(status);

  let commits;
  let plans;
  try {
    [commits, plans] = await Promise.all([
      Promise.resolve(callFeeder(app, "git.user_commits", { limit: 100 })),
      Promise.resolve(callFeeder(app, "plans.list")),
    ]);
  } catch (error) {
    status.textContent = `Could not load dispatch choices: ${error.message}`;
    throw error;
  }

  status.remove();
  const manifest = getCurrentSelection(app);
  const currentPaths = selectionPaths(manifest);
  const sourceSelect = el("select");
  sourceSelect.style.width = "100%";
  if (manifest) {
    sourceSelect.appendChild(el("option", { value: "current", text: currentSelectionLabel(manifest, currentPaths) }));
  } else {
    sourceSelect.appendChild(el("option", {
      value: "current-unavailable",
      text: "Current selection unavailable",
      disabled: "disabled",
    }));
  }
  sourceSelect.appendChild(el("option", { value: "commit", text: "Files from user commit" }));
  sourceSelect.value = manifest ? "current" : "commit";

  const commitSelect = el("select");
  commitSelect.style.width = "100%";
  const planSelect = el("select");
  planSelect.style.width = "100%";

  if (!commits.length) {
    commitSelect.appendChild(el("option", { text: "No user-defined commits found." }));
    commitSelect.disabled = true;
  } else {
    for (const commit of commits) commitSelect.appendChild(el("option", { value: commit.hash, text: commitLabel(commit) }));
  }

  if (!plans.length) {
    planSelect.appendChild(el("option", { text: "No uploaded plans found." }));
    planSelect.disabled = true;
  } else {
    for (const plan of plans) {
      const slug = plan.slug || plan.record_identity;
      planSelect.appendChild(el("option", { value: slug, text: planLabel(plan) }));
    }
  }

  const commitWrap = el("label", {}, ["Select user commit", commitSelect]);
  const filesBox = el("div");
  const resultBox = el("pre");
  resultBox.style.whiteSpace = "pre-wrap";

  function selectedCommit() {
    return commits.find(commit => commit.hash === commitSelect.value) || null;
  }
  function selectedSource() {
    if (sourceSelect.value === "current") return { kind: "current", paths: currentPaths, commit: null };
    const commit = selectedCommit();
    return { kind: "commit", paths: commit?.files || [], commit };
  }
  function refreshFiles() {
    const source = selectedSource();
    commitWrap.style.display = source.kind === "commit" ? "grid" : "none";
    renderFiles(filesBox, source.paths, source.kind === "current" ? "The current selection is empty." : "This commit contains no files.");
    resultBox.textContent = "";
  }
  sourceSelect.addEventListener("change", refreshFiles);
  commitSelect.addEventListener("change", refreshFiles);

  const dispatchButton = button("Dispatch Run", () => {
    const source = selectedSource();
    const planSlug = planSelect.value;
    if (source.kind === "commit" && !source.commit) return new Notice("Select a commit.");
    if (!source.paths.length) return new Notice("The selected source contains no files.");
    if (!planSlug) return new Notice("Select an uploaded plan.");

    dispatchButton.disabled = true;
    resultBox.textContent = "Dispatching…";
    try {
      const payload = { paths: source.paths, plan_slug: planSlug };
      if (source.commit) payload.commit = source.commit.hash;
      const result = callFeeder(app, "dispatch.run", payload);
      resultBox.textContent = [`Dispatched ${result.count} file(s)`, `Plan: ${result.plan_slug}`, result.pipeline_output || ""].filter(Boolean).join("\n");
      new Notice(`Dispatched ${result.count} file(s) with ${result.plan_slug}.`);
    } catch (error) {
      resultBox.textContent = `Dispatch failed: ${error.message}`;
      new Notice(`Dispatch failed: ${error.message}`);
      console.error(error);
    } finally {
      dispatchButton.disabled = false;
    }
  });

  const controls = el("div");
  controls.style.display = "grid";
  controls.style.gap = "0.75rem";
  controls.append(el("label", {}, ["File source", sourceSelect]), commitWrap, el("label", {}, ["Uploaded plan", planSelect]), dispatchButton, resultBox);
  container.append(controls, filesBox);
  refreshFiles();
}

module.exports = { renderCreateRun };
