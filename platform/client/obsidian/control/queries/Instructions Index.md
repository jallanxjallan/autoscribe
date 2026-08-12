# Instructions Index

````dataviewjs
const CONFIG = {
  title: "Instructions Index",

  // Instruction notes may all live in one folder. Metadata and slug prefixes,
  // rather than physical subfolders, determine membership and grouping.
  instructionFolder: "instructions",
  slugPrefixes: ["rol", "cxt", "ins", "ref"],
  classes: ["task", "role", "context", "reference"],

  excludePaths: [
    ".obsidian",
    ".trash",
    ".autoscribe",
  ],
};

const { Modal } = require("obsidian");

function normalized(value) {
  return String(value ?? "").trim();
}

function slugPrefix(value) {
  return normalized(value).split(/[._-]/, 1)[0].toLowerCase();
}

function pathIsExcluded(path) {
  return CONFIG.excludePaths.some(prefix =>
    path === prefix || path.startsWith(`${prefix}/`)
  );
}

function inInstructionFolder(path) {
  const folder = normalized(CONFIG.instructionFolder).replace(/^\/+|\/+$/g, "");
  if (!folder) return true;
  return path === folder || path.startsWith(`${folder}/`);
}

function inferClass(frontmatter) {
  const explicit = normalized(frontmatter?.class).toLowerCase();
  if (explicit) return explicit;

  const prefix = slugPrefix(frontmatter?.slug);
  return {
    rol: "role",
    cxt: "context",
    ins: "task",
    ref: "reference",
  }[prefix] || "unknown";
}

function isInstruction(file, frontmatter) {
  if (pathIsExcluded(file.path)) return false;
  if (!inInstructionFolder(file.path)) return false;

  const type = normalized(frontmatter?.type).toLowerCase();
  const prefix = slugPrefix(frontmatter?.slug || file.basename);
  return type === "instruction" || CONFIG.slugPrefixes.includes(prefix);
}

function flattenLinks(value, label = "dependency", output = []) {
  if (value == null || value === "") return output;

  if (Array.isArray(value)) {
    for (const item of value) flattenLinks(item, label, output);
    return output;
  }

  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      flattenLinks(item, key, output);
    }
    return output;
  }

  const text = String(value);
  const matches = [...text.matchAll(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g)];

  if (!matches.length) {
    output.push({ label, linktext: text.trim(), display: text.trim() });
    return output;
  }

  for (const match of matches) {
    const linktext = match[1].trim();
    const display = (match[2] || match[1]).trim();
    if (linktext) output.push({ label, linktext, display });
  }

  return output;
}

function resolveDependency(sourceFile, dependency) {
  const target = app.metadataCache.getFirstLinkpathDest(
    dependency.linktext,
    sourceFile.path
  );

  return {
    ...dependency,
    target,
    targetPath: target?.path || null,
  };
}

function collectRows() {
  return app.vault.getMarkdownFiles()
    .map(file => {
      const cache = app.metadataCache.getFileCache(file);
      const frontmatter = cache?.frontmatter || {};
      if (!isInstruction(file, frontmatter)) return null;

      const dependencies = flattenLinks(frontmatter.dependencies)
        .map(dependency => resolveDependency(file, dependency));

      return {
        file,
        path: file.path,
        title: normalized(frontmatter.title) || file.basename,
        slug: normalized(frontmatter.slug),
        className: inferClass(frontmatter),
        scope: normalized(frontmatter.scope) || "—",
        tags: Array.isArray(frontmatter.tags)
          ? frontmatter.tags.map(String).filter(Boolean)
          : normalized(frontmatter.tags)
            ? [normalized(frontmatter.tags)]
            : [],
        dependencies,
        usedBy: [],
        warnings: [],
      };
    })
    .filter(Boolean);
}

function addReverseReferences(rows) {
  const byPath = new Map(rows.map(row => [row.path, row]));

  for (const row of rows) {
    for (const dependency of row.dependencies) {
      const targetRow = dependency.targetPath
        ? byPath.get(dependency.targetPath)
        : null;

      if (targetRow) {
        targetRow.usedBy.push({
          sourcePath: row.path,
          sourceTitle: row.title,
          label: dependency.label,
        });
      }
    }
  }
}

function addWarnings(rows) {
  const byPath = new Map(rows.map(row => [row.path, row]));

  for (const row of rows) {
    if (!row.slug) row.warnings.push("missing slug");
    if (!CONFIG.classes.includes(row.className)) {
      row.warnings.push(`unknown class: ${row.className}`);
    }

    const expectedPrefix = {
      role: "rol",
      context: "cxt",
      task: "ins",
      reference: "ref",
    }[row.className];

    if (row.slug && expectedPrefix && slugPrefix(row.slug) !== expectedPrefix) {
      row.warnings.push(`class expects ${expectedPrefix} slug`);
    }

    if (row.className === "task") {
      const labels = new Set(row.dependencies.map(item => item.label));
      if (!labels.has("role")) row.warnings.push("task has no role dependency");
    }

    const seenLabels = new Map();
    for (const dependency of row.dependencies) {
      seenLabels.set(
        dependency.label,
        (seenLabels.get(dependency.label) || 0) + 1
      );

      if (!dependency.target) {
        row.warnings.push(`unresolved ${dependency.label}: ${dependency.linktext}`);
        continue;
      }

      if (!byPath.has(dependency.target.path)) {
        row.warnings.push(
          `${dependency.label} points outside instructions: ${dependency.display}`
        );
      }

      if (dependency.target.path === row.path) {
        row.warnings.push(`self-dependency: ${dependency.label}`);
      }
    }

    for (const [label, count] of seenLabels) {
      if (count > 1) row.warnings.push(`duplicate dependency label: ${label}`);
    }

    if (["role", "context", "reference"].includes(row.className) && !row.usedBy.length) {
      row.warnings.push("unused dependency file");
    }
  }
}

function detectCycles(rows) {
  const byPath = new Map(rows.map(row => [row.path, row]));
  const visiting = new Set();
  const visited = new Set();

  function visit(row, trail = []) {
    if (visiting.has(row.path)) {
      const cycle = [...trail, row.path]
        .map(path => byPath.get(path)?.title || path)
        .join(" → ");
      for (const path of trail) {
        const member = byPath.get(path);
        if (member && !member.warnings.includes("circular dependency")) {
          member.warnings.push("circular dependency");
        }
      }
      return cycle;
    }

    if (visited.has(row.path)) return null;
    visiting.add(row.path);

    for (const dependency of row.dependencies) {
      const next = dependency.targetPath ? byPath.get(dependency.targetPath) : null;
      if (next) visit(next, [...trail, row.path]);
    }

    visiting.delete(row.path);
    visited.add(row.path);
    return null;
  }

  for (const row of rows) visit(row);
}

function createInternalLink(parent, path, text) {
  const link = parent.createEl("a", { text, href: path });
  link.addClass("internal-link");
  link.dataset.href = path;
  link.onclick = event => {
    event.preventDefault();
    app.workspace.openLinkText(path, "", false);
  };
  return link;
}

function renderLinkList(cell, items, emptyText = "—") {
  if (!items.length) {
    cell.setText(emptyText);
    return;
  }

  const list = cell.createEl("ul");
  list.style.margin = "0";
  list.style.paddingLeft = "1.2em";

  for (const item of items) {
    const li = list.createEl("li");
    if (item.label) li.createEl("strong", { text: `${item.label}: ` });

    if (item.targetPath || item.sourcePath) {
      createInternalLink(
        li,
        item.targetPath || item.sourcePath,
        item.display || item.sourceTitle
      );
    } else {
      li.createEl("span", { text: item.display || item.linktext });
    }
  }
}

function renderWarnings(cell, warnings) {
  if (!warnings.length) {
    cell.setText("—");
    return;
  }

  const list = cell.createEl("ul");
  list.style.margin = "0";
  list.style.paddingLeft = "1.2em";

  for (const warning of warnings) {
    list.createEl("li", { text: warning });
  }
}

function renderTable(parent, rows) {
  const wrap = parent.createDiv();
  wrap.style.overflowX = "auto";

  const table = wrap.createEl("table");
  table.classList.add("dataview", "table-view-table");
  table.style.width = "100%";

  const thead = table.createEl("thead");
  const header = thead.createEl("tr");
  ["File", "Scope", "Dependencies", "Used by", "Warnings"]
    .forEach(text => header.createEl("th", { text }));

  const tbody = table.createEl("tbody");

  for (const row of rows) {
    const tr = tbody.createEl("tr");

    const fileCell = tr.createEl("td");
    createInternalLink(fileCell, row.path, row.title);
    if (row.slug) {
      const slug = fileCell.createEl("div", { text: row.slug });
      slug.style.opacity = "0.65";
      slug.style.fontSize = "0.85em";
    }

    tr.createEl("td", { text: row.scope });
    renderLinkList(tr.createEl("td"), row.dependencies);
    renderLinkList(tr.createEl("td"), row.usedBy);
    renderWarnings(tr.createEl("td"), row.warnings);
  }
}

function makeSelect(parent, label, values, selected, onChange) {
  const wrap = parent.createDiv();
  wrap.style.display = "flex";
  wrap.style.alignItems = "center";
  wrap.style.gap = "0.4em";

  wrap.createEl("label", { text: label });
  const select = wrap.createEl("select");
  select.createEl("option", { text: "All", value: "" });

  for (const value of values) {
    select.createEl("option", { text: value, value });
  }

  select.value = selected;
  select.onchange = () => onChange(select.value);
}

const rows = collectRows();
addReverseReferences(rows);
addWarnings(rows);
detectCycles(rows);

const state = {
  className: "",
  scope: "",
  warningsOnly: false,
};

function render() {
  dv.container.empty();

  const heading = dv.container.createEl("h1", { text: CONFIG.title });
  heading.style.marginBottom = "0.4em";

  const controls = dv.container.createDiv();
  controls.style.display = "flex";
  controls.style.flexWrap = "wrap";
  controls.style.gap = "1em";
  controls.style.marginBottom = "1em";

  const classes = [...new Set(rows.map(row => row.className))].sort();
  const scopes = [...new Set(rows.map(row => row.scope).filter(value => value !== "—"))].sort();

  makeSelect(controls, "Class", classes, state.className, value => {
    state.className = value;
    render();
  });

  makeSelect(controls, "Scope", scopes, state.scope, value => {
    state.scope = value;
    render();
  });

  const warningWrap = controls.createDiv();
  warningWrap.style.display = "flex";
  warningWrap.style.alignItems = "center";
  warningWrap.style.gap = "0.4em";
  const warningBox = warningWrap.createEl("input", { type: "checkbox" });
  warningBox.checked = state.warningsOnly;
  warningBox.onchange = () => {
    state.warningsOnly = warningBox.checked;
    render();
  };
  warningWrap.createEl("label", { text: "Warnings only" });

  const filtered = rows
    .filter(row => !state.className || row.className === state.className)
    .filter(row => !state.scope || row.scope === state.scope)
    .filter(row => !state.warningsOnly || row.warnings.length)
    .sort((a, b) => a.title.localeCompare(b.title));

  const warningCount = filtered.filter(row => row.warnings.length).length;
  dv.container.createEl("p", {
    text: `${filtered.length} instruction file(s); ${warningCount} with warnings.`,
  });

  const groupOrder = ["task", "role", "context", "reference", "unknown"];
  const groups = new Map();

  for (const row of filtered) {
    if (!groups.has(row.className)) groups.set(row.className, []);
    groups.get(row.className).push(row);
  }

  for (const className of groupOrder) {
    const groupRows = groups.get(className);
    if (!groupRows?.length) continue;

    dv.container.createEl("h2", {
      text: `${className[0].toUpperCase()}${className.slice(1)}s (${groupRows.length})`,
    });
    renderTable(dv.container, groupRows);
  }

  for (const [className, groupRows] of groups) {
    if (groupOrder.includes(className)) continue;
    dv.container.createEl("h2", { text: `${className} (${groupRows.length})` });
    renderTable(dv.container, groupRows);
  }
}

render();
````
