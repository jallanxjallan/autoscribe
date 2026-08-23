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

module.exports = function make_slug(tp, prefix) {
  const app = tp?.app || globalThis.app;

  if (!app) {
    throw new Error("Obsidian app object unavailable.");
  }

  const { makeSlug } = createControlRuntime(app).requireControl("scripts/lib/slug.js");

  return makeSlug(prefix, tp.file.title);
};