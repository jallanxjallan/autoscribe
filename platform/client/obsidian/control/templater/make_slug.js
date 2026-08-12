function nodeRequire(name) {
  if (typeof require === "function") return require(name);
  if (typeof window !== "undefined" && window.require) return window.require(name);
  throw new Error(`Node module unavailable: ${name}`);
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;

  if (typeof adapter?.getBasePath === "function") {
    return adapter.getBasePath();
  }

  if (adapter?.basePath) {
    return adapter.basePath;
  }

  throw new Error("Could not determine vault base path.");
}

function requireFromVault(app, vaultRelativePath) {
  const path = nodeRequire("path");
  const fullPath = path.join(getVaultBasePath(app), vaultRelativePath);

  if (nodeRequire.cache?.[fullPath]) {
    delete nodeRequire.cache[fullPath];
  }

  return nodeRequire(fullPath);
}

module.exports = function make_slug(tp, prefix) {
  const app = tp?.app || globalThis.app;

  if (!app) {
    throw new Error("Obsidian app object unavailable.");
  }

  const { makeSlug } = requireFromVault(
    app,
    "_control/scripts/lib/slug.js"
  );

  return makeSlug(prefix, tp.file.title);
};