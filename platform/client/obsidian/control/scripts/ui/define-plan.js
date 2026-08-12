"use strict";

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const { spawnSync } = nodeRequire("node:child_process");

const ZSH = "/usr/bin/zsh";
const STEP_KINDS = ["llm", "script", "rag"];
const SCOPES = ["standing", "role", "context", "task"];
const PREFIXES = { standing: "std", role: "rol", context: "cxt", task: "tsk" };
const STATUS_KEY = "autoscribe.define-plan.status";
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

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

function id(record) { return String(record?.registry_key || record?.key || record?.slug || record?.record_identity || ""); }
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
function isLocalInstruction(record) {
  return Boolean(record && record.source === "active" && record.path);
}
function localInstructionSet(record, root) {
  if (!isLocalInstruction(record)) return null;
  const relpath = String(record.path || "").trim();
  if (!relpath) return null;
  return {
    slug: id(record),
    path: relpath,
    source_path: relpath,
    abspath: pathMod.resolve(root, relpath),
  };
}

function encodeTime(time, length) {
  let value = BigInt(time);
  let out = "";
  for (let index = 0; index < length; index += 1) {
    out = CROCKFORD[Number(value % 32n)] + out;
    value /= 32n;
  }
  return out;
}


function screenSteps(plan, catalogs) {
  return Object.entries(plan?.payload?.steps || {}).sort(([a], [b]) => Number(a) - Number(b)).map(([, step]) => {
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
  const { listPlanRecords, loadPlanRecord, savePlanRecord, deletePlanRecord } = loadControl("scripts/plans/plan-store.js");
  const { callFeederAsync, handoffFeeder } = loadControl("scripts/lib/feeder-ipc.js");
  const { vaultRoot } = loadControl("scripts/lib/vault-state.js");
  const { snapshotList } = loadControl("scripts/lib/control-loader.js");
  const { makeSlug } = loadControl("scripts/lib/slug.js");
  const root = vaultRoot(app);
  const control = ascSnapshot("control", root);
  const catalogs = {
    engines: snapshotList(control, "engines"), models: snapshotList(control, "models"),
    scripts: snapshotList(control, "local_scripts"), ragProfiles: snapshotList(control, "rag_profiles"),
    instructions: await callFeederAsync(app, "instructions.catalog", { include_pipeline: true }),
  };
  let plans = listPlanRecords(app), loaded = null, steps = [];

  container.appendChild(el("h2", { text: "Define Plan" }));
  container.appendChild(el("p", { text: "Create or modify a plan and publish its complete local instruction set. Plans are stored under _plans/ and versioned in Git." }));

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
      if (message) sessionStorage.setItem(STATUS_KEY, message);
      else sessionStorage.removeItem(STATUS_KEY);
    } catch {}
  }

  function refreshInstructions() {
    return callFeederAsync(app, "instructions.catalog", { include_pipeline: true }).then((records) => {
      catalogs.instructions = records;
      redraw();
      return records;
    });
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

  function instructionDirectory() {
    const active = catalogs.instructions.filter((item) => item.source === "active" && item.path);
    if (active.length) {
      const counts = new Map();
      for (const item of active) {
        const dir = pathMod.dirname(item.path);
        counts.set(dir, (counts.get(dir) || 0) + 1);
      }
      return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
    }
    return "Instructions";
  }

  async function createInstruction(scope, step, field) {
    notify(`Creating ${scope} instruction…`);
    const title = String(window.prompt(`Title for new ${scope} instruction:`) || "").trim();
    if (!title) return;
    const slug = makeSlug(PREFIXES[scope], title);
    const dir = instructionDirectory();
    const safeName = title.replace(/[\\/:*?"<>|]/g, "-").trim() || "Untitled Instruction";
    let relpath = pathMod.posix.join(dir === "." ? "" : dir, `${safeName}.md`);
    let counter = 2;
    while (app.vault.getAbstractFileByPath(relpath)) {
      relpath = pathMod.posix.join(dir === "." ? "" : dir, `${safeName} ${counter}.md`);
      counter += 1;
    }
    const body = `---\nslug: ${slug}\ntype: instruction\nscope: ${scope}\nversion: 1\ntags: []\n---\n\n# ${title}\n\n`;
    const parent = pathMod.posix.dirname(relpath);
    if (parent && parent !== "." && !app.vault.getAbstractFileByPath(parent)) await app.vault.createFolder(parent);
    const file = await app.vault.create(relpath, body);
    await refreshInstructions();
    const record = selected(catalogs.instructions, slug);
    if (scope === "standing") {
      step.standingSlugs = [...new Set([...(step.standingSlugs || []), slug])];
    } else {
      step[field] = record || { slug, path: relpath, title, label: title, scope, source: "active", abspath: pathMod.join(root, relpath) };
    }
    redraw();
    await app.workspace.getLeaf(false).openFile(file);
    notify(`Created ${scope} instruction: ${title}.`);
  }

  function openInstruction(record) {
    if (!record?.path) return;
    const file = app.vault.getAbstractFileByPath(record.path);
    if (file) app.workspace.getLeaf(false).openFile(file);
  }

  function scopedPicker(card, step, scope, field, titleText) {
    const records = byScope(catalogs.instructions, scope);
    const heading = el("div"); heading.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-top:.65rem";
    heading.appendChild(el("strong", { text: titleText }));
    const buttons = el("span");
    const create = el("button", { text: "Create instruction" });
    create.addEventListener("click", () => createInstruction(scope, step, field).catch((error) => notify(`Create instruction failed: ${error.message || error}`, 10000)));
    buttons.appendChild(create);
    if (step[field]?.path) {
      const open = el("button", { text: "Open" }); open.addEventListener("click", () => openInstruction(step[field])); buttons.appendChild(open);
    }
    heading.appendChild(buttons);
    card.appendChild(heading);
    card.appendChild(choice(records, step[field], (value) => { step[field] = value; redraw(); }, `Choose ${scope}`, { titleOnly: true }));
    const current = step[field];
    if (current) {
      const selectedRow = el("div"); selectedRow.style.cssText = "margin:.2rem 0 .35rem";
      if (isLocalInstruction(current)) {
        const link = el("button", { text: `[[${title(current)}]]` });
        link.style.cssText = "background:none;border:0;padding:0;color:var(--link-color);text-align:left";
        link.addEventListener("click", () => openInstruction(current));
        selectedRow.appendChild(link);
      } else {
        selectedRow.appendChild(el("span", { text: title(current) }));
      }
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
    const create = el("button", { text: "Create instruction" });
    create.addEventListener("click", () => createInstruction("standing", step, "standingSlugs").catch((error) => notify(`Create instruction failed: ${error.message || error}`, 10000)));
    buttons.append(selectAll, clearAll, create); heading.appendChild(buttons); card.appendChild(heading);
    const selectedSlugs = new Set(step.standingSlugs || []);
    for (const record of records) {
      const row = el("div"); row.style.cssText = "display:flex;align-items:center;gap:.4rem";
      const checkbox = el("input", { type: "checkbox" }); checkbox.checked = selectedSlugs.has(id(record));
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedSlugs.add(id(record)); else selectedSlugs.delete(id(record));
        step.standingSlugs = [...selectedSlugs];
      });
      if (isLocalInstruction(record)) {
        const link = el("button", { text: `[[${title(record)}]]` });
        link.style.cssText = "background:none;border:0;padding:0;color:var(--link-color);text-align:left";
        link.addEventListener("click", () => openInstruction(record));
        row.append(checkbox, link);
      } else {
        row.append(checkbox, el("span", { text: title(record) }));
      }
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
      const stepLabel = el("input", { type: "text", value: step.label || `Step ${index + 1}` }); stepLabel.style.width = "100%";
      stepLabel.addEventListener("input", () => { step.label = stepLabel.value; });
      const kind = el("select"); STEP_KINDS.forEach((value) => kind.appendChild(el("option", { value, text: value })));
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
      const remove = el("button", { text: "Delete Step" }); remove.addEventListener("click", () => { steps.splice(index, 1); redraw(); notify(`Deleted step ${index + 1}.`); }); card.append(remove);
      stepsBox.appendChild(card);
    });
  }

  function loadSelectedPlan() {
    notify("Loading plan…");
    if (!planSelect.value) {
      setStatus(plans.length ? "Select a saved plan, then click Load Plan." : "No saved plans were found under _plans/.");
      return;
    }
    try {
      loaded = loadPlanRecord(app, planSelect.value);
      name.value = loaded.payload?.label || loaded.label || "";
      type.value = loaded.payload?.type || loaded.type || "";
      description.value = loaded.payload?.description || loaded.description || "";
      steps = screenSteps(loaded, catalogs);
      redraw();
      setStatus(`Loaded ${planSlug(loaded)} from ${loaded.path}`);
      notify(`Loaded plan ${planSlug(loaded)}.`);
    } catch (error) { const message = `Load failed: ${error.message || error}`; setStatus(message); notify(message, 10000); }
  }

  loadButton.addEventListener("click", loadSelectedPlan);
  planSelect.addEventListener("dblclick", loadSelectedPlan);
  newButton.addEventListener("click", () => { planSelect.value = ""; clearForm(); setStatus("New plan form ready."); notify("New plan form ready."); name.focus(); });

  const add = el("button", { text: "Add Step" });
  add.addEventListener("click", () => {
    steps.push({
      kind: "llm", label: `Step ${steps.length + 1}`, argsJson: "{}",
      standingSlugs: byScope(catalogs.instructions, "standing").map(id),
    });
    redraw();
    notify(`Added step ${steps.length}.`);
  });

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
      const savedPath = savePlanRecord(app, record);
      loaded = { ...record, path: savedPath };
      plans = listPlanRecords(app); refreshSelect(planSlug(record));

      const selectedSlugs = new Set();
      for (const step of steps) for (const values of Object.values(step.instruction_slugs || {})) for (const slug of values) selectedSlugs.add(slug);
      const instructionSets = [...selectedSlugs]
        .map((slug) => localInstructionSet(selected(catalogs.instructions, slug), root))
        .filter(Boolean);
      handoffFeeder(app, "plan.save", { record, instruction_sets: instructionSets });
      // Fire-and-forget: feeder/server completion and failures belong in logs/status.
    } catch (error) {
      console.error("Define Plan handoff failed before feeder launch", error);
    }
  });

  const del = el("button", { text: "Delete Plan" });
  del.addEventListener("click", () => {
    notify("Deleting plan…");
    if (!loaded) { const message = "Load a plan before deleting it."; setStatus(message); notify(message); return; }
    try {
      const deletedPath = deletePlanRecord(app, planSlug(loaded));
      plans = listPlanRecords(app); refreshSelect(); clearForm(); setStatus(`Deleted ${deletedPath}`); notify(`Deleted plan ${deletedPath}.`);
    } catch (error) { const message = `Delete failed: ${error.message || error}`; setStatus(message); notify(message, 10000); }
  });

  const pickerButtons = el("div"); pickerButtons.style.cssText = "display:flex;gap:.5rem;margin:.4rem 0 1rem"; pickerButtons.append(loadButton, newButton);
  const actionButtons = el("div"); actionButtons.style.cssText = "display:flex;gap:.5rem;margin-top:.75rem"; actionButtons.append(add, save, del);

  refreshSelect();
  container.append(planLabel, planSelect, pickerButtons, nameLabel, name, typeLabel, type, descriptionLabel, description, stepsBox, actionButtons, status);
  redraw();
  try { status.textContent = sessionStorage.getItem(STATUS_KEY) || ""; } catch {}
}

module.exports = { renderCreatePlan };
