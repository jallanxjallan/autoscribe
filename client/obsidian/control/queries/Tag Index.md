# Tag Index

````dataviewjs
const CONFIG = {
  tocPath: "",
  tempRoot: "",
  debug: false,

  queryTitle: "Tag Index",
  namespace: "tag-index",
  bridgeName: "__tagIndexSelection",
  showTagColumn: true,
  visibleFilterKeys: ["tag_values"],

  // Keep these as the content filter, but do not expose them as a selector.
  slugPrefixes: ["cnt_", "img_"],
  selectorChoiceLimit: 10,

  unicodeReference: [
    { symbol: "❦", code: "U+2766", label: "motif", meaning: "Motif" },
    { symbol: "▣", code: "U+25A3", label: "boxout", meaning: "Boxout" },
    { symbol: "◈", code: "U+25C8", label: "feature", meaning: "Feature" },
    { symbol: "¶", code: "U+00B6", label: "narrative", meaning: "Narrative" },
    { symbol: "▯", code: "U+25AF", label: "single", meaning: "Single page" },
    { symbol: "▭", code: "U+25AD", label: "double", meaning: "Double page" },
  ],

  defaultClass: "—",
  defaultTags: "—",
  defaultLayoutComponent: "—",

  excludePaths: [
    ".obsidian",
    ".trash",
    ".autoscribe",
  ],
};

const nodeRequire = typeof require === "function" ? require : window.require;
const pathMod = nodeRequire("path");
const vaultBasePath = app.vault.adapter.getBasePath?.() || app.vault.adapter.basePath;
const queryPathForBootstrap = app.workspace.getActiveFile().path;
const markerIndexForBootstrap = queryPathForBootstrap.indexOf("/queries/");

if (markerIndexForBootstrap === -1) {
  throw new Error(`Query is not inside a queries folder: ${queryPathForBootstrap}`);
}

const controlRootForBootstrap = queryPathForBootstrap.slice(0, markerIndexForBootstrap);
const runtimePath = pathMod.join(
  vaultBasePath,
  ...controlRootForBootstrap.split("/").filter(Boolean),
  "scripts",
  "lib",
  "query-runtime.js"
);

const { createQueryRuntime } = nodeRequire(runtimePath);
const runtime = createQueryRuntime({ app, queryTitle: "Tag Index query" });
const { loader, queryPath, vaultName } = runtime;

const { renderSelectionQuery } = loader.requireControl("scripts/lib/selection-query.js");
const { makeContentIndexView } = loader.requireControl("scripts/lib/content-index-view.js");

function compactChoiceLists(root, limit) {
  if (!Number.isFinite(limit) || limit < 1) return;

  const blocks = [...root.querySelectorAll("div, fieldset")]
    .map(block => ({
      block,
      choices: [...block.children].filter(child =>
        child.tagName === "LABEL" &&
        child.querySelector('input[type="checkbox"], input[type="radio"]')
      ),
    }))
    .filter(item => item.choices.length > limit)
    .filter((item, _index, items) =>
      !items.some(other => other !== item && other.block.contains(item.block))
    );

  for (const { block, choices } of blocks) {
    const hidden = choices.slice(limit);
    if (!hidden.length) continue;

    for (const choice of hidden) choice.style.display = "none";

    const toggle = block.createEl("a", {
      href: "#",
      text: `more (${hidden.length})`,
    });

    toggle.style.display = "inline-block";
    toggle.style.marginTop = "0.25em";

    toggle.onclick = event => {
      event.preventDefault();

      const expanded = toggle.dataset.expanded === "true";
      for (const choice of hidden) choice.style.display = expanded ? "none" : "";

      toggle.dataset.expanded = expanded ? "false" : "true";
      toggle.setText(expanded ? `more (${hidden.length})` : "less");
    };
  }
}

async function renderTidySelectionQuery(options) {
  const result = await renderSelectionQuery(options);
  compactChoiceLists(dv.container, CONFIG.selectorChoiceLimit);
  return result;
}

await makeContentIndexView({
  app,
  dv,
  nodeRequire: runtime.nodeRequire,
  queryPath,
  vaultName,
  config: CONFIG,
  renderSelectionQuery: renderTidySelectionQuery,
}).render();
````
