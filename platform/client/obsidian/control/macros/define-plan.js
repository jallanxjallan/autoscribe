"use strict";

const { loadConfig } = require("../scripts/lib/config-loader");
const { el } = require("../scripts/lib/dom.js");
const { activeInstructionSlugs } = require("../scripts/lib/instruction-query.js");
const { notify } = require("../scripts/lib/notify.js");
const { serviceCall: callService } = require("../scripts/lib/dispatch-service.js");
const { buildPlanRecord } = require("../scripts/plans/plan-record.js");

function workflowConfig() { return loadConfig("workflow"); }
function protocolConfig() { return loadConfig("protocol"); }
function stepKinds() { return workflowConfig().step_kinds || ["llm", "script", "rag"]; }
function statusKey() { return String(workflowConfig().define_plan?.status_storage_key || "autoscribe.define-plan.status"); }

function id(record) { return String(record?.slug || record?.record_identity || record?.key || "").trim(); }
function title(record) { return String(record?.title || record?.label || record?.name || id(record)); }
function selected(records, value) { return records.find((record) => id(record) === String(value || "")) || null; }
function planSlug(record) { return String(record?.record_identity || record?.slug || record?.key || "").trim(); }
function sortRecords(records) {
  return [...records].sort((a, b) =>
    title(a).localeCompare(title(b), undefined, { sensitivity: "base", numeric: true }) ||
    id(a).localeCompare(id(b), undefined, { sensitivity: "base", numeric: true })
  );
}
function byScope(records, scope) {
  return sortRecords(records.filter((record) => String(record?.scope || "").toLowerCase() === scope));
}

function option(select, record, { titleOnly = false } = {}) {
  const recordId = id(record);
  const display = title(record);
  select.appendChild(el("option", {
    value: recordId,
    text: titleOnly || !recordId || display === recordId ? display : `${display} — ${recordId}`,
  }));
}

async function serviceCall(app, command, input = {}) {
  const result = await callService(app, command, input);
  const output = JSON.parse(String(result.stdout || "{}").trim() || "{}");
  if (!output.ok) throw new Error(output.error || `${command} failed`);
  return output;
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
        standingSlugs: Array.isArray(refs.standing) ? [...refs.standing] : [],
        role: selected(catalogs.instructions, refs.role?.[0]),
        context: selected(catalogs.instructions, refs.context?.[0]),
        task: selected(catalogs.instructions, refs.task?.[0] || step.instruction),
        argsJson: JSON.stringify(step.args || {}, null, 2),
      };
    });
}

async function renderCreatePlan({ app, container }) {
  container.empty();
  const protocol = protocolConfig();
  const snapshotSpec = protocol.service_operations?.define_plan_snapshot || {};
  const snapshot = await serviceCall(app, String(snapshotSpec.command || "define-plan-snapshot"), {
    version: Number(snapshotSpec.request_version || 1),
  });

  const catalogs = catalogsFrom(snapshot);
  const plans = catalogs.plans;
  let loaded = null;
  let steps = [];

  container.appendChild(el("h2", { text: "Define Plan" }));
  const toolbar = el("div");
  toolbar.style.cssText = "display:flex;gap:.5rem;align-items:center;margin-bottom:.75rem";
  const refresh = el("button", { text: "Refresh" });
  const freshness = el("span", { text: snapshot.refreshed_at ? `Service state: ${snapshot.refreshed_at}` : "Service state has not been refreshed yet." });
  toolbar.append(refresh, freshness);
  container.appendChild(toolbar);

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
    try {
      if (message) sessionStorage.setItem(statusKey(), message);
      else sessionStorage.removeItem(statusKey());
    } catch {}
  }

  function refreshSelect(slug = "") {
    planSelect.innerHTML = "";
    planSelect.appendChild(el("option", { value: "", text: plans.length ? "Select a plan…" : "No saved plans" }));
    for (const plan of sortRecords(plans)) {
      const slugValue = planSlug(plan);
      if (!slugValue) continue;
      planSelect.appendChild(el("option", { value: slugValue, text: String(plan?.payload?.label || plan?.label || plan?.title || slugValue) }));
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

  function scopedPicker(card, step, scope, field, heading) {
    const records = byScope(catalogs.instructions, scope);
    card.appendChild(el("strong", { text: `${heading} (${records.length})` }));
    card.appendChild(choice(records, step[field], (value) => { step[field] = value; redraw(); }, `Choose ${scope}`, { titleOnly: true }));
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
        card.append(choice(catalogs.engines, step.engine, (v) => { step.engine = v; }, "Engine"));
        card.append(choice(catalogs.models, step.model, (v) => { step.model = v; }, "Model"));
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

  function clearForm() {
    loaded = null; name.value = ""; type.value = ""; description.value = ""; steps = []; redraw();
  }

  function loadSelectedPlan() {
    if (!planSelect.value) return setStatus("Select a plan first.");
    loaded = plans.find((plan) => planSlug(plan) === planSelect.value) || null;
    if (!loaded) return setStatus("Service did not return the selected plan.");
    name.value = loaded.payload?.label || loaded.label || "";
    type.value = loaded.payload?.type || loaded.type || "";
    description.value = loaded.payload?.description || loaded.description || "";
    steps = screenSteps(loaded, catalogs); redraw(); setStatus(`Loaded ${planSlug(loaded)}.`);
  }

  refresh.addEventListener("click", async () => {
    refresh.disabled = true; setStatus("Refreshing service state…");
    try {
      const spec = protocol.service_operations?.define_plan_refresh || {};
      const output = await serviceCall(app, String(spec.command || "define-plan-refresh"), {
        version: Number(spec.request_version || 1),
        instruction_slugs: activeInstructionSlugs(app),
      });
      notify(`Refresh complete: ${output.uploaded_instructions || 0} instruction(s) uploaded.`);
      await renderCreatePlan({ app, container });
    } catch (error) {
      const message = `Refresh failed: ${error.message || error}`; setStatus(message); notify(message, 10000);
    } finally { refresh.disabled = false; }
  });

  loadButton.addEventListener("click", loadSelectedPlan);
  newButton.addEventListener("click", () => { planSelect.value = ""; clearForm(); setStatus("New plan form ready."); });
  const add = el("button", { text: "Add Step" });
  add.addEventListener("click", () => {
    steps.push({ kind: String(workflowConfig().define_plan?.default_step_kind || "llm"), label: `Step ${steps.length + 1}`, argsJson: "{}", standingSlugs: byScope(catalogs.instructions, "standing").map(id) });
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
      const record = buildPlanRecord({ label: name.value, type: type.value, description: description.value, steps, force_slug: planSlug(loaded) || null });
      const spec = protocol.plan_save || {};
      await serviceCall(app, String(spec.command || "plan-save"), { version: Number(spec.request_version || 1), plan: record });
      setStatus(`Saved ${planSlug(record)}.`); notify(`Saved plan ${planSlug(record)}.`);
      await renderCreatePlan({ app, container });
    } catch (error) {
      const message = `Save failed: ${error.message || error}`; setStatus(message); notify(message, 10000);
    } finally { save.disabled = false; }
  });

  refreshSelect();
  const pickerButtons = el("div"); pickerButtons.style.cssText = "display:flex;gap:.5rem;margin:.4rem 0 1rem"; pickerButtons.append(loadButton, newButton);
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

module.exports = async function define_plan(params = {}) {
  const app = params.app || globalThis.app;
  if (!app?.vault || !app?.workspace) throw new Error("Obsidian app object unavailable.");
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const { openWorkflowModal } = require(path.join(root, "_control/scripts/lib/workflow-modal.js"));
  return openWorkflowModal({ app, title: "Define Plan", render: (container) => renderCreatePlan({ app, container }) });
};
