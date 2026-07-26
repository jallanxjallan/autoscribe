const path = require("path");

function parseSelection(text) {
  const rows = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const paths = [];
  const seen = new Set();

  for (const row of rows) {
    const cells = row.split("\t").map((cell) => cell.trim()).filter(Boolean);
    let candidate = cells.find((cell) => /\.md$/i.test(cell));

    if (!candidate) {
      const wiki = row.match(/\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/);
      if (wiki) candidate = wiki[1];
    }

    if (!candidate) continue;
    candidate = candidate.replace(/^file:\/\//, "").replace(/\\/g, "/");
    if (!/\.md$/i.test(candidate)) candidate += ".md";
    if (!seen.has(candidate)) {
      seen.add(candidate);
      paths.push(candidate);
    }
  }

  return paths;
}

async function renderDispatchRun({ app, container }) {
  container.empty();
  const vaultRoot = app.vault.adapter.basePath;
  const { handoffFeeder } = require(path.join(vaultRoot, "_control/scripts/lib/feeder-ipc.js"));
  const { listPlanRecords, loadPlanRecord } = require(path.join(vaultRoot, "_control/scripts/plans/plan-store.js"));

  const heading = container.createEl("h2", { text: "Dispatch selected files" });
  heading.style.marginTop = "0";

  const status = container.createEl("div", { text: "Loading selection…" });
  status.style.marginBottom = "0.75em";

  let selection = [];
  try {
    selection = parseSelection(await navigator.clipboard.readText());
  } catch (error) {
    status.setText(`Could not read clipboard: ${error.message || error}`);
    return;
  }

  if (!selection.length) {
    status.setText("The clipboard selection contains no Markdown file paths.");
    return;
  }

  status.setText(`${selection.length} selected file${selection.length === 1 ? "" : "s"}`);
  const list = container.createEl("ul");
  for (const selectedPath of selection) list.createEl("li", { text: selectedPath });

  const planRows = listPlanRecords(app);
  if (!Array.isArray(planRows) || !planRows.length) {
    container.createEl("p", { text: "No plans are available." });
    return;
  }

  const form = container.createEl("div");
  form.style.display = "grid";
  form.style.gap = "0.6em";
  form.style.maxWidth = "42em";

  form.createEl("label", { text: "Plan" });
  const select = form.createEl("select");
  for (const plan of planRows) {
    const slug = String(plan.record_identity || plan.slug || "").trim();
    if (!slug) continue;
    const label = String(plan.label || plan.name || slug);
    select.createEl("option", { text: label, value: slug });
  }

  form.createEl("label", { text: "Commit message (optional)" });
  const message = form.createEl("input", {
    attr: {
      type: "text",
      placeholder: "Defaults to DISPATCH <plan>: <timestamp>"
    }
  });

  const runButton = form.createEl("button", { text: "Dispatch Run", cls: "mod-cta" });
  const result = container.createEl("pre");
  result.style.whiteSpace = "pre-wrap";

  runButton.addEventListener("click", async () => {
    runButton.disabled = true;
    result.setText("Handing dispatch to feeder…");
    try {
      const plan = loadPlanRecord(app, select.value);
      const handoff = handoffFeeder(app, "dispatch.run", {
        paths: selection,
        plan_slug: select.value,
        plan_record: plan,
        message: message.value.trim()
      });
      result.setText(
        `Dispatch handed off to feeder.\n` +
        `Process: ${handoff.pid}\n` +
        `Open System Status if the expected response does not appear.`
      );
    } catch (error) {
      result.setText(`Dispatch failed: ${error.message || error}`);
    } finally {
      runButton.disabled = false;
    }
  });
}

module.exports = { renderDispatchRun, parseSelection };
