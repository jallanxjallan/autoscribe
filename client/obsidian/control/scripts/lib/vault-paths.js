function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;

  if (typeof adapter?.getBasePath === "function") {
    return adapter.getBasePath();
  }

  if (adapter?.basePath) {
    return adapter.basePath;
  }

  return "";
}

function getVaultAbsolutePath(app, vaultPath) {
  const base = getVaultBasePath(app);
  if (!base || !vaultPath) return null;

  return `${base.replace(/\/+$/, "")}/${String(vaultPath).replace(/^\/+/, "")}`;
}

module.exports = {
  getVaultBasePath,
  getVaultAbsolutePath,
};
