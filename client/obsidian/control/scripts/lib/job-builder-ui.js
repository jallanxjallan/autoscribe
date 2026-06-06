async function renderJobBuilder(options) {
  const { app, container, registries, instructions, outputDir = "_jobs" } = options;

  const registryRoot = (registries && registries.registries) || {};
  const engines = sortByLabel(Object.values(registryRoot.engines || {}));
  const localScripts = sortByLabel(Object.values(registryRoot.local_scripts || {}));
  const ragProfiles = sortByLabel(Object.values(registryRoot.rag_profiles || {}));

  const state = {
    label: "",
    slug: "",
    scope: "vault",
    steps: [],
  };

  container.empty ? container.empty() : (container.innerHTML = "");

  const root = el("div", { className: "asc-job-builder" });
  const status = el("div", { className: "asc-job-builder-status" });
  const stepsRoot = el("div", { className: "asc-job-builder-steps" });

  root.appendChild(styleElement());
  root.appendChild(el("h2", {}, "Define AutoScribe Job"));
  root.appendChild(
    el(
      "p",
      { className: "asc-muted" },
      "Build a structured JSON job from live AutoScribe registries and Markdown instruction files in this vault."
    )
  );

  root.appendChild(
    fieldRow([
      labelledInput(
        "Job label",
        textInput({
          placeholder: "Normalize imported document",
          oninput: (event) => {
            state.label = event.target.value;
          },
        })
      ),
      labelledInput(
        "Scope",
        selectInput({
          value: state.scope,
          options: [
            { value: "vault", label: "vault" },
            { value: "global", label: "global" },
          ],
          onchange: (event) => {
            state.scope = event.target.value;
          },
        })
      ),
    ])
  );

  const slugInput = textInput({
    placeholder: "job.normalize-import.abc123",
    oninput: (event) => {
      state.slug = event.target.value.trim();
    },
  });

  root.appendChild(
    fieldRow([
      labelledInput("Slug", slugInput),
      el(
        "button",
        {
          type: "button",
          className: "asc-button asc-button-secondary",
          onclick: () => {
            state.slug = makeJobSlug(state.label);
            slugInput.value = state.slug;
            setStatus(status, `Generated slug: ${state.slug}`, "info");
          },
        },
        "Generate slug"
      ),
    ])
  );

  const toolbar = el("div", { className: "asc-toolbar" }, [
    el(
      "button",
      {
        type: "button",
        className: "asc-button",
        onclick: () => {
          state.steps.push(newStep(engines));
          redrawSteps();
        },
      },
      "Add Step"
    ),
    el(
      "button",
      {
        type: "button",
        className: "asc-button asc-button-primary",
        onclick: async () => {
          await saveJob({ app, outputDir, state, engines, status });
        },
      },
      "Save Job JSON"
    ),
  ]);

  root.appendChild(toolbar);
  root.appendChild(status);
  root.appendChild(stepsRoot);
  container.appendChild(root);

  if (engines.length === 0) {
    setStatus(status, "No engines were returned by asc registries list.", "error");
  } else {
    state.steps.push(newStep(engines));
    redrawSteps();
  }

  function redrawSteps() {
    stepsRoot.innerHTML = "";

    if (state.steps.length === 0) {
      stepsRoot.appendChild(el("p", { className: "asc-muted" }, "No steps yet."));
      return;
    }

    state.steps.forEach((step, index) => {
      stepsRoot.appendChild(
        renderStepCard({
          step,
          index,
          state,
          engines,
          localScripts,
          ragProfiles,
          instructions,
          redrawSteps,
        })
      );
    });
  }
}

function renderStepCard(context) {
  const {
    step,
    index,
    state,
    engines,
    localScripts,
    ragProfiles,
    instructions,
    redrawSteps,
  } = context;

  const card = el("section", { className: "asc-step-card" });
  const engine = engines.find((item) => item.key === step.engine) || engines[0];
  const engineKind = engine && engine.kind;

  card.appendChild(
    el("div", { className: "asc-step-header" }, [
      el("h3", {}, `Step ${index + 1}`),
      el("div", { className: "asc-step-actions" }, [
        smallButton("↑", () => {
          if (index === 0) return;
          const temp = state.steps[index - 1];
          state.steps[index - 1] = state.steps[index];
          state.steps[index] = temp;
          redrawSteps();
        }),
        smallButton("↓", () => {
          if (index === state.steps.length - 1) return;
          const temp = state.steps[index + 1];
          state.steps[index + 1] = state.steps[index];
          state.steps[index] = temp;
          redrawSteps();
        }),
        smallButton("Remove", () => {
          state.steps.splice(index, 1);
          redrawSteps();
        }),
      ]),
    ])
  );

  card.appendChild(
    fieldRow([
      labelledInput(
        "Step label",
        textInput({
          value: step.label,
          placeholder: "Structure cleanup",
          oninput: (event) => {
            step.label = event.target.value;
          },
        })
      ),
      labelledInput(
        "Engine",
        selectInput({
          value: step.engine,
          options: engines.map((item) => ({
            value: item.key,
            label: `${item.label || item.key} (${item.key})`,
          })),
          onchange: (event) => {
            step.engine = event.target.value;
            redrawSteps();
          },
        })
      ),
    ])
  );

  if (step.engine === "script" || engineKind === "script") {
    card.appendChild(
      labelledInput(
        "Local script",
        selectInput({
          value: step.script,
          options: [
            { value: "", label: "Select script" },
            ...localScripts.map((item) => ({
              value: item.key,
              label: `${item.label || item.key} (${item.key})`,
            })),
          ],
          onchange: (event) => {
            step.script = event.target.value;
          },
        })
      )
    );
  }

  if (step.engine === "rag" || engineKind === "rag") {
    card.appendChild(
      labelledInput(
        "RAG profile",
        selectInput({
          value: step.rag_profile,
          options: [
            {
              value: "",
              label: ragProfiles.length
                ? "Select RAG profile"
                : "No RAG profiles registered yet",
            },
            ...ragProfiles.map((item) => ({
              value: item.key,
              label: `${item.label || item.key} (${item.key})`,
            })),
          ],
          onchange: (event) => {
            step.rag_profile = event.target.value;
          },
        })
      )
    );
  }

  if (engineKind === "llm" || step.engine === "openai" || step.engine === "anthropic") {
    card.appendChild(
      labelledInput(
        "Model",
        textInput({
          value: step.model,
          placeholder: "gpt-5.5-thinking",
          oninput: (event) => {
            step.model = event.target.value;
          },
        })
      )
    );
  }

  card.appendChild(
    labelledInput(
      "Args JSON",
      textareaInput({
        value: step.argsJson,
        rows: 4,
        placeholder: "{}",
        oninput: (event) => {
          step.argsJson = event.target.value;
        },
      })
    )
  );

  card.appendChild(renderInstructionPicker({ step, instructions, redrawSteps }));

  card.appendChild(
    labelledInput(
      "Ad hoc instruction",
      textareaInput({
        value: step.ad_hoc,
        rows: 4,
        placeholder: "Optional one-off instruction for this step.",
        oninput: (event) => {
          step.ad_hoc = event.target.value;
        },
      })
    )
  );

  return card;
}

function renderInstructionPicker({ step, instructions, redrawSteps }) {
  const wrapper = el("div", { className: "asc-instruction-picker" });
  let selectedSlug = "";

  const picker = selectInput({
    value: "",
    options: [
      {
        value: "",
        label: instructions.length ? "Select instruction" : "No ins.* instructions found",
      },
      ...instructions.map((item) => ({
        value: item.slug,
        label: `${item.label} (${item.slug})`,
      })),
    ],
    onchange: (event) => {
      selectedSlug = event.target.value;
    },
  });

  wrapper.appendChild(
    labelledInput(
      "Add instruction",
      fieldRow([
        picker,
        el(
          "button",
          {
            type: "button",
            className: "asc-button asc-button-secondary",
            onclick: () => {
              if (!selectedSlug) return;
              if (!step.instructions.includes(selectedSlug)) {
                step.instructions.push(selectedSlug);
                redrawSteps();
              }
            },
          },
          "Add"
        ),
      ])
    )
  );

  const selectedList = el("div", { className: "asc-selected-instructions" });

  if (step.instructions.length === 0) {
    selectedList.appendChild(el("p", { className: "asc-muted" }, "No instructions selected."));
  } else {
    step.instructions.forEach((slug, index) => {
      const option = instructions.find((item) => item.slug === slug);
      const label = option ? option.label : slug;

      selectedList.appendChild(
        el("div", { className: "asc-selected-instruction" }, [
          el("div", {}, [
            el("strong", {}, label),
            el("div", { className: "asc-muted asc-small" }, slug),
          ]),
          el("div", { className: "asc-step-actions" }, [
            smallButton("↑", () => {
              if (index === 0) return;
              const temp = step.instructions[index - 1];
              step.instructions[index - 1] = step.instructions[index];
              step.instructions[index] = temp;
              redrawSteps();
            }),
            smallButton("↓", () => {
              if (index === step.instructions.length - 1) return;
              const temp = step.instructions[index + 1];
              step.instructions[index + 1] = step.instructions[index];
              step.instructions[index] = temp;
              redrawSteps();
            }),
            smallButton("Remove", () => {
              step.instructions.splice(index, 1);
              redrawSteps();
            }),
          ]),
        ])
      );
    });
  }

  wrapper.appendChild(selectedList);
  return wrapper;
}

async function saveJob({ app, outputDir, state, engines, status }) {
  try {
    if (!state.slug) {
      state.slug = makeJobSlug(state.label);
    }

    const payload = buildJobPayload(state, engines);
    const errors = validateJobPayload(payload);

    if (errors.length) {
      setStatus(status, errors.join("\n"), "error");
      return;
    }

    const outputPath = `${outputDir}/${payload.slug}.json`;

    await ensureFolder(app, outputDir);

    if (await vaultPathExists(app, outputPath)) {
      setStatus(status, `Refusing to overwrite existing job file: ${outputPath}`, "error");
      return;
    }

    await app.vault.adapter.write(
      outputPath,
      `${JSON.stringify(payload, null, 2)}\n`
    );

    setStatus(status, `Saved ${outputPath}`, "success");
  } catch (error) {
    setStatus(status, error && error.stack ? error.stack : String(error), "error");
  }
}

function buildJobPayload(state, engines) {
  return {
    schema_version: 1,
    type: "job",
    slug: state.slug.trim(),
    label: state.label.trim(),
    scope: state.scope,
    steps: state.steps.map((step, index) => {
      const engine = engines.find((item) => item.key === step.engine) || {};
      const args = parseArgsJson(step.argsJson, index + 1);

      if (
        (engine.kind === "llm" || step.engine === "openai" || step.engine === "anthropic") &&
        step.model.trim()
      ) {
        args.model = step.model.trim();
      }

      const out = {
        position: index + 1,
        label: step.label.trim() || `Step ${index + 1}`,
        engine: step.engine,
        args,
        instructions: [...step.instructions],
        ad_hoc: step.ad_hoc.trim(),
      };

      if (step.engine === "local" || engine.kind === "local") {
        out.script = step.script;
      }

      if (step.engine === "rag" || engine.kind === "rag") {
        out.rag_profile = step.rag_profile;
      }

      return out;
    }),
  };
}

function validateJobPayload(payload) {
  const errors = [];

  if (!payload.label) {
    errors.push("Job label is required.");
  }

  if (!/^job\.[a-z0-9][a-z0-9-]*(\.[a-z0-9][a-z0-9-]*)+$/.test(payload.slug)) {
    errors.push(`Invalid job slug: ${payload.slug}`);
  }

  if (!payload.steps.length) {
    errors.push("At least one step is required.");
  }

  payload.steps.forEach((step) => {
    if (!step.engine) {
      errors.push(`Step ${step.position}: engine is required.`);
    }

    if (step.engine === "local" && !step.script) {
      errors.push(`Step ${step.position}: local script is required.`);
    }

    if (!Array.isArray(step.instructions)) {
      errors.push(`Step ${step.position}: instructions must be an array.`);
    }
  });

  return errors;
}

function parseArgsJson(text, position) {
  const trimmed = String(text || "").trim();

  if (!trimmed) {
    return {};
  }

  const parsed = JSON.parse(trimmed);

  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`Step ${position}: Args JSON must be an object.`);
  }

  return parsed;
}

function newStep(engines) {
  const defaultEngine = engines.find((item) => item.key === "local") || engines[0] || { key: "" };

  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    label: "",
    engine: defaultEngine.key,
    script: "",
    rag_profile: "",
    model: "",
    argsJson: "{}",
    instructions: [],
    ad_hoc: "",
  };
}

async function ensureFolder(app, folderPath) {
  if (await vaultPathExists(app, folderPath)) {
    return;
  }

  await app.vault.createFolder(folderPath);
}

async function vaultPathExists(app, path) {
  if (app.vault.adapter.exists) {
    return await app.vault.adapter.exists(path);
  }

  return Boolean(app.vault.getAbstractFileByPath(path));
}

function makeJobSlug(label) {
  const stem = kebab(label || "untitled-job") || "untitled-job";
  return `job.${stem}.${randomSuffix()}`;
}

function kebab(text) {
  return String(text)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
}

function randomSuffix() {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  let value = "";

  for (let index = 0; index < 6; index += 1) {
    value += alphabet[Math.floor(Math.random() * alphabet.length)];
  }

  if (!/[0-9]/.test(value)) {
    const digit = String(Math.floor(Math.random() * 10));
    value = `${value.slice(0, 5)}${digit}`;
  }

  return value;
}

function sortByLabel(items) {
  return [...items].sort((a, b) => {
    const labelCompare = String(a.label || a.key || "").localeCompare(
      String(b.label || b.key || "")
    );
    if (labelCompare !== 0) return labelCompare;
    return String(a.key || "").localeCompare(String(b.key || ""));
  });
}

function labelledInput(label, input) {
  return el("label", { className: "asc-field" }, [
    el("span", { className: "asc-field-label" }, label),
    input,
  ]);
}

function fieldRow(children) {
  return el("div", { className: "asc-row" }, children);
}

function textInput(attrs) {
  return el("input", {
    ...attrs,
    type: "text",
    className: joinClasses("asc-input", attrs.className),
  });
}

function textareaInput(attrs) {
  return el("textarea", {
    ...attrs,
    className: joinClasses("asc-textarea", attrs.className),
  });
}

function selectInput(attrs) {
  const { options = [], ...rest } = attrs;
  const select = el("select", {
    ...rest,
    className: joinClasses("asc-select", rest.className),
  });

  for (const option of options) {
    select.appendChild(el("option", { value: option.value }, option.label));
  }

  select.value = attrs.value || "";
  return select;
}

function smallButton(label, onclick) {
  return el(
    "button",
    {
      type: "button",
      className: "asc-button asc-button-small asc-button-secondary",
      onclick,
    },
    label
  );
}

function setStatus(status, message, kind) {
  status.textContent = message;
  status.className = `asc-job-builder-status asc-status-${kind}`;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null) continue;

    if (key === "className") {
      node.className = value;
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      node.setAttribute(key, value);
    }
  }

  const childList = Array.isArray(children) ? children : [children];

  for (const child of childList) {
    if (child === undefined || child === null) continue;
    node.appendChild(
      child instanceof Node ? child : document.createTextNode(String(child))
    );
  }

  return node;
}

function joinClasses(...values) {
  return values.filter(Boolean).join(" ");
}

function styleElement() {
  return el("style", {}, `
    .asc-job-builder {
      display: grid;
      gap: 1rem;
      max-width: 960px;
    }
    .asc-muted {
      opacity: 0.72;
    }
    .asc-small {
      font-size: 0.82em;
    }
    .asc-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 0.75rem;
      align-items: end;
    }
    .asc-toolbar,
    .asc-step-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
    }
    .asc-field {
      display: grid;
      gap: 0.3rem;
    }
    .asc-field-label {
      font-weight: 600;
    }
    .asc-input,
    .asc-select,
    .asc-textarea {
      width: 100%;
      box-sizing: border-box;
      padding: 0.45rem 0.55rem;
      border: 1px solid var(--background-modifier-border);
      border-radius: 6px;
      background: var(--background-primary);
      color: var(--text-normal);
    }
    .asc-textarea {
      font-family: var(--font-monospace);
    }
    .asc-button {
      padding: 0.45rem 0.7rem;
      border: 1px solid var(--background-modifier-border);
      border-radius: 6px;
      cursor: pointer;
    }
    .asc-button-primary {
      font-weight: 700;
    }
    .asc-button-small {
      padding: 0.25rem 0.45rem;
      font-size: 0.85em;
    }
    .asc-step-card {
      display: grid;
      gap: 0.85rem;
      padding: 1rem;
      border: 1px solid var(--background-modifier-border);
      border-radius: 10px;
      background: var(--background-secondary);
    }
    .asc-step-header,
    .asc-selected-instruction {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: center;
    }
    .asc-selected-instructions {
      display: grid;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }
    .asc-selected-instruction {
      padding: 0.5rem;
      border: 1px solid var(--background-modifier-border);
      border-radius: 8px;
      background: var(--background-primary);
    }
    .asc-job-builder-status {
      white-space: pre-wrap;
      padding: 0.5rem 0.65rem;
      border-radius: 8px;
    }
    .asc-status-info {
      background: var(--background-secondary);
    }
    .asc-status-success {
      background: var(--background-modifier-success);
    }
    .asc-status-error {
      background: var(--background-modifier-error);
    }
  `);
}

module.exports = {
  renderJobBuilder,
};