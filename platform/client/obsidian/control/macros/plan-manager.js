"use strict";

function createControlRuntime(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app?.vault?.adapter?.getBasePath?.() || app?.vault?.adapter?.basePath;
  if (!base) throw new Error("Could not determine vault base path.");
  const loaderPath = path.join(base, "_control", "scripts", "lib", "control-loader.js");
  try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
  const { createControlLoader } = nodeRequire(loaderPath);
  return createControlLoader({ app, controlRoot: "_control" });
}

let loadConfig;
let el;
let notify;
let buildPlanRecord;
let copyText;

function workflowConfig() { return loadConfig("workflow"); }
function stepKinds() { return workflowConfig().step_kinds || ["llm", "script", "rag"]; }
function managerConfig() { return workflowConfig().plan_manager || {}; }
function statusKey() { return String(managerConfig().status_storage_key || "autoscribe.plan-manager.status"); }
function id(record) { return String(record?.slug || record?.record_identity || record?.key || "").trim(); }
function title(record) { return String(record?.title || record?.label || record?.name || record?.payload?.label || id(record)); }
function planSlug(record) { return String(record?.record_identity || record?.slug || record?.key || "").trim(); }
function planScore(record) { return Number(record?.usage_score || 0) || 0; }
function planUseCount(record) { return Number(record?.use_count || 0) || 0; }
function selected(records, value) { return records.find((record) => id(record) === String(value || "")) || null; }

function sortRecords(records) {
  return [...records].sort((a, b) =>
    title(a).localeCompare(title(b), undefined, { sensitivity: "base", numeric: true }) ||
    id(a).localeCompare(id(b), undefined, { sensitivity: "base", numeric: true })
  );
}
function sortPlans(records) {
  return [...records].sort((a, b) =>
    planScore(b) - planScore(a) ||
    title(a).localeCompare(title(b), undefined, { sensitivity: "base", numeric: true }) ||
    planSlug(a).localeCompare(planSlug(b), undefined, { sensitivity: "base", numeric: true })
  );
}
function componentOf(record) {
  const explicit = String(record?.component || record?.class || "").trim().toLowerCase();
  if (explicit) return explicit;
  const prefix = id(record).toLowerCase().split(".", 1)[0];
  return ({ std: "standing", rul: "rule", rol: "role", ctx: "context", tsk: "task", ins: "task" })[prefix] || "";
}
function byComponent(records, component) {
  const wanted = String(component || "").trim().toLowerCase();
  return sortRecords(records.filter((record) => {
    const current = componentOf(record);
    if (current === wanted) return true;
    return wanted === "task" && ["instruction", "specific"].includes(current);
  }));
}
function option(select, record, { titleOnly = false } = {}) {
  const recordId = id(record);
  const display = title(record);
  select.appendChild(el("option", {
    value: recordId,
    text: titleOnly || !recordId || display === recordId ? display : `${display} — ${recordId}`,
  }));
}
function catalogsFrom(output) {
  const source = output?.catalogs || {};
  return {
    instructions: Array.isArray(source.instructions) ? source.instructions : [],
    plans: Array.isArray(source.plans) ? source.plans : [],
    engines: Array.isArray(source.engines) ? source.engines : [],
    models: Array.isArray(source.models) ? source.models : [],
    scripts: Array.isArray(source.scripts) ? source.scripts : [],
    ragProfiles: Array.isArray(source.rag_profiles) ? source.rag_profiles : [],
  };
}
function screenSteps(plan, catalogs) {
  return Object.entries(plan?.payload?.steps || plan?.steps || {})
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([, step]) => {
      const refs = step.instruction_slugs || {};
      return {
        kind: step.kind || "llm",
        label: step.label || "Step",
        engine: selected(catalogs.engines, step.engine),
        model: selected(catalogs.models, step.model),
        script: selected(catalogs.scripts, step.script),
        rag_profile: selected(catalogs.ragProfiles, step.rag_profile),
        role: selected(catalogs.instructions, refs.role?.[0]),
        context: selected(catalogs.instructions, refs.context?.[0]),
        task: selected(catalogs.instructions, refs.task?.[0] || step.instruction),
        argsJson: JSON.stringify(step.args || {}, null, 2),
      };
    });
}

function statePaths(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const path = nodeRequire("node:path");
  const base = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const stateDir = String(managerConfig().state_dir || ".autoscribe");
  return {
    state: path.join(base, stateDir, String(managerConfig().state_file || "control-state.json")),
    plans: path.join(base, stateDir, String(managerConfig().plan_dir || "plans")),
  };
}
function readState(app) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const fs = nodeRequire("node:fs");
  const paths = statePaths(app);
  if (!fs.existsSync(paths.state)) {
    throw new Error(`Plan catalogue is not initialized. Run 'svc refresh' from the vault root first.`);
  }
  const state = JSON.parse(fs.readFileSync(paths.state, "utf8"));
  if (Number(state.version || 0) !== 1) throw new Error("Unsupported AutoScribe control-state version.");
  return state;
}
function writePlanDraft(app, record) {
  const nodeRequire = typeof require === "function" ? require : window.require;
  const fs = nodeRequire("node:fs");
  const path = nodeRequire("node:path");
  const paths = statePaths(app);
  fs.mkdirSync(paths.plans, { recursive: true });
  const slug = planSlug(record);
  if (!/^[a-z0-9][a-z0-9._-]*$/i.test(slug)) throw new Error(`Unsafe plan slug: ${slug}`);
  const target = path.join(paths.plans, `${slug}.json`);
  const temp = `${target}.tmp-${process.pid}-${Date.now()}`;
  fs.writeFileSync(temp, JSON.stringify(record, null, 2) + "\n", "utf8");
  fs.renameSync(temp, target);
  return target;
}
function gitMarker(record) {
  const slug = planSlug(record);
  const hint = String(record?.payload?.label || record?.label || record?.title || slug).replace(/[\r\n]+/g, " ").trim();
  return `Autoscribe-Plan: ${slug}\nAutoscribe-Plan-Title: ${hint}`;
}

async function renderPlanManager({ app, container }) {
  container.empty();
  const state = readState(app);
  const catalogs = catalogsFrom(state);
  const plans = catalogs.plans;
  let loaded = null;
  let steps = [];

  container.appendChild(el("h2", { text: "Plan Manager" }));
  container.appendChild(el("p", {
    text: state.refreshed_at ? `Catalogue refreshed: ${state.refreshed_at}. Run svc refresh after saving a plan.` : "Run svc refresh after saving a plan.",
  }));

  const ranked = el("div");
  ranked.style.cssText = "border:1px solid var(--background-modifier-border);padding:.75rem;border-radius:8px;margin:.75rem 0 1rem";
  ranked.appendChild(el("h3", { text: "Plans — ranked by use" }));
  if (!plans.length) ranked.appendChild(el("p", { text: "No plans are available yet." }));
  for (const plan of sortPlans(plans)) {
    const row = el("div");
    row.style.cssText = "display:grid;grid-template-columns:minmax(14rem,1fr) auto auto;gap:.5rem;align-items:center;margin:.35rem 0";
    const label = el("div");
    label.appendChild(el("strong", { text: String(plan?.payload?.label || title(plan)) }));
    label.appendChild(el("div", { text: `${planSlug(plan)} · score ${planScore(plan).toFixed(2)} · ${planUseCount(plan)} use${planUseCount(plan) === 1 ? "" : "s"}` }));
    const edit = el("button", { text: "Edit" });
    edit.addEventListener("click", () => { planSelect.value = planSlug(plan); loadSelectedPlan(); });
    const copy = el("button", { text: "Copy Git Marker" });
    copy.addEventListener("click", async () => {
      await copyText(gitMarker(plan), { notify, successMessage: `Copied ${planSlug(plan)} for Obsidian Git.` });
    });
    row.append(label, edit, copy);
    ranked.appendChild(row);
  }
  container.appendChild(ranked);

  const planSelect = el("select"); planSelect.style.width = "100%";
  const loadButton = el("button", { text: "Load Plan" });
  const newButton = el("button", { text: "New Plan" });
  const name = el("input", { type: "text", placeholder: "Plan label" }); name.style.width = "100%";
  const type = el("input", { type: "text", placeholder: "e.g. revise, research, proofread" }); type.style.width = "100%";
  const description = el("textarea", { placeholder: "Optional description" }); description.style.width = "100%";
  const stepsBox = el("div");
  const status = el("pre"); status.style.cssText = "white-space:pre-wrap;margin-top:.75rem";

  function setStatus(message) {
    status.textContent = message || "";
    try { if (message) sessionStorage.setItem(statusKey(), message); else sessionStorage.removeItem(statusKey()); } catch {}
  }
  function refreshSelect(slug = "") {
    planSelect.innerHTML = "";
    planSelect.appendChild(el("option", { value: "", text: plans.length ? "Select a plan…" : "No saved plans" }));
    for (const plan of sortPlans(plans)) {
      const slugValue = planSlug(plan);
      if (!slugValue) continue;
      planSelect.appendChild(el("option", { value: slugValue, text: `${plan?.payload?.label || title(plan)} — ${slugValue}` }));
    }
    planSelect.value = slug;
  }
  function choice(records, value, onChange, placeholder, options = {}) {
    const select = el("select"); select.style.width = "100%";
    select.appendChild(el("option", { value: "", text: placeholder }));
    sortRecords(records).forEach((record) => option(select, record, options));
    select.value = id(value);
    select.addEventListener("change", () => onChange(selected(records, select.value)));
    return select;
  }
  function componentPicker(card, step, component, field, heading) {
    const records = byComponent(catalogs.instructions, component);
    card.appendChild(el("strong", { text: `${heading} (${records.length})` }));
    card.appendChild(choice(records, step[field], (value) => { step[field] = value; redraw(); }, `Choose ${heading.toLowerCase()}`, { titleOnly: true }));
  }
  function redraw() {
    stepsBox.innerHTML = "";
    steps.forEach((step, index) => {
      const card = el("div"); card.style.cssText = "border:1px solid var(--background-modifier-border);padding:.75rem;margin:.75rem 0;border-radius:8px";
      const stepLabel = el("input", { type: "text", value: step.label || `Step ${index + 1}` }); stepLabel.style.width = "100%";
      stepLabel.addEventListener("input", () => { step.label = stepLabel.value; });
      const kind = el("select"); stepKinds().forEach((value) => kind.appendChild(el("option", { value, text: value })));
      kind.value = step.kind; kind.addEventListener("change", () => { step.kind = kind.value; redraw(); });
      card.append(el("h3", { text: `Step ${index + 1}` }), stepLabel, kind);
      if (step.kind === "llm") {
        card.append(choice(catalogs.engines, step.engine, (v) => { step.engine = v; }, "Engine"));
        card.append(choice(catalogs.models, step.model, (v) => { step.model = v; }, "Model"));
        componentPicker(card, step, "role", "role", "Role");
        componentPicker(card, step, "context", "context", "Context");
        componentPicker(card, step, "task", "task", "Task");
      } else if (step.kind === "script") {
        card.append(choice(catalogs.scripts, step.script, (v) => { step.script = v; }, "Script"));
      } else {
        card.append(choice(catalogs.ragProfiles, step.rag_profile, (v) => { step.rag_profile = v; }, "RAG profile"));
      }
      const args = el("textarea"); args.style.width = "100%"; args.value = step.argsJson || "{}";
      args.addEventListener("input", () => { step.argsJson = args.value; }); card.append(args);
      const remove = el("button", { text: "Delete Step" }); remove.addEventListener("click", () => { steps.splice(index, 1); redraw(); }); card.append(remove);
      stepsBox.appendChild(card);
    });
  }
  function clearForm() { loaded = null; name.value = ""; type.value = ""; description.value = ""; steps = []; redraw(); }
  function loadSelectedPlan() {
    if (!planSelect.value) return setStatus("Select a plan first.");
    loaded = plans.find((plan) => planSlug(plan) === planSelect.value) || null;
    if (!loaded) return setStatus("The selected plan is not in the current catalogue snapshot.");
    name.value = loaded.payload?.label || loaded.label || "";
    type.value = loaded.payload?.type || loaded.type || "";
    description.value = loaded.payload?.description || loaded.description || "";
    steps = screenSteps(loaded, catalogs); redraw(); setStatus(`Loaded ${planSlug(loaded)}.`);
  }

  loadButton.addEventListener("click", loadSelectedPlan);
  newButton.addEventListener("click", () => { planSelect.value = ""; clearForm(); setStatus("New plan form ready."); });
  const add = el("button", { text: "Add Step" });
  add.addEventListener("click", () => {
    steps.push({ kind: String(managerConfig().default_step_kind || "llm"), label: `Step ${steps.length + 1}`, argsJson: "{}" });
    redraw();
  });
  const save = el("button", { text: "Save Plan Locally", class: "mod-cta" });
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      for (const [index, step] of steps.entries()) {
        if (step.kind !== "llm") continue;
        if (!step.task) throw new Error(`Step ${index + 1}: choose a task instruction.`);
        step.instruction_slugs = {
          role: step.role ? [id(step.role)] : [],
          context: step.context ? [id(step.context)] : [],
          task: [id(step.task)],
        };
      }
      const record = buildPlanRecord({ label: name.value, type: type.value, description: description.value, steps, force_slug: planSlug(loaded) || null });
      writePlanDraft(app, record);
      const existing = plans.findIndex((plan) => planSlug(plan) === planSlug(record));
      const scored = { ...record, usage_score: existing >= 0 ? planScore(plans[existing]) : 0, use_count: existing >= 0 ? planUseCount(plans[existing]) : 0 };
      if (existing >= 0) plans.splice(existing, 1, scored); else plans.push(scored);
      loaded = scored;
      refreshSelect(planSlug(record));
      setStatus(`Saved ${planSlug(record)} locally. Run 'svc refresh' before relying on the updated plan.`);
      notify(`Saved plan ${planSlug(record)} locally.`);
    } catch (error) {
      const message = `Save failed: ${error.message || error}`; setStatus(message); notify(message, 10000);
    } finally { save.disabled = false; }
  });
  const copyCurrent = el("button", { text: "Copy Git Marker" });
  copyCurrent.addEventListener("click", async () => {
    const record = loaded || plans.find((plan) => planSlug(plan) === planSelect.value);
    if (!record) return setStatus("Load a plan first.");
    await copyText(gitMarker(record), { notify, successMessage: `Copied ${planSlug(record)} for Obsidian Git.` });
  });

  refreshSelect();
  const pickerButtons = el("div"); pickerButtons.style.cssText = "display:flex;gap:.5rem;margin:.4rem 0 1rem"; pickerButtons.append(loadButton, newButton, copyCurrent);
  const actionButtons = el("div"); actionButtons.style.cssText = "display:flex;gap:.5rem;margin-top:.75rem"; actionButtons.append(add, save);
  container.append(
    el("label", { text: "Existing plan" }), planSelect, pickerButtons,
    el("label", { text: "Plan label" }), name,
    el("label", { text: "Plan type" }), type,
    el("label", { text: "Description" }), description,
    stepsBox, actionButtons, status,
  );
  redraw();
  try { status.textContent = sessionStorage.getItem(statusKey()) || ""; } catch {}
}

module.exports = async function plan_manager(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const loader = createControlRuntime(app);
  ({ loadConfig } = loader.requireControl("scripts/lib/config-loader.js"));
  ({ el } = loader.requireControl("scripts/lib/dom.js"));
  ({ notify } = loader.requireControl("scripts/lib/notify.js"));
  ({ copyText } = loader.requireControl("scripts/lib/clipboard.js"));
  ({ buildPlanRecord } = loader.requireControl("scripts/plans/plan-record.js"));
  const { openWorkflowModal } = loader.requireControl("scripts/lib/workflow-modal.js");
  return openWorkflowModal({ app, title: "Plan Manager", render: (container) => renderPlanManager({ app, container }) });
};
