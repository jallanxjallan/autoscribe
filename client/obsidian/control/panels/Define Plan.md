# Define Plan

````dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loadControl = (relativePath) => nodeRequire(pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/")));

const { spawnSync } = require("node:child_process");
const path = require("node:path");
const { buildPlanRecord } = loadControl("scripts/plans/plan-record.js");
const { listPlanRecords, loadPlanRecord, savePlanRecord, deletePlanRecord } = loadControl("scripts/plans/plan-store.js");
const { callFeeder } = loadControl("scripts/lib/feeder-ipc.js");
const { vaultRoot } = loadControl("scripts/lib/vault-state.js");
const { snapshotList } = loadControl("scripts/lib/control-loader.js");
const { resolveInstructionStack } = loadControl("scripts/plans/instruction-resolver.js");

const ZSH = "/usr/bin/zsh";
const STEP_KINDS = ["llm", "script", "rag"];
const STATUS_KEY = "autoscribe.define-plan.status";

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function ascSnapshot(group, cwd) {
  const result = spawnSync(ZSH, ["-lic", `asc ${group} snapshot`], {
    cwd, encoding: "utf8", timeout: 30000, maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    throw new Error(String(result.stderr || result.error?.message || `asc ${group} snapshot failed`).trim());
  }
  return JSON.parse(String(result.stdout || "{}"));
}

function id(record) { return String(record?.key || record?.slug || record?.record_identity || ""); }
function label(record) { return String(record?.label || id(record)); }
function option(select, record) { select.appendChild(el("option", { value: id(record), text: `${label(record)} — ${id(record)}` })); }
function selected(records, value) { return records.find((record) => id(record) === value) || null; }
function planSlug(record) { return String(record?.record_identity || record?.slug || ""); }

function screenSteps(plan, catalogs) {
  return Object.entries(plan?.payload?.steps || {}).sort(([a], [b]) => Number(a) - Number(b)).map(([, step]) => ({
    kind: step.kind || "llm", label: step.label || "Step", engine: selected(catalogs.engines, step.engine),
    model: selected(catalogs.models, step.model), script: selected(catalogs.scripts, step.script),
    rag_profile: selected(catalogs.ragProfiles, step.rag_profile),
    instruction: selected(catalogs.instructions, step.instruction || step.instruction_slugs?.instructions?.[0]),
    argsJson: JSON.stringify(step.args || {}, null, 2),
  }));
}

async function renderCreatePlan({ app, container }) {
  container.empty();
  const root = vaultRoot(app);
  const registry = ascSnapshot("registry", root);
  const catalogs = {
    engines: snapshotList(registry, "engines"), models: snapshotList(registry, "models"),
    scripts: snapshotList(registry, "local_scripts"), ragProfiles: snapshotList(registry, "rag_profiles"),
    instructions: await callFeeder(app, "instructions.catalog", { include_pipeline: false }),
  };
  let plans = listPlanRecords(app), loaded = null, steps = [];

  container.appendChild(el("h2", { text: "Define Plan" }));
  container.appendChild(el("p", { text: "Create a new vault plan or load an existing plan for modification. Plans are stored under _plans/ and versioned in Git." }));

  const planLabel = el("label", { text: "Existing plan" });
  const planSelect = el("select"); planSelect.style.width = "100%";
  const loadButton = el("button", { text: "Load Plan" });
  const newButton = el("button", { text: "New Plan" });
  const nameLabel = el("label", { text: "Plan label" });
  const name = el("input", { type: "text", placeholder: "Plan label" }); name.style.width = "100%";
  const descriptionLabel = el("label", { text: "Description" });
  const description = el("textarea", { placeholder: "Optional description" }); description.style.width = "100%";
  const stepsBox = el("div");
  const status = el("pre"); status.style.cssText = "white-space:pre-wrap;margin-top:.75rem";

  function setStatus(message) {
    status.textContent = message || "";
    try {
      if (message) sessionStorage.setItem(STATUS_KEY, message);
      else sessionStorage.removeItem(STATUS_KEY);
    } catch {}
  }

  function clearForm() {
    loaded = null;
    name.value = "";
    description.value = "";
    steps = [];
    redraw();
  }

  function refreshSelect(slug = "") {
    planSelect.innerHTML = "";
    planSelect.appendChild(el("option", { value: "", text: plans.length ? "Select a plan…" : "No saved plans" }));
    plans.forEach((plan) => option(planSelect, { ...plan, key: planSlug(plan) }));
    planSelect.value = slug;
  }

  function choice(records, value, onChange, placeholder) {
    const select = el("select"); select.appendChild(el("option", { value: "", text: placeholder }));
    records.forEach((record) => option(select, record)); select.value = id(value);
    select.addEventListener("change", () => onChange(selected(records, select.value))); return select;
  }

  function redraw() {
    stepsBox.innerHTML = "";
    steps.forEach((step, index) => {
      const card = el("div"); card.style.cssText = "border:1px solid var(--background-modifier-border);padding:.75rem;margin:.75rem 0;border-radius:8px";
      const stepLabel = el("input", { type: "text", value: step.label || `Step ${index + 1}` });
      stepLabel.addEventListener("input", () => { step.label = stepLabel.value; });
      const kind = el("select"); STEP_KINDS.forEach((value) => kind.appendChild(el("option", { value, text: value })));
      kind.value = step.kind; kind.addEventListener("change", () => { step.kind = kind.value; redraw(); });
      card.append(el("h3", { text: `Step ${index + 1}` }), stepLabel, kind);
      if (step.kind === "llm") {
        card.append(choice(catalogs.engines, step.engine, (v) => { step.engine = v; }, "Engine"));
        card.append(choice(catalogs.models, step.model, (v) => { step.model = v; }, "Model"));
      } else if (step.kind === "script") card.append(choice(catalogs.scripts, step.script, (v) => { step.script = v; }, "Script"));
      else card.append(choice(catalogs.ragProfiles, step.rag_profile, (v) => { step.rag_profile = v; }, "RAG profile"));
      if (step.kind !== "script") card.append(choice(catalogs.instructions, step.instruction, (v) => { step.instruction = v; }, "Instruction"));
      const args = el("textarea"); args.value = step.argsJson || "{}"; args.addEventListener("input", () => { step.argsJson = args.value; }); card.append(args);
      const remove = el("button", { text: "Delete Step" }); remove.addEventListener("click", () => { steps.splice(index, 1); redraw(); }); card.append(remove);
      stepsBox.appendChild(card);
    });
  }

  function loadSelectedPlan() {
    if (!planSelect.value) {
      setStatus(plans.length ? "Select a saved plan, then click Load Plan." : "No saved plans were found under _plans/." );
      return;
    }
    try {
      loaded = loadPlanRecord(app, planSelect.value);
      name.value = loaded.payload?.label || loaded.label || "";
      description.value = loaded.payload?.description || loaded.description || "";
      steps = screenSteps(loaded, catalogs);
      redraw();
      setStatus(`Loaded ${planSlug(loaded)} from ${loaded.path}`);
    } catch (error) {
      setStatus(`Load failed: ${error.message || error}`);
    }
  }

  loadButton.addEventListener("click", loadSelectedPlan);
  planSelect.addEventListener("dblclick", loadSelectedPlan);
  newButton.addEventListener("click", () => {
    planSelect.value = "";
    clearForm();
    setStatus("New plan form ready.");
    name.focus();
  });

  const add = el("button", { text: "Add Step" }); add.addEventListener("click", () => { steps.push({ kind: "llm", label: `Step ${steps.length + 1}`, argsJson: "{}" }); redraw(); });
  const save = el("button", { text: "Save Plan", class: "mod-cta" }); save.addEventListener("click", () => {
    try {
      for (const step of steps) {
        if (!step.instruction) {
          delete step.instruction_slugs;
          continue;
        }
        const resolved = resolveInstructionStack(app, step.instruction);
        step.instruction_slugs = resolved.instruction_slugs;
      }
      const record = buildPlanRecord({ label: name.value, description: description.value, steps, force_slug: planSlug(loaded) || null });
      record.created = loaded?.created || new Date().toISOString(); record.modified = new Date().toISOString();
      const savedPath = savePlanRecord(app, record); loaded = { ...record, path: savedPath }; plans = listPlanRecords(app); refreshSelect(planSlug(record));
      setStatus(`Saved ${planSlug(record)} to ${savedPath}`);
    } catch (error) { setStatus(`Save failed: ${error.message || error}`); }
  });
  const del = el("button", { text: "Delete Plan" }); del.addEventListener("click", () => {
    if (!loaded) { setStatus("Load a plan before deleting it."); return; }
    try {
      const deletedPath = deletePlanRecord(app, planSlug(loaded));
      plans = listPlanRecords(app); refreshSelect(); clearForm();
      setStatus(`Deleted ${deletedPath}`);
    } catch (error) { setStatus(`Delete failed: ${error.message || error}`); }
  });

  const pickerButtons = el("div"); pickerButtons.style.cssText = "display:flex;gap:.5rem;margin:.4rem 0 1rem"; pickerButtons.append(loadButton, newButton);
  const actionButtons = el("div"); actionButtons.style.cssText = "display:flex;gap:.5rem;margin-top:.75rem"; actionButtons.append(add, save, del);

  refreshSelect();
  container.append(planLabel, planSelect, pickerButtons, nameLabel, name, descriptionLabel, description, stepsBox, actionButtons, status);
  redraw();
  try { status.textContent = sessionStorage.getItem(STATUS_KEY) || ""; } catch {}
}

await renderCreatePlan({ app, dv, container: dv.container });
````
