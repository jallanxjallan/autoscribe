function getNodeRequire() {
  if (typeof require === "function") return require;
  throw new Error("Obsidian Desktop Node access is unavailable.");
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

function getVaultName(app) {
  return String(app?.vault?.getName?.() || app?.vault?.name || "vault").trim() || "vault";
}

function getActiveQueryPath(app) {
  const activeFile = app?.workspace?.getActiveFile?.();
  const queryPath = activeFile?.path;

  if (!queryPath) {
    throw new Error("Could not determine active query path.");
  }

  return queryPath;
}

function getControlRootFromQueryPath(queryPath, queryTitle = "Query") {
  const marker = "/queries/";
  const markerIndex = queryPath.indexOf(marker);

  if (markerIndex === -1) {
    throw new Error(`${queryTitle} is not inside a queries folder: ${queryPath}`);
  }

  const controlRoot = queryPath.slice(0, markerIndex);

  if (!controlRoot) {
    throw new Error(`Could not determine control root from query path: ${queryPath}`);
  }

  return controlRoot;
}

function createQueryRuntime({ app, queryTitle = "Query" }) {
  if (!app) throw new Error("createQueryRuntime requires app.");

  const nodeRequire = getNodeRequire();
  const pathMod = nodeRequire("path");
  const vaultBasePath = getVaultBasePath(app);
  const vaultName = getVaultName(app);
  const queryPath = getActiveQueryPath(app);
  const controlRoot = getControlRootFromQueryPath(queryPath, queryTitle);

  const controlLoaderPath = pathMod.join(
    vaultBasePath,
    ...controlRoot.split("/").filter(Boolean),
    "scripts",
    "lib",
    "control-loader.js"
  );

  const { createControlLoader } = nodeRequire(controlLoaderPath);
  const loader = createControlLoader({ app });

  return {
    app,
    nodeRequire: loader.nodeRequire,
    loader,
    pathMod,
    vaultBasePath,
    vaultName,
    queryPath,
    controlRoot,
    controlLoaderPath
  };
}

module.exports = {
  createQueryRuntime,
  getNodeRequire,
  getVaultBasePath,
  getVaultName,
  getActiveQueryPath,
  getControlRootFromQueryPath
};
