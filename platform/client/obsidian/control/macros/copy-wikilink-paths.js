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

function getActiveMarkdownFile(app) {
  const file = app?.workspace?.getActiveFile();
  if (!file || file.extension !== "md") {
    throw new Error("The active file is not a Markdown file.");
  }
  return file;
}

module.exports = async function copyWikilinkPaths(params = {}) {
  const app = params.app ?? globalThis.app;
  if (!app?.vault || !app?.workspace || !app?.metadataCache) {
    throw new Error("Obsidian app instance is unavailable.");
  }

  const loader = createControlRuntime(app);
  const { extractResolvedWikilinks } = loader.requireControl("scripts/lib/wikilinks.js");
  const { copyText } = loader.requireControl("scripts/lib/clipboard.js");
  const { notify } = loader.requireControl("scripts/lib/notify.js");

  const file = getActiveMarkdownFile(app);
  const text = await app.vault.cachedRead(file);

  // extractResolvedWikilinks() preserves regex encounter order, so the output
  // order exactly follows the wikilinks in the source document. Do not sort or
  // deduplicate: repeated links can be intentional in a compiled run.
  const links = extractResolvedWikilinks({
    app,
    text,
    sourcePath: file.path,
  });

  if (!links.length) {
    notify(`No wikilinks found in ${file.name}.`);
    return;
  }

  const unresolved = links.filter((link) => !link.resolved || !link.vaultPath);
  if (unresolved.length) {
    const details = unresolved.map((link) => link.raw).join(", ");
    throw new Error(
      `Could not resolve ${unresolved.length} wikilink${unresolved.length === 1 ? "" : "s"}: ${details}`
    );
  }

  const output = links.map((link) => link.vaultPath).join("\n");
  const copied = await copyText(output, {
    notify,
    successMessage: `Copied ${links.length} resolved wikilink path${links.length === 1 ? "" : "s"} in document order.`,
    failureMessage: "Could not copy resolved wikilink paths.",
  });

  if (!copied) throw new Error("Could not copy resolved wikilink paths.");
};
