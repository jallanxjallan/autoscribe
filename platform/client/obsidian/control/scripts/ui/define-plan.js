"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const { spawnSync } = nodeRequire("node:child_process");
const { loadConfig } = require("../lib/config-loader");

function workflowConfig() { return loadConfig("workflow"); }
function pathsConfig() { return loadConfig("paths"); }
function instructionConfig() { return loadConfig("instructions"); }
function serviceConfig() { return loadConfig("service"); }
function protocolConfig() { return loadConfig("protocol"); }
function expandHome(value) { return String(value || "").replace(/^\$HOME(?=\/|$)/, process.env.HOME || ""); }
function scopeFromPrefix(prefix) {
  return Object.entries(instructionConfig().plan_scopes || {}).find(([, item]) => String(item.prefix) === String(prefix))?.[0] || "";
}
function stepKinds() { return workflowConfig().step_kinds || []; }
function scopes() { return Object.keys(instructionConfig().plan_scopes || {}); }
function statusKey() { return String(workflowConfig().define_plan?.status_storage_key || "autoscribe.define-plan.status"); }
function crockford() { return String(workflowConfig().define_plan?.id_alphabet || "0123456789ABCDEFGHJKMNPQRSTVWXYZ"); }

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

function ascSnapshot(name, cwd) {
  const spec = protocolConfig().asc_snapshots?.[name] || {};
  const command = [pathsConfig().asc_command, spec.command, spec.subcommand].map(String).filter(Boolean).join(" ");
  const result = spawnSync(String(pathsConfig().preferred_shell), ["-lic", command], {
    cwd, encoding: "utf8", timeout: Number(workflowConfig().define_plan?.snapshot_timeout_ms), maxBuffer: Number(workflowConfig().define_plan?.snapshot_max_buffer_bytes),
  });
  if (result.error || result.status !== 0) {
    throw new Error(String(result.stderr || result.error?.message || `${spec.label} failed`).trim());
  }
  return JSON.parse(String(result.stdout || "{}"));
}

async function serviceCall(app, command, input = null) {
  const root = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const control = nodeRequire(pathMod.join(root, "_control/scripts/lib/dispatch-service.js"));
  const executable = control.serviceCommand(app);
  const result = await control.run(executable.command, [...executable.prefix, command], {
    cwd: root, input: input == null ? "" : JSON.stringify(input),
  });
  const output = JSON.parse(String(result.stdout || "{}").trim() || "{}");
  if (!output.ok) throw new Error(output.error || `${command} failed`);
  return output;
}

function id(record) { return String(record?.slug || record?.record_identity || record?.registry_key || record?.key || ""); }
function fileStem(value) {
  const clean = String(value || "").replace(/\\/g, "/");
  return clean ? pathMod.posix.basename(clean).replace(/\.[^.]+$/, "") : "";
}
function label(record) {
  return String(
    record?.title ||
    record?.display_name ||
    record?.name ||
    fileStem(record?.path || record?.source_path || record?.file) ||
    fileStem(id(record)) ||
    record?.label ||
    id(record)
  );
}
function title(record) { return String(record?.title || record?.label || id(record)); }
function option(select, record, { titleOnly = false } = {}) {
  const display = titleOnly ? title(record) : label(record);
  const recordId = id(record);
  const text = titleOnly || !recordId || display === recordId ? display : `${display} — ${recordId}`;
  select.appendChild(el("option", { value: id(record), text }));
}
function selected(records, value) { return records.find((record) => id(record) === value) || null; }
function planSlug(record) { return String(record?.record_identity || record?.slug || ""); }
function byScope(records, scope) { return records.filter((record) => String(record?.scope || "").toLowerCase() === scope); }
function encodeTime(time, length) {
  let value = BigInt(time);
  let out = "";
  for (let index = 0; index < length; index += 1) {
    out = crockford()[Number(value % 32n)] + out;
    value /= 32n;
  }
  return out;
}


function screenSteps(plan, catalogs) {
  return Object.entries(plan?.payload?.steps || plan?.steps || {}).sort(([a], [b]) => Number(a) - Number(b)).map(([, step]) => {
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
      task: selected(catalogs.instructions, refs.task?.[0] || refs.instructions?.[0] || step.instruction),
      argsJson: JSON.stringify(step.args || {}, null, 2),
    };
  });
}

function materializeServerPlan(record) {
  const slug = String(record?.record_identity || record?.slug || "");
  const parse = (value, fallback = {}) => {
    if (value && typeof value === "object") return value;
    try { return JSON.parse(String(value || "")); } catch { return fallback; }
  };
  if (record?.payload) return { ...record, record_identity: slug };
  return { ...record, record_identity: slug, payload: {
    ...parse(record?.metadata_json), steps: parse(record?.steps_json),
    label: record?.label || slug,
  }};
}

async function renderCreatePlan({ app, container }) {
  container.empty();
  const controlVaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
  const loadControl = (relativePath) => {
    const implementation = pathMod.join(controlVaultRoot, "_control", ...relativePath.split("/"));
    if (relativePath === "scripts/lib/control-loader.js") {
      try { delete nodeRequire.cache[nodeRequire.resolve(implementation)]; } catch (_) {}
    }
    return nodeRequire(implementation);
  };
  const { notify } = loadControl("scripts/lib/notify.js");
  const { buildPlanRecord } = loadControl("scripts/plans/plan-record.js");
  const { vaultRoot } = loadControl("scripts/lib/vault-state.js");
  const { snapshotList, listInstructions } = loadControl("scripts/lib/control-loader.js");
  const root = vaultRoot(app);
  const control = ascSnapshot("control", root);
  const service = await serviceCall(app, String((protocolConfig().service_operations?.define_plan_snapshot || protocolConfig().define_plan_snapshot || {}).command));
  const serverRegistries = service.server?.registries || {};
  const serverInstructions = Object.values(serverRegistries.instructions || {}).map((record) => ({
    ...record, slug: record.slug || record.record_identity, source: "server",
    scope: record.scope || scopeFromPrefix(String(record.slug || record.record_identity || "").split(".")[0]),
  }));
  const localInstructions = listInstructions(app);
  const instructionMap = new Map(serverInstructions.map((record) => [id(record), record]));
  // Markdown is authoritative: a local/library file overrides the runtime copy.
  localInstructions.forEach((record) => instructionMap.set(id(record), record));
  const catalogs = {
    engines: snapshotList(control, "engines"), models: snapshotList(control, "models"),
    scripts: snapshotList(control, "local_scripts"), ragProfiles: snapshotList(control, "rag_profiles"),
    instructions: [...instructionMap.values()],
  };
  const serverPlans = Object.values(serverRegistries.plans || {}).map(materializeServerPlan);
  const planMap = new Map(serverPlans.map((record) => [planSlug(record), record]));
  service.authored_plans.forEach((record) => planMap.set(planSlug(record), record));
  let plans = [...planMap.values()], loaded = null, steps = [];

  container.appendChild(el("h2", { text: "Define Plan" }));
  container.appendChild(el("p", { text: "Create or modify a project plan on the AutoScribe server. Markdown instructions from the active project and generic Library are synchronized before the plan is saved." }));

  const planLabel = el("label", { text: "Existing plan" });
  const planSelect = el("select"); planSelect.style.width = "100%";
  const loadButton = el("button", { text: "Load Plan" });
  const newButton = el("button", { text: "New Plan" });
  const nameLabel = el("label", { text: "Plan label" });
  const name = el("input", { type: "text", placeholder: "Plan label" }); name.style.width = "100%";
  const typeLabel = el("label", { text: "Plan type" });
  const type = el("input", { type: "text", placeholder: "e.g. revise, research, proofread" }); type.style.width = "100%";
  const descriptionLabel = el("label", { text: "Description" });
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

  function clearForm() {
    loaded = null;
    name.value = "";
    type.value = "";
    description.value = "";
    steps = [];
    redraw();
  }

  function refreshSelect(slug = "") {
    planSelect.innerHTML = "";
    planSelect.appendChild(el("option", { value: "", text: plans.length ? "Select a plan…" : "No saved plans" }));
    plans.forEach((plan) => {
      const display = String(plan?.payload?.title || plan?.title || plan?.payload?.label || plan?.label || planSlug(plan));
      planSelect.appendChild(el("option", { value: planSlug(plan), text: display }));
    });
    planSelect.value = slug;
  }

  function choice(records, value, onChange, placeholder, { titleOnly = false } = {}) {
    const select = el("select"); select.style.width = "100%";
    select.appendChild(el("option", { value: "", text: placeholder }));
    records.forEach((record) => option(select, record, { titleOnly }));
    select.value = id(value);
    select.addEventListener("change", () => onChange(selected(records, select.value)));
    return select;
  }

  function scopedPicker(card, step, scope, field, titleText) {
    const records = byScope(catalogs.instructions, scope);
    const heading = el("div"); heading.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-top:.65rem";
    heading.appendChild(el("strong", { text: titleText }));
    heading.appendChild(el("span", { text: `${records.length} available` }));
    card.appendChild(heading);
    card.appendChild(choice(records, step[field], (value) => { step[field] = value; redraw(); }, `Choose ${scope}`, { titleOnly: true }));
    const current = step[field];
    if (current) {
      const selectedRow = el("div"); selectedRow.style.cssText = "margin:.2rem 0 .35rem";
      selectedRow.appendChild(el("span", { text: title(current) }));
      card.appendChild(selectedRow);
    }
  }

  function standingPicker(card, step) {
    const records = byScope(catalogs.instructions, "standing");
    const heading = el("div"); heading.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-top:.65rem";
    heading.appendChild(el("strong", { text: "Standing instructions" }));
    const buttons = el("span");
    const selectAll = el("button", { text: "Select all" });
    selectAll.addEventListener("click", () => { step.standingSlugs = records.map(id); redraw(); notify(`Selected all ${records.length} standing instruction(s).`); });
    const clearAll = el("button", { text: "Clear all" });
    clearAll.addEventListener("click", () => { step.standingSlugs = []; redraw(); notify("Cleared standing instruction selection."); });
    buttons.append(selectAll, clearAll); heading.appendChild(buttons); card.appendChild(heading);
    const selectedSlugs = new Set(step.standingSlugs || []);
    for (const record of records) {
      const row = el("div"); row.style.cssText = "display:flex;align-items:center;gap:.4rem";
      const checkbox = el("input", { type: "checkbox" }); checkbox.checked = selectedSlugs.has(id(record));
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedSlugs.add(id(record)); else selectedSlugs.delete(id(record));
        step.standingSlugs = [...selectedSlugs];
      });
      row.append(checkbox, el("span", { text: title(record) }));
      card.appendChild(row);
    }
    for (const slug of selectedSlugs) {
      if (!records.some((record) => id(record) === slug)) card.appendChild(el("div", { text: `⚠ Missing standing instruction: ${slug}` }));
    }
  }

  function redraw() {
    stepsBox.innerHTML = "";
    steps.forEach((step, index) => {
      const card = el("div"); card.style.cssText = "border:1px solid var(--background-modifier-border);padding:.75rem;margin:.75rem 0;border-radius:8px";
      const stepLabel = el("input", { type: "text", value: step.label || `${workflowConfig().define_plan?.step_label_prefix || "Step"} ${index + 1}` }); stepLabel.style.width = "100%";
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
      const args = el("textarea"); args.style.width = "100%"; args.value = step.argsJson || String(workflowConfig().define_plan?.default_args_json || "{}");
      args.addEventListener("input", () => { step.argsJson = args.value; }); card.append(args);
      const remove = el("button", { text: "Delete Step" }); remove.addEventListener("click", () => { steps.splice(index, 1); redraw(); notify(`Deleted step ${index + 1}.`); }); card.append(remove);
      stepsBox.appendChild(card);
    });
  }

  async function loadSelectedPlan() {
    notify("Loading plan…");
    if (!planSelect.value) {
      setStatus(plans.length ? "Select a server plan, then click Load Plan." : "No plans were found on the server.");
      return;
    }
    try {
      loaded = plans.find((plan) => planSlug(plan) === planSelect.value) || null;
      name.value = loaded.payload?.label || loaded.label || "";
      type.value = loaded.payload?.type || loaded.type || "";
      description.value = loaded.payload?.description || loaded.description || "";
      steps = screenSteps(loaded, catalogs);
      redraw();
      setStatus(`Loaded ${planSlug(loaded)} from the server.`);
      notify(`Loaded plan ${planSlug(loaded)}.`);
    } catch (error) { const message = `Load failed: ${error.message || error}`; setStatus(message); notify(message, 10000); }
  }

  loadButton.addEventListener("click", () => loadSelectedPlan().catch((error) => notify(`Load failed: ${error.message || error}`, 10000)));
  planSelect.addEventListener("dblclick", () => loadSelectedPlan().catch((error) => notify(`Load failed: ${error.message || error}`, 10000)));
  newButton.addEventListener("click", () => { planSelect.value = ""; clearForm(); setStatus("New plan form ready."); notify("New plan form ready."); name.focus(); });

  const add = el("button", { text: "Add Step" });
  add.addEventListener("click", () => {
    steps.push({
      kind: String(workflowConfig().define_plan?.default_step_kind || "llm"), label: `${workflowConfig().define_plan?.step_label_prefix || "Step"} ${steps.length + 1}`, argsJson: String(workflowConfig().define_plan?.default_args_json || "{}"),
      standingSlugs: byScope(catalogs.instructions, String(workflowConfig().define_plan?.default_scope || "standing")).map(id),
    });
    redraw();
    notify(`Added step ${steps.length}.`);
  });

  async function syncReferencedMarkdown() {
    const selectedSlugs = new Set();
    for (const step of steps) {
      for (const slug of step.standingSlugs || []) selectedSlugs.add(slug);
      for (const record of [step.role, step.context, step.task]) {
        if (record && id(record)) selectedSlugs.add(id(record));
      }
    }

    const localBySlug = new Map(localInstructions.map((record) => [id(record), record]));
    const byRoot = new Map();
    for (const slug of selectedSlugs) {
      const record = localBySlug.get(slug);
      if (!record?.root || !record?.path) continue;
      if (!byRoot.has(record.root)) byRoot.set(record.root, []);
      byRoot.get(record.root).push(record.path);
    }

    const syncSpec = protocolConfig().service_operations?.instructions_sync || {};
    for (const [instructionRoot, paths] of byRoot) {
      await serviceCall(app, String(syncSpec.command || "instructions-sync"), {
        version: Number(syncSpec.request_version || 1),
        root: instructionRoot,
        paths: [...new Set(paths)],
      });
    }
  }

  const save = el("button", { text: "Save Plan", class: "mod-cta" });
  save.addEventListener("click", async () => {
    notify("Saving plan and publishing dependencies…");
    try {
      for (const [index, step] of steps.entries()) {
        if (step.kind !== "llm") { delete step.instruction_slugs; continue; }
        if (!step.task) throw new Error(`Step ${index + 1}: choose a task instruction.`);
        step.instruction_slugs = {
          standing: [...new Set(step.standingSlugs || [])],
          role: step.role ? [id(step.role)] : [],
          context: step.context ? [id(step.context)] : [],
          task: [id(step.task)],
        };
      }
      const record = buildPlanRecord({ label: name.value, type: type.value, description: description.value, steps, force_slug: planSlug(loaded) || null });
      await syncReferencedMarkdown();
      const svc = serviceConfig();
      const dbEnv = String(svc.environment?.database || "AUTOSCRIBE_DATABASE");
      const saveProtocol = protocolConfig().plan_save || {};
      await serviceCall(app, String(saveProtocol.command || "plan-save"), {
        version: Number(saveProtocol.request_version || 1),
        database_path: process.env[dbEnv] || expandHome(svc.database_default),
        plan: record,
      });
      loaded = record;
      planMap.set(planSlug(record), record); plans = [...planMap.values()];
      refreshSelect(planSlug(record));
      setStatus(`Saved ${planSlug(record)} on the server.`);
      notify(`Saved plan ${planSlug(record)}.`);
    } catch (error) {
      const message = `Save failed: ${error.message || error}`;
      setStatus(message);
      notify(message, 10000);
    }
  });

  const pickerButtons = el("div"); pickerButtons.style.cssText = "display:flex;gap:.5rem;margin:.4rem 0 1rem"; pickerButtons.append(loadButton, newButton);
  const actionButtons = el("div"); actionButtons.style.cssText = "display:flex;gap:.5rem;margin-top:.75rem"; actionButtons.append(add, save);

  refreshSelect();
  container.append(planLabel, planSelect, pickerButtons, nameLabel, name, typeLabel, type, descriptionLabel, description, stepsBox, actionButtons, status);
  redraw();
  try { status.textContent = sessionStorage.getItem(statusKey()) || ""; } catch {}
}

module.exports = { renderCreatePlan };
