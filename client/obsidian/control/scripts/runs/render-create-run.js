"use strict";

const { el, clear, button } = require("../lib/dom.js");
const { callFeeder } = require("../lib/feeder-ipc.js");

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

function renderFiles(container, files) {
  container.innerHTML = "";
  container.appendChild(el("h3", { text: `Files (${files.length})` }));
  if (!files.length) {
    container.appendChild(el("p", { text: "This commit contains no files." }));
    return;
  }
  const list = el("ul");
  for (const file of files) list.appendChild(el("li", {}, [el("code", { text: file })]));
  container.appendChild(list);
}

async function renderCreateRun({ app, container }) {
  clear(container);
  container.appendChild(el("h2", { text: "Dispatch Run" }));
  container.appendChild(el("p", { text: "Select a user commit and an uploaded plan. Feeder sends the commit filepaths to Pandoc and enqueues them with the selected plan slug." }));

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
  const commitSelect = el("select");
  commitSelect.style.width = "100%";
  const planSelect = el("select");
  planSelect.style.width = "100%";

  if (!commits.length) {
    commitSelect.appendChild(el("option", { text: "No user-defined commits found." }));
    commitSelect.disabled = true;
  } else {
    for (const commit of commits) {
      commitSelect.appendChild(el("option", { value: commit.hash, text: commitLabel(commit) }));
    }
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

  const filesBox = el("div");
  const resultBox = el("pre");
  resultBox.style.whiteSpace = "pre-wrap";

  function selectedCommit() {
    return commits.find((commit) => commit.hash === commitSelect.value) || null;
  }

  function refreshFiles() {
    const commit = selectedCommit();
    renderFiles(filesBox, commit?.files || []);
    resultBox.textContent = "";
  }
  commitSelect.addEventListener("change", refreshFiles);

  const dispatchButton = button("Dispatch Run", () => {
    const commit = selectedCommit();
    const planSlug = planSelect.value;
    if (!commit) {
      new Notice("Select a commit.");
      return;
    }
    if (!planSlug) {
      new Notice("Select an uploaded plan.");
      return;
    }
    dispatchButton.disabled = true;
    resultBox.textContent = "Dispatching…";
    try {
      const result = callFeeder(app, "dispatch.run", {
        commit: commit.hash,
        paths: commit.files,
        plan_slug: planSlug,
      });
      resultBox.textContent = [
        `Dispatched ${result.count} file(s)`,
        `Plan: ${result.plan_slug}`,
        result.pipeline_output || "",
      ].filter(Boolean).join("\n");
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
  controls.append(
    el("label", {}, ["User commit", commitSelect]),
    el("label", {}, ["Uploaded plan", planSelect]),
    dispatchButton,
    resultBox,
  );
  container.append(controls, filesBox);
  refreshFiles();
}

module.exports = { renderCreateRun };
