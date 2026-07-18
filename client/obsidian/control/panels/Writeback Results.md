# Writeback Results

```dataviewjs
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawnSync } = require("node:child_process");
const rootNode = this.container;

function el(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  Object.assign(node, attrs);
  if (text !== null) node.textContent = text;
  return node;
}

function vaultRootFromObsidian(app) {
  const adapter = app?.vault?.adapter;
  if (adapter && typeof adapter.getBasePath === "function") return adapter.getBasePath();
  if (adapter && typeof adapter.basePath === "string") return adapter.basePath;
  throw new Error("Could not determine vault root from Obsidian adapter.");
}

function vaultKey(root) {
  const name = path.basename(root).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "vault";
  const digest = crypto.createHash("sha1").update(root).digest("hex").slice(0, 8);
  return `${name}-${digest}`;
}

function writebackManifestPath(root) {
  return path.join(os.homedir(), ".local/share/autoscribe/obsidian/vaults", vaultKey(root), "writeback", "writeback-results.json");
}

function normalizeRelPath(relPath) {
  return String(relPath || "").replace(/\\/g, "/").replace(/^\.\//, "");
}

function gitStatus(root, relPath) {
  const gitBin = process.env.OBSIDIAN_GIT_BIN || process.env._OBSIDIAN_GIT_BIN || "git";
  const result = spawnSync(gitBin, ["status", "--porcelain", "--", relPath], { cwd: root, encoding: "utf8", shell: false });
  if (result.error) return { ok: false, status: "", message: result.error.message };
  if (result.status !== 0) return { ok: false, status: "", message: String(result.stderr || result.stdout || "").trim() || `git exited ${result.status}` };
  return { ok: true, status: String(result.stdout || "").trim(), message: "" };
}

function shortIdentity(value) {
  const text = String(value || "");
  return text.length <= 10 ? text : `${text.slice(0, 6)}…${text.slice(-4)}`;
}

function statusLabel(root, relPath) {
  const status = gitStatus(root, relPath);
  if (!status.ok) return `git error: ${status.message}`;
  if (!status.status) return "clean";
  return `dirty: ${status.status.slice(0, 2).trim() || "modified"}`;
}

function render() {
  rootNode.replaceChildren();
  const refresh = el("button", {}, "Refresh");
  refresh.onclick = render;
  rootNode.append(refresh);

  try {
    const root = vaultRootFromObsidian(app);
    const manifestPath = writebackManifestPath(root);
    if (!fs.existsSync(manifestPath)) {
      rootNode.append(el("p", {}, "No writeback manifest found for this vault."), el("p", {}, `Expected: ${manifestPath}`));
      return;
    }

    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    const items = Array.isArray(manifest.items) ? manifest.items : [];
    rootNode.append(el("p", {}, `Manifest: ${manifestPath}`), el("p", {}, `Timestamp: ${manifest.timestamp || "unknown"}`));

    if (manifest.vault && manifest.vault !== root) {
      rootNode.append(el("p", {}, "⚠️ Manifest vault does not match active vault."), el("p", {}, `Manifest vault: ${manifest.vault}`), el("p", {}, `Active vault: ${root}`));
    }
    if (!items.length) {
      rootNode.append(el("p", {}, "No writeback items in the latest manifest."));
      return;
    }

    const table = el("table");
    const head = el("tr");
    for (const label of ["Writeback", "Git", "Slug", "File", "Call", "Result"]) head.append(el("th", {}, label));
    table.append(head);

    for (const item of items) {
      const relPath = normalizeRelPath(item.path);
      const row = el("tr");
      const link = el("a", { href: relPath }, relPath);
      link.onclick = (event) => { event.preventDefault(); app.workspace.openLinkText(relPath, "", false); };
      row.append(
        el("td", {}, item.changed ? "changed" : "unchanged"),
        el("td", {}, statusLabel(root, relPath)),
        el("td", {}, item.prompt_slug || ""),
        el("td"),
        el("td", {}, shortIdentity(item.call_identity)),
        el("td", {}, shortIdentity(item.result_identity)),
      );
      row.children[3].append(link);
      table.append(row);
    }
    rootNode.append(table);
  } catch (error) {
    rootNode.append(el("p", {}, `Writeback Results failed: ${error.message}`));
  }
}

render();
```
