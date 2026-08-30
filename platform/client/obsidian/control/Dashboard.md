---
cssclasses:
  - autoscribe-dashboard
---

# Dashboard

```dataviewjs
const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("node:path");
const vaultRoot = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const loaderPath = pathMod.join(vaultRoot, "_control", "scripts", "lib", "control-loader.js");
function freshControlLoader() {
  try { delete nodeRequire.cache[nodeRequire.resolve(loaderPath)]; } catch (_) {}
  const { createControlLoader } = nodeRequire(loaderPath);
  return createControlLoader({ app, controlRoot: "_control" });
}
const controlLoader = freshControlLoader();
const loadControl = (relativePath) => controlLoader.requireControl(relativePath);
const { openFileInMain } = loadControl("scripts/lib/workspace.js");
const { readSystemState } = loadControl("scripts/lib/system-state.js");
const { collectAnnotations } = loadControl("scripts/lib/annotate.js");
const { loadConfig } = loadControl("scripts/lib/config-loader.js");
const dashboardConfig = () => loadConfig("dashboard");
const recordsConfig = () => loadConfig("records");
const { readClipboardTextSync } = loadControl("scripts/lib/clipboard.js");

let notify = (message) => new Notice(message);
try {
  ({ notify } = loadControl("scripts/lib/notify.js"));
} catch (error) {
  console.debug("Dashboard: using Obsidian notices", error);
}

const dashboard = dv.container;
const style = dashboard.createEl("style");
style.textContent = `
  .autoscribe-dashboard .dashboard-toolbar { display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; margin:.6rem 0 1rem; }
  .autoscribe-dashboard .dashboard-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(16rem,1fr)); gap:.75rem; margin:.5rem 0 1.2rem; }
  .autoscribe-dashboard .dashboard-card { border:1px solid var(--background-modifier-border); border-radius:8px; padding:.75rem .9rem; background:var(--background-secondary); }
  .autoscribe-dashboard .dashboard-card h3 { margin:0 0 .45rem; font-size:1rem; }
  .autoscribe-dashboard .dashboard-card p { margin:.2rem 0; }
  .autoscribe-dashboard .dashboard-muted { color:var(--text-muted); }
  .autoscribe-dashboard .dashboard-good { color:var(--color-green); }
  .autoscribe-dashboard .dashboard-warn { color:var(--color-orange); }
  .autoscribe-dashboard .dashboard-bad { color:var(--color-red); }
  .autoscribe-dashboard .dashboard-actions { display:grid; grid-template-columns:repeat(auto-fit,minmax(13rem,1fr)); gap:.5rem; margin:.5rem 0 1.2rem; }
  .autoscribe-dashboard .dashboard-actions button { width:100%; min-height:2.4rem; text-align:left; }
  .autoscribe-dashboard button[data-dashboard-hotkey]::after { content: attr(data-dashboard-hotkey); float:right; margin-left:.75rem; color:var(--text-muted); font-size:.82em; font-weight:400; }
  .autoscribe-dashboard .dashboard-section { margin-top:1.35rem; }
  .autoscribe-dashboard .dashboard-refresh-status { font-size:.85rem; }
  .autoscribe-dashboard .dashboard-clipboard { font-size:.85rem; }
  .autoscribe-dashboard .dashboard-clipboard code { user-select:all; }
`;

function section(title) {
  return dashboard
    .createEl("section", { cls: "dashboard-section" })
    .createEl("h2", { text: title })
    .parentElement;
}

function card(parent, title) {
  const el = parent.createEl("div", {
    cls: "dashboard-card",
  });

  el.createEl("h3", { text: title });
  return el;
}

function line(parent, label, value, cls = "") {
  const row = parent.createEl("p");
  row.createEl("strong", { text: `${label}: ` });
  row.createSpan({ text: String(value), cls });
}

async function openInMain(path) {
  try {
    await openFileInMain(app, path, {
      mode: "preview",
    });
  } catch (error) {
    notify(error?.message || String(error), 10000);
  }
}

function addLink(parent, label, path) {
  const row = parent.createEl("div");
  const anchor = row.createEl("a", {
    text: label,
    href: "#",
  });

  anchor.onclick = async (event) => {
    event.preventDefault();
    await openInMain(path);
  };
}

const localHotkeys = new Map();

function normalizeHotkey(value) {
  return String(value || "").trim().toLowerCase();
}

function bindLocalHotkey(button, hotkey) {
  const key = normalizeHotkey(hotkey);
  if (!key) return;

  if (localHotkeys.has(key)) {
    console.warn(`Dashboard: duplicate local hotkey ${key}`);
    return;
  }

  localHotkeys.set(key, button);
  button.dataset.dashboardHotkey = key.toUpperCase();
}

function dashboardIsActive() {
  const leaf = dashboard.closest(".workspace-leaf");
  return Boolean(leaf?.classList.contains("mod-active"));
}

function isTypingTarget(target) {
  return Boolean(
    target?.closest?.(
      'input, textarea, select, [contenteditable="true"], .cm-editor'
    )
  );
}

const onDashboardKeydown = (event) => {
  if (!dashboard.isConnected) {
    document.removeEventListener("keydown", onDashboardKeydown, true);
    return;
  }

  if (
    event.defaultPrevented ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    isTypingTarget(event.target) ||
    !dashboardIsActive()
  ) {
    return;
  }

  const button = localHotkeys.get(normalizeHotkey(event.key));
  if (!button || button.disabled) return;

  event.preventDefault();
  event.stopPropagation();
  button.click();
};

document.addEventListener("keydown", onDashboardKeydown, true);

function addCommand(parent, label, macroPath, hotkey = "") {
  const button = parent.createEl("button", {
    text: label,
  });
  button.type = "button";
  bindLocalHotkey(button, hotkey);

  button.onclick = async () => {
    button.disabled = true;
    notify(`Opening ${label}…`);

    try {
      // Re-enter Control at each button invocation. The Dashboard can remain
      // open across code replacement, so action code must not use its old
      // renderer cache or bypass the canonical runtime boundary.
      const run = freshControlLoader().requireControl(macroPath);
      await run({ app });
    } catch (error) {
      console.error(`${label} failed:`, error);
      notify(
        `${label} failed: ${error?.message || error}`,
        10000
      );
    } finally {
      button.disabled = false;
    }
  };
}

function nextPaint() {
  return new Promise((resolve) =>
    requestAnimationFrame(() => resolve())
  );
}

const stateSection = section("System state");
const toolbar = stateSection.createEl("div", {
  cls: "dashboard-toolbar",
});

const refresh = toolbar.createEl("button", {
  text: "Reload state",
});
refresh.type = "button";
bindLocalHotkey(refresh, "r");

const statusLink = toolbar.createEl("button", {
  text: "Open full System Status",
});
statusLink.type = "button";
bindLocalHotkey(statusLink, "s");
statusLink.onclick = () =>
  openInMain(String(dashboardConfig().paths?.system_status));

const refreshStatus = toolbar.createSpan({
  cls: "dashboard-muted dashboard-refresh-status",
});

const clipboardStatus = toolbar.createSpan({
  cls: "dashboard-muted dashboard-clipboard",
});

function extractClipboardSlug(text) {
  const value = String(text || "").trim();
  if (!value) return "";

  const yamlMatch = value.match(/(?:^|\n)\s*slug\s*:\s*["']?([^\s"'\]}>,]+)["']?/i);
  if (yamlMatch?.[1]) return yamlMatch[1];

  const knownPrefixMatch = value.match(/\b(?:cnt|psg|ins|rol|ctx|spc)\.[a-z0-9][a-z0-9._-]*\b/i);
  if (knownPrefixMatch?.[0]) return knownPrefixMatch[0];

  const dottedSlugMatch = value.match(/\b[a-z][a-z0-9-]*\.[a-z0-9][a-z0-9._-]*\b/i);
  return dottedSlugMatch?.[0] || "";
}

function renderClipboardSlug() {
  let slug = "";
  try {
    slug = extractClipboardSlug(readClipboardTextSync());
  } catch (error) {
    console.debug("Dashboard: clipboard read failed", error);
  }

  clipboardStatus.empty();
  clipboardStatus.createSpan({ text: "Clipboard slug: " });
  if (slug) {
    clipboardStatus.createEl("code", { text: slug });
  } else {
    clipboardStatus.createSpan({ text: "—" });
  }
}

renderClipboardSlug();
const clipboardPoll = window.setInterval(() => {
  if (!dashboard.isConnected) {
    window.clearInterval(clipboardPoll);
    return;
  }
  if (dashboardIsActive()) renderClipboardSlug();
}, 1000);

window.addEventListener("focus", renderClipboardSlug);

const stateGrid = stateSection.createEl("div", {
  cls: "dashboard-grid",
});

async function renderState({
  announce = false,
} = {}) {
  if (refresh.disabled) return;

  refresh.disabled = true;
  refresh.setText("Reloading…");
  refreshStatus.setText(
    "Reading current Git and pipeline state…"
  );
  stateGrid.empty();

  const gitCard = card(stateGrid, "Git");
  line(
    gitCard,
    "Status",
    "Loading…",
    "dashboard-muted"
  );

  const pipelineCard = card(stateGrid, "Pipeline");
  line(
    pipelineCard,
    "Status",
    "Loading…",
    "dashboard-muted"
  );

  let completed = false;

  try {
    await nextPaint();

    const system = await readSystemState(app);

    if (!system.git) {
      throw new Error(
        system.errors.git ||
          "Git state unavailable"
      );
    }

    const state = system.git;

    gitCard.empty();
    gitCard.createEl("h3", { text: "Git" });

    const dirty =
      state.staged +
      state.modified +
      state.untracked;

    line(
      gitCard,
      "Status",
      dirty
        ? `${dirty} changed file${
            dirty === 1 ? "" : "s"
          }`
        : "Clean",
      dirty
        ? "dashboard-warn"
        : "dashboard-good"
    );

    line(gitCard, "Branch", state.branch);
    line(gitCard, "Staged", state.staged);
    line(gitCard, "Modified", state.modified);
    line(gitCard, "Untracked", state.untracked);

    if (state.conflicted) {
      line(
        gitCard,
        "Conflicts",
        state.conflicted,
        "dashboard-bad"
      );
    }

    line(
      gitCard,
      "Remote",
      state.ahead == null
        ? "No upstream"
        : `${state.ahead} ahead / ${state.behind} behind`
    );

    line(
      gitCard,
      "Latest",
      state.latest || "No commits"
    );

    pipelineCard.empty();
    pipelineCard.createEl("h3", {
      text: "Pipeline",
    });

    if (!system.pipeline) {
      pipelineCard.createEl("p", {
        text:
          system.errors.pipeline ||
          "Pipeline state unavailable",
        cls: "dashboard-bad",
      });
    } else {
      const { counts, handoffs } = system.pipeline;

      const active = counts.total || 0;

      line(
        pipelineCard,
        "Active runs",
        active,
        active
          ? "dashboard-warn"
          : "dashboard-good"
      );

      line(
        pipelineCard,
        "Unclaimed",
        counts.unclaimed || 0
      );

      line(
        pipelineCard,
        "Processing",
        counts.waiting || 0
      );

      line(
        pipelineCard,
        "Responses ready",
        counts.response_pending || 0,
        counts.response_pending
          ? "dashboard-good"
          : ""
      );

      line(
        pipelineCard,
        "Recent handoffs",
        handoffs.length
      );
    }

    completed = true;

    const refreshedAt = new Date(
      system.refreshed_at
    );

    refreshStatus.setText(
      `Updated ${refreshedAt.toLocaleTimeString()}`
    );

    if (announce) {
      notify("System state reloaded.");
    }
  } catch (error) {
    const message =
      error?.message || String(error);

    gitCard.empty();
    gitCard.createEl("h3", { text: "Git" });
    gitCard.createEl("p", {
      text: message,
      cls: "dashboard-bad",
    });

    pipelineCard.empty();
    pipelineCard.createEl("h3", {
      text: "Pipeline",
    });

    pipelineCard.createEl("p", {
      text: "State refresh did not complete.",
      cls: "dashboard-bad",
    });

    refreshStatus.setText("Refresh failed");

    if (announce) {
      notify(
        `State refresh failed: ${message}`,
        10000
      );
    }
  } finally {
    refresh.disabled = false;
    refresh.setText("Reload state");

    if (
      !completed &&
      !refreshStatus.getText?.()
    ) {
      refreshStatus.setText("Refresh failed");
    }
  }
}

refresh.addEventListener("click", () => {
  renderClipboardSlug();
  renderState({ announce: true });
});

await renderState();

function countEditorialNotes() {
  const folder =
    app.vault.getAbstractFileByPath(
      String(recordsConfig().editorial_note?.folder)
    );

  return (
    folder?.children?.filter(
      (file) => file.extension === "md"
    ).length || 0
  );
}

const editing = section("Editing status");
const editingGrid = editing.createEl("div", {
  cls: "dashboard-grid",
});

const annotations = card(
  editingGrid,
  "Annotations"
);

line(
  annotations,
  "Items",
  (await collectAnnotations(app)).length
);

addCommand(
  annotations,
  "List Annotations",
  "macros/list-annotations.js",
  "a"
);

const editorialNotes = card(
  editingGrid,
  "Editorial Notes"
);

line(
  editorialNotes,
  "Items",
  countEditorialNotes()
);

addLink(
  editorialNotes,
  "Open Editorial Notes",
  String(dashboardConfig().paths?.editorial_notes_query)
);

const workflow = section("Operations");
const actions = workflow.createEl("div", {
  cls: "dashboard-actions",
});

Object.values(dashboardConfig().actions || {}).forEach((action, index) => {
  const fallbackHotkey = index < 9 ? String(index + 1) : "";
  addCommand(
    actions,
    String(action.label),
    String(action.macro),
    String(action.hotkey || fallbackHotkey)
  );
});

function normalizePath(path) {
  return path
    .replace(/^\/+|\/+$/g, "")
    .toLowerCase();
}

function resolveFolderPath(requestedPath) {
  const exact =
    app.vault.getAbstractFileByPath(
      requestedPath
    );

  if (exact?.children) {
    return exact.path;
  }

  const wanted = normalizePath(requestedPath);

  return (
    app.vault
      .getAllLoadedFiles()
      .find(
        (item) =>
          item?.children &&
          normalizePath(item.path) === wanted
      )?.path ?? null
  );
}

const deprecatedDashboardFiles = new Set(dashboardConfig().deprecated_dashboard_files || []);

function addFolder(
  parent,
  title,
  requestedPath
) {
  const box = card(parent, title);
  const folderPath =
    resolveFolderPath(requestedPath);

  if (!folderPath) {
    box.createEl("p", {
      text: `Folder not found: ${requestedPath}`,
      cls: "dashboard-muted",
    });
    return;
  }

  const files = app.vault
    .getFiles()
    .filter(
      (file) =>
        file.parent?.path === folderPath
    )
    .filter(
      (file) =>
        !deprecatedDashboardFiles.has(
          file.basename.toLowerCase()
        )
    )
    .sort((a, b) =>
      a.basename.localeCompare(
        b.basename,
        undefined,
        {
          numeric: true,
          sensitivity: "base",
        }
      )
    );

  if (!files.length) {
    box.createEl("p", {
      text: "No files found.",
      cls: "dashboard-muted",
    });
    return;
  }

  for (const file of files) {
    addLink(box, file.basename, file.path);
  }
}

const resources = section("Vault resources");
const resourceGrid = resources.createEl(
  "div",
  {
    cls: "dashboard-grid",
  }
);

for (const resource of Object.values(dashboardConfig().resource_folders || {})) {
  addFolder(resourceGrid, String(resource.label), String(resource.path));
}
```
