"use strict";

const path = require("node:path");
const { loadConfig } = require("../scripts/lib/config-loader");

function workflowConfig() { return loadConfig("workflow"); }
function stepKinds() { return workflowConfig().step_kinds || ["llm", "script", "rag"]; }
function statusKey() { return String(workflowConfig().plan_manager?.status_storage_key || "autoscribe.plan-manager.status"); }

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

function id(record) { return String(record?.slug || record?.record_identity || record?.key || "").trim(); }
function title(record) { return String(record?.title || record?.label || record?.name || id(record)); }
function description(record) { return String(record?.description || "").trim(); }
function selected(records, value) { return records.find((record) => id(record) === String(value || "")) || null; }
function missingRecord(value) {
  const slug = String(value || "").trim();
  return slug ? { slug, title: slug, missing: true } : null;
}
function selectedOrMissing(records, value) { return selected(records, value) || missingRecord(value); }
function isMissing(record) { return Boolean(record?.missing); }
function planSlug(record) { return String(record?.record_identity || record?.slug || record?.key || "").trim(); }
function byScope(records, scope) { return records.filter((record) => String(record?.scope || "").toLowerCase() === scope); }
function modelsForEngine(records, engine) {
  const engineId = id(engine);
  if (!engineId) return records;
  return records.filter((record) => {
    const owner = String(record?.engine || record?.engine_key || record?.provider || record?.provider_key || "").trim();
    return !owner || owner === engineId;
  });
}

function option(select, record, { titleOnly = false } = {}) {
  const recordId = id(record);
  const display = title(record);
  select.appendChild(el("option", {
    value: recordId,
    text: titleOnly
      ? (description(record) ? `${display} — ${description(record)}` : display)
      : (!recordId || display === recordId ? display : `${display} — ${recordId}`),
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
  return Object.entries(plan?.payload?.steps || {})
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
        standingSlugs: Array.isArray(refs.standing) ? [...refs.standing] : [],
        role: selectedOrMissing(catalogs.instructions, refs.role?.[0]),
        context: selectedOrMissing(catalogs.instructions, refs.context?.[0]),
        task: selectedOrMissing(catalogs.instructions, refs.task?.[0] || step.instruction),
        argsJson: JSON.stringify(step.args || {}, null, 2),
      };
    });
}

async function renderCreatePlan({ app, container }) {
  container.empty();
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const load = (relative) => require(path.join(root, "_control", ...relative.split("/")));
  const { notify } = load("scripts/lib/notify.js");
  const { buildPlanRecord } = load("scripts/plans/plan-record.js");
  const { readPlanManagerSnapshot, savePlan, deletePlan } = load("scripts/lib/config-git.js");
  const snapshot = await readPlanManagerSnapshot(root);

  const catalogs = catalogsFrom(snapshot);
  const plans = catalogs.plans;
  let loaded = null;
  let steps = [];

  container.appendChild(el("h2", { text: "Define Plan" }));
  const toolbar = el("div");
  toolbar.style.cssText = "display:flex;gap:.5rem;align-items:center;margin-bottom:.75rem";
  const refresh = el("button", { text: "Reload Git" });
  const stateText = snapshot.catalog?.available
    ? `Catalogue: ${snapshot.catalog.server_instructions} server + ${snapshot.catalog.local_instructions} local instruction(s) · local overrides win`
    : `Catalogue: local instructions only${snapshot.catalog?.warning ? ` · server fetch failed` : ""}`;
  const freshness = el("span", { text: stateText });
  toolbar.append(refresh, freshness);
  container.appendChild(toolbar);

  const planSelect = el("select"); planSelect.style.width = "100%";
  const loadButton = el("button", { text: "Load Plan" });
  const newButton = el("button", { text: "New Plan" });
  const deleteButton = el("button", { text: "Delete Plan" });
  deleteButton.disabled = true;
  let deleteArmedSlug = "";
  const name = el("input", { type: "text", placeholder: "Plan label" }); name.style.width = "100%";
  const description = el("textarea", { placeholder: "Optional description" }); description.style.width = "100%";
  const stepsBox = el("div");
  const status = el("pre"); status.style.cssText = "white-space:pre-wrap;margin-top:.75rem";

  function setStatus(message) {
    status.textContent = message || "";
    try {
      if (message) sessionStorage.setItem(statusKey(), message);
      else sessionStorage.removeItem(statusKey());
    } catch {}
  }

  function refreshSelect(slug = "") {
    planSelect.innerHTML = "";
    planSelect.appendChild(el("option", { value: "", text: plans.length ? "Select a plan…" : "No saved plans" }));
    for (const plan of plans) {
      const slugValue = planSlug(plan);
      if (!slugValue) continue;
      planSelect.appendChild(el("option", { value: slugValue, text: String(plan?.payload?.label || plan?.label || plan?.title || slugValue) }));
    }
    planSelect.value = slug;
  }

  function choice(records, value, onChange, placeholder, options = {}) {
    const select = el("select"); select.style.width = "100%";
    select.appendChild(el("option", { value: "", text: placeholder }));
    const valueId = id(value);
    if (valueId && !records.some((record) => id(record) === valueId)) {
      select.appendChild(el("option", { value: valueId, text: `⚠ Missing from catalog — ${valueId}` }));
    }
    records.forEach((record) => option(select, record, options));
    select.value = valueId;
    select.addEventListener("change", () => onChange(selected(records, select.value)));
    return select;
  }

  function scopedPicker(card, step, scope, field, heading) {
    const records = byScope(catalogs.instructions, scope);
    card.appendChild(el("strong", { text: `${heading} (${records.length})` }));
    card.appendChild(choice(records, step[field], (value) => { step[field] = value; redraw(); }, `Choose ${scope}`, { titleOnly: true }));
    if (isMissing(step[field])) {
      const warning = el("div", { text: `⚠ Referenced ${scope} instruction is not in the catalog: ${id(step[field])}` });
      warning.style.cssText = "color:var(--text-warning);margin:.25rem 0 .5rem";
      card.appendChild(warning);
    }
  }

  function standingPicker(card, step) {
    const records = byScope(catalogs.instructions, "standing");
    const selectedSlugs = new Set(step.standingSlugs || []);
    const heading = el("div"); heading.style.cssText = "display:flex;gap:.5rem;align-items:center;margin-top:.65rem";
    heading.appendChild(el("strong", { text: `Standing instructions (${records.length})` }));
    const all = el("button", { text: "Select all" });
    const none = el("button", { text: "Clear all" });
    all.addEventListener("click", () => { step.standingSlugs = records.map(id); redraw(); });
    none.addEventListener("click", () => { step.standingSlugs = []; redraw(); });
    heading.append(all, none); card.appendChild(heading);
    const catalogSlugs = new Set(records.map(id));
    for (const slug of selectedSlugs) {
      if (catalogSlugs.has(slug)) continue;
      const row = el("label"); row.style.cssText = "display:flex;gap:.4rem;align-items:center;color:var(--text-warning)";
      const checkbox = el("input", { type: "checkbox" }); checkbox.checked = true;
      checkbox.addEventListener("change", () => {
        if (!checkbox.checked) selectedSlugs.delete(slug);
        step.standingSlugs = [...selectedSlugs];
        redraw();
      });
      row.append(checkbox, el("span", { text: `⚠ Missing from catalog — ${slug}` })); card.appendChild(row);
    }
    for (const record of records) {
      const row = el("label"); row.style.cssText = "display:flex;gap:.4rem;align-items:center";
      const checkbox = el("input", { type: "checkbox" }); checkbox.checked = selectedSlugs.has(id(record));
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedSlugs.add(id(record)); else selectedSlugs.delete(id(record));
        step.standingSlugs = [...selectedSlugs];
      });
      row.append(checkbox, el("span", { text: title(record) })); card.appendChild(row);
    }
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
        card.append(choice(catalogs.engines, step.engine, (v) => {
          step.engine = v;
          const allowed = modelsForEngine(catalogs.models, v);
          if (step.model && !allowed.some((record) => id(record) === id(step.model))) step.model = null;
          redraw();
        }, "Engine"));
        card.append(choice(modelsForEngine(catalogs.models, step.engine), step.model, (v) => { step.model = v; }, "Model"));
        standingPicker(card, step);
        scopedPicker(card, step, "role", "role", "Role");
        scopedPicker(card, step, "context", "context", "Context");
        scopedPicker(card, step, "task", "task", "Task");
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

  function disarmDelete() {
    deleteArmedSlug = "";
    deleteButton.textContent = "Delete Plan";
    deleteButton.classList.remove("mod-warning");
  }

  function clearForm() {
    loaded = null; name.value = ""; description.value = ""; steps = []; deleteButton.disabled = true; disarmDelete(); redraw();
  }

  function missingInstructionSlugs() {
    const catalog = new Set(catalogs.instructions.map(id));
    const missing = new Set();
    for (const step of steps) {
      if (step.kind !== "llm") continue;
      for (const slug of step.standingSlugs || []) if (slug && !catalog.has(slug)) missing.add(slug);
      for (const record of [step.role, step.context, step.task]) {
        const slug = id(record);
        if (slug && !catalog.has(slug)) missing.add(slug);
      }
    }
    return [...missing];
  }

  function loadSelectedPlan() {
    if (!planSelect.value) return setStatus("Select a plan first.");
    loaded = plans.find((plan) => planSlug(plan) === planSelect.value) || null;
    if (!loaded) return setStatus("The selected plan is no longer present in Git state.");
    name.value = loaded.payload?.label || "";
    description.value = loaded.payload?.description || "";
    steps = screenSteps(loaded, catalogs);
    deleteButton.disabled = false;
    redraw();
    const missing = missingInstructionSlugs();
    setStatus(missing.length
      ? `Loaded ${planSlug(loaded)} with ${missing.length} missing instruction reference${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`
      : `Loaded ${planSlug(loaded)}.`);
  }

  refresh.addEventListener("click", async () => {
    refresh.disabled = true; setStatus("Fetching server catalogue and re-reading local instructions…");
    try {
      await renderCreatePlan({ app, container });
    } catch (error) {
      const message = `Reload failed: ${error.message || error}`; setStatus(message); notify(message, 10000);
    } finally { refresh.disabled = false; }
  });

  planSelect.addEventListener("change", () => {
    disarmDelete();
    deleteButton.disabled = !planSelect.value;
  });
  loadButton.addEventListener("click", loadSelectedPlan);
  newButton.addEventListener("click", () => { planSelect.value = ""; clearForm(); setStatus("New plan form ready."); });
  deleteButton.addEventListener("click", async () => {
    const slug = planSelect.value || planSlug(loaded);
    if (!slug) return setStatus("Select a plan first.");
    const plan = plans.find((record) => planSlug(record) === slug) || loaded;
    const label = String(plan?.payload?.label || plan?.label || slug);

    if (deleteArmedSlug !== slug) {
      deleteArmedSlug = slug;
      deleteButton.textContent = "Confirm Delete";
      deleteButton.classList.add("mod-warning");
      setStatus(`Press Confirm Delete to remove “${label}” (${slug}) from autoscribe/config. Select another plan or press New Plan to cancel.`);
      return;
    }

    deleteButton.disabled = true;
    setStatus(`Deleting ${slug}…`);
    try {
      const commit = await deletePlan(root, slug);
      const deletedIndex = plans.findIndex((record) => planSlug(record) === slug);
      if (deletedIndex >= 0) plans.splice(deletedIndex, 1);
      clearForm();
      refreshSelect();
      notify(`Deleted plan ${slug} from Git.`);
      setStatus(`Deleted ${slug} from autoscribe/config (${String(commit).slice(0, 10)}). Pushed for server ingestion.`);
    } catch (error) {
      const message = `Delete failed: ${error.message || error}`; setStatus(message); notify(message, 10000);
      disarmDelete();
      deleteButton.disabled = !planSelect.value;
    }
  });
  const add = el("button", { text: "Add Step" });
  add.addEventListener("click", () => {
    steps.push({ kind: String(workflowConfig().plan_manager?.default_step_kind || "llm"), label: `Step ${steps.length + 1}`, argsJson: "{}", standingSlugs: byScope(catalogs.instructions, "standing").map(id) });
    redraw();
  });
  const save = el("button", { text: "Save Plan", class: "mod-cta" });
  save.addEventListener("click", async () => {
    save.disabled = true; setStatus("Saving plan…");
    try {
      for (const [index, step] of steps.entries()) {
        if (step.kind !== "llm") continue;
        if (!step.task) throw new Error(`Step ${index + 1}: choose a task instruction.`);
        step.instruction_slugs = {
          standing: [...new Set(step.standingSlugs || [])],
          role: step.role ? [id(step.role)] : [],
          context: step.context ? [id(step.context)] : [],
          task: [id(step.task)],
        };
      }
      const record = buildPlanRecord({ label: name.value, description: description.value, steps, force_slug: planSlug(loaded) || null });
      const commit = await savePlan(root, record);
      setStatus(`Saved ${planSlug(record)} to autoscribe/config (${String(commit).slice(0, 10)}). Pushed for server ingestion.`);
      notify(`Saved plan ${planSlug(record)} to Git.`);
      await renderCreatePlan({ app, container });
    } catch (error) {
      const message = `Save failed: ${error.message || error}`; setStatus(message); notify(message, 10000);
    } finally { save.disabled = false; }
  });

  refreshSelect();
  const pickerButtons = el("div"); pickerButtons.style.cssText = "display:flex;gap:.5rem;margin:.4rem 0 1rem"; pickerButtons.append(loadButton, newButton, deleteButton);
  const actionButtons = el("div"); actionButtons.style.cssText = "display:flex;gap:.5rem;margin-top:.75rem"; actionButtons.append(add, save);
  container.append(
    el("label", { text: "Existing plan" }), planSelect, pickerButtons,
    el("label", { text: "Plan label" }), name,
    el("label", { text: "Description" }), description,
    stepsBox, actionButtons, status,
  );
  redraw();
  try { status.textContent = sessionStorage.getItem(statusKey()) || ""; } catch {}
}

module.exports = async function define_plan(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const { openWorkflowModal } = require(path.join(root, "_control/scripts/lib/workflow-modal.js"));
  return openWorkflowModal({ app, title: "Define Plan", render: (container) => renderCreatePlan({ app, container }) });
};
